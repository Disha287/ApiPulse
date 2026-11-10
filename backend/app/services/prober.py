import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Optional
import uuid
import httpx
from sqlalchemy import desc, select
from app.core.database import AsyncSessionLocal
from app.models.models import Incident, IncidentStatus, Monitor, MonitorStatus, ProbeLog
from app.services.alert_service import (
    send_recovery_notification,
    trigger_alert_if_not_cooled_down,
)
from app.services.anomaly_detector import evaluate_latency_anomaly
from app.services.rca_service import populate_incident_rca

logger = logging.getLogger("apipulse.prober")


async def execute_probe(
    monitor_id: uuid.UUID,
    client: httpx.AsyncClient,
) -> Optional[ProbeLog]:
    """
    Executes a high-precision asynchronous HTTP health probe against a target monitor.
    Applies the 3-strike state machine and hybrid ML latency anomaly detection:
      - 1-2 consecutive failures -> DEGRADED
      - 3+ consecutive failures  -> DOWN (opens Incident & evaluates Redis cooldown alert)
      - Success on open incident -> HEALTHY (resolves Incident & sends recovery)
      - On successful probe      -> Evaluates rolling Z-Score & Isolation Forest in threadpool
    """
    async with AsyncSessionLocal() as session:
        monitor = await session.get(Monitor, monitor_id)
        if not monitor or not monitor.is_active:
            return None

        start_time = time.perf_counter()
        status_code: Optional[int] = None
        error_message: Optional[str] = None
        is_success: bool = False
        response_snippet: Optional[str] = None

        try:
            response = await client.request(
                method=monitor.method,
                url=monitor.url,
                timeout=monitor.timeout_seconds,
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code
            is_success = (response.status_code == monitor.expected_status)
            if not is_success:
                try:
                    response_snippet = response.text[:300].strip()
                except Exception:
                    response_snippet = None
                error_message = (
                    f"Expected {monitor.expected_status}, got {response.status_code}"
                )
                if response_snippet:
                    error_message += f" | Body: {response_snippet}"
        except httpx.TimeoutException:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            is_success = False
            status_code = None
            error_message = "Request timed out"
        except httpx.RequestError as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            is_success = False
            status_code = None
            error_message = str(exc)
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            is_success = False
            status_code = None
            error_message = f"Unexpected error: {str(exc)}"

        now = datetime.now(timezone.utc)
        monitor.last_checked_at = now

        is_anomaly: bool = False
        anomaly_score: Optional[float] = None

        # --- 3-Strike State Machine & Anomaly Detection ---
        if not is_success:
            monitor.consecutive_failures += 1

            if monitor.consecutive_failures in (1, 2):
                monitor.current_status = MonitorStatus.DEGRADED
                logger.info(
                    f"Monitor '{monitor.name}' ({monitor.id}) Strike {monitor.consecutive_failures}/3 -> DEGRADED"
                )
            else:
                # 3 or more consecutive failures -> DOWN
                monitor.current_status = MonitorStatus.DOWN

                # Find any active OPEN incident for this monitor
                stmt = select(Incident).where(
                    Incident.monitor_id == monitor.id,
                    Incident.status == IncidentStatus.OPEN,
                )
                res = await session.execute(stmt)
                open_incident = res.scalar_one_or_none()

                if not open_incident:
                    open_incident = Incident(
                        monitor_id=monitor.id,
                        status=IncidentStatus.OPEN,
                        started_at=now,
                        failure_count=monitor.consecutive_failures,
                        trigger_error=error_message,
                    )
                    session.add(open_incident)
                    await session.flush()
                else:
                    open_incident.failure_count = monitor.consecutive_failures
                    if not open_incident.trigger_error:
                        open_incident.trigger_error = error_message

                # Automated AI Root-Cause Analysis (LLM SRE Engine + Fallback)
                if not open_incident.rca_summary:
                    try:
                        await populate_incident_rca(
                            open_incident.id,
                            response_snippet=response_snippet,
                            db=session,
                        )
                    except Exception as rca_err:
                        logger.error(
                            f"Failed to generate RCA for incident {open_incident.id}: {rca_err}"
                        )

                await trigger_alert_if_not_cooled_down(monitor, open_incident)

        else:
            # Probe succeeded
            monitor.consecutive_failures = 0
            monitor.current_status = MonitorStatus.HEALTHY

            # Check if an OPEN incident needs resolution
            stmt = select(Incident).where(
                Incident.monitor_id == monitor.id,
                Incident.status == IncidentStatus.OPEN,
            )
            res = await session.execute(stmt)
            open_incident = res.scalar_one_or_none()

            if open_incident:
                open_incident.status = IncidentStatus.RESOLVED
                open_incident.resolved_at = now
                await send_recovery_notification(monitor, open_incident)

            # Unsupervised ML Latency Anomaly Detection (Isolation Forest + Rolling Z-Score)
            hist_stmt = (
                select(ProbeLog.latency_ms)
                .where(ProbeLog.monitor_id == monitor.id, ProbeLog.is_success == True)
                .order_by(desc(ProbeLog.timestamp))
                .limit(50)
            )
            hist_res = await session.execute(hist_stmt)
            historical_latencies = list(hist_res.scalars().all())

            # Run in threadpool so CPU-bound fitting never blocks the async event loop
            is_anomaly, anomaly_score = await asyncio.to_thread(
                evaluate_latency_anomaly, latency_ms, historical_latencies
            )

            if is_anomaly:
                baseline_mean = (
                    round(sum(historical_latencies) / len(historical_latencies), 2)
                    if historical_latencies
                    else 0.0
                )
                logger.warning(
                    "\n" + "=" * 65 + "\n"
                    f"[ML ANOMALY DETECTED] ⚠️ LATENCY SPIKE (Isolation Forest + Z-Score)\n"
                    f"Monitor:    {monitor.name} (ID: {monitor.id})\n"
                    f"Target URL: {monitor.url}\n"
                    f"Latency:    {latency_ms} ms (Baseline Mean: {baseline_mean} ms)\n"
                    f"Z-Score:    {anomaly_score}σ (Samples: {len(historical_latencies)})\n"
                    + "=" * 65
                )

        probe_log = ProbeLog(
            monitor_id=monitor.id,
            timestamp=now,
            status_code=status_code,
            latency_ms=latency_ms,
            is_success=is_success,
            error_message=error_message,
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score,
        )

        session.add(probe_log)
        await session.commit()
        await session.refresh(probe_log)
        return probe_log
