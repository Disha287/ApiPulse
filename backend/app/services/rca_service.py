import logging
import re
from typing import List, Optional
import uuid
import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.models import Incident, Monitor, ProbeLog

logger = logging.getLogger("apipulse.rca")


def _generate_deterministic_rca(
    monitor_name: str,
    target_url: str,
    method: str,
    trigger_error: str,
    status_code: Optional[int],
    response_snippet: Optional[str],
    recent_latencies: List[float],
) -> str:
    """
    Deterministic SRE Heuristic Engine:
    Generates a structured 3-section Markdown RCA report based on incident failure signature.
    """
    latency_summary = (
        f"Average recent latency was {round(sum(recent_latencies)/len(recent_latencies), 1)} ms "
        f"(peak: {max(recent_latencies)} ms over {len(recent_latencies)} probe samples)."
        if recent_latencies
        else "No prior latency telemetry available."
    )

    snippet_info = f"\n- **Response Body Snippet:** `{response_snippet}`" if response_snippet else ""

    # 1. HTTP 429 - Rate Limiting / Quota Exhaustion
    if status_code == 429 or "429" in trigger_error:
        return (
            f"### Root Cause Diagnosis\n"
            f"The target service `{monitor_name}` triggered an outage due to **HTTP 429 (Too Many Requests)**. "
            f"The upstream gateway or API rate limiter has throttled incoming traffic as the request volume exceeded "
            f"the configured token bucket or concurrency threshold.\n\n"
            f"### Telemetry & Evidence Correlation\n"
            f"- **Target:** `{method} {target_url}`\n"
            f"- **Failure Signature:** `{trigger_error}`{snippet_info}\n"
            f"- **Latency Telemetry:** {latency_summary}\n"
            f"- **Threshold:** 3 consecutive probe failures confirm sustained upstream throttling rather than an isolated burst.\n\n"
            f"### Immediate Mitigation Checklist\n"
            f"1. **Enforce Adaptive Backoff:** Verify that client consumers are respecting `Retry-After` headers with exponential backoff and randomized jitter.\n"
            f"2. **Quota Scaling:** Evaluate if client traffic has legitimately scaled; request a quota increase in API Gateway / Cloud Armor.\n"
            f"3. **Request Coalescing:** Implement Redis caching or deduplication on hot upstream query paths to reduce repetitive requests."
        )

    # 2. HTTP 503 / 502 / 504 - Service Unavailable / Gateway Overload / Pool Starvation
    if status_code in (502, 503, 504) or any(code in trigger_error for code in ("502", "503", "504")):
        is_db_pool = "pool" in (response_snippet or "").lower() or "database" in trigger_error.lower()
        specific_cause = (
            "upstream database connection pool exhaustion"
            if is_db_pool
            else "service unavailability or upstream reverse-proxy gateway overload"
        )
        return (
            f"### Root Cause Diagnosis\n"
            f"The target service `{monitor_name}` triggered an outage due to **HTTP {status_code or 503} (Service Unavailable)**. "
            f"The failure signature indicates **{specific_cause}**, preventing the backend application from servicing HTTP traffic.\n\n"
            f"### Telemetry & Evidence Correlation\n"
            f"- **Target:** `{method} {target_url}`\n"
            f"- **Failure Signature:** `{trigger_error}`{snippet_info}\n"
            f"- **Latency Telemetry:** {latency_summary}\n"
            f"- **Outage Pattern:** Sustained 3-strike failure indicates persistent container degradation, backend process deadlock, or resource starvation.\n\n"
            f"### Immediate Mitigation Checklist\n"
            f"1. **Connection Pool & Worker Health:** Inspect upstream connection pool metrics (`pool_size`, active checkouts, waiting queries) and restart deadlocked instances.\n"
            f"2. **Database Sizing:** Verify PostgreSQL / database CPU utilization, memory pressure, and long-running locks.\n"
            f"3. **Container Health & Auto-Healing:** Check Kubernetes / Docker health probes and trigger rolling replacement of unhealthy pods if connection pool recovery fails."
        )

    # 3. HTTP 500 - Internal Server Error
    if status_code == 500 or "500" in trigger_error:
        return (
            f"### Root Cause Diagnosis\n"
            f"The target service `{monitor_name}` suffered an outage due to unhandled application exceptions (**HTTP 500 Internal Server Error**). "
            f"An unexpected runtime error or unhandled dependency failure caused the application worker to crash during request execution.\n\n"
            f"### Telemetry & Evidence Correlation\n"
            f"- **Target:** `{method} {target_url}`\n"
            f"- **Failure Signature:** `{trigger_error}`{snippet_info}\n"
            f"- **Latency Telemetry:** {latency_summary}\n"
            f"- **Impact Assessment:** 3 consecutive 500 errors confirm recurring systemic failure on endpoint `{target_url}`.\n\n"
            f"### Immediate Mitigation Checklist\n"
            f"1. **Log Inspection:** Search centralized logging (Datadog/Elastic/CloudWatch) for exception tracebacks associated with `{target_url}`.\n"
            f"2. **Recent Release Rollback:** Check recent CI/CD deployments; roll back to previous stable build if regression was introduced.\n"
            f"3. **Dependency Health Check:** Validate health of upstream microservices, caches, and third-party APIs invoked by this route."
        )

    # 4. Timeout / Network Connection Partition
    if "timeout" in trigger_error.lower() or "connect" in trigger_error.lower():
        return (
            f"### Root Cause Diagnosis\n"
            f"The target service `{monitor_name}` experienced a **Timeout / Network Partition**. "
            f"The probe client was unable to establish a connection or receive a response before the timeout deadline.\n\n"
            f"### Telemetry & Evidence Correlation\n"
            f"- **Target:** `{method} {target_url}`\n"
            f"- **Failure Signature:** `{trigger_error}`\n"
            f"- **Latency Telemetry:** {latency_summary}\n"
            f"- **Network State:** Consecutive timeouts suggest the host server is completely unresponsive, frozen, or network routing is blocked.\n\n"
            f"### Immediate Mitigation Checklist\n"
            f"1. **Infrastructure Health:** Check physical host / VM CPU and memory metrics to verify instance responsiveness.\n"
            f"2. **DNS & Ingress Routing:** Validate DNS resolution, SSL certificate validity, and load balancer listeners.\n"
            f"3. **Socket Backlog Saturation:** Check if the web server accept queue / socket backlog is full due to thread starvation."
        )

    # Generic Fallback
    return (
        f"### Root Cause Diagnosis\n"
        f"The target service `{monitor_name}` transitioned to DOWN following 3 consecutive failed probes. "
        f"The endpoint returned unexpected response criteria: `{trigger_error}`.\n\n"
        f"### Telemetry & Evidence Correlation\n"
        f"- **Target:** `{method} {target_url}`\n"
        f"- **Failure Signature:** `{trigger_error}`{snippet_info}\n"
        f"- **Latency Telemetry:** {latency_summary}\n\n"
        f"### Immediate Mitigation Checklist\n"
        f"1. **Validate Endpoint Specification:** Verify the expected HTTP response status code and payload contracts.\n"
        f"2. **Inspect Server Logs:** Review application logs coinciding with the timestamp of the first probe failure.\n"
        f"3. **Trigger Manual Diagnostic:** Execute on-demand probe via API to capture live response telemetry."
    )


async def generate_incident_rca(
    monitor_name: str,
    target_url: str,
    method: str,
    trigger_error: str,
    status_code: Optional[int],
    response_snippet: Optional[str],
    recent_latencies: List[float],
) -> str:
    """
    Dual-Mode AI Root-Cause Analysis Engine:
      - Mode 1: Calls Google Gemini REST API if GEMINI_API_KEY is configured.
      - Mode 2: Deterministic SRE Heuristic Engine (immediate fallback).
    """
    if settings.GEMINI_API_KEY:
        try:
            latency_str = ", ".join(f"{ms}ms" for ms in recent_latencies) if recent_latencies else "N/A"
            prompt = (
                f"You are a Principal Site Reliability Engineer (SRE) analyzing a production outage. "
                f"An automated monitoring platform has detected 3 consecutive failed probes against a critical API endpoint.\n\n"
                f"Incident Telemetry:\n"
                f"- Service/Monitor Name: {monitor_name}\n"
                f"- Target URL: {method} {target_url}\n"
                f"- HTTP Status Code: {status_code or 'None'}\n"
                f"- Failure Signature: {trigger_error}\n"
                f"- Response Snippet: {response_snippet or 'None'}\n"
                f"- Recent Latencies: {latency_str}\n\n"
                f"Provide a concise, professional Root-Cause Analysis (RCA) report formatted with exactly these 3 Markdown headers:\n"
                f"### Root Cause Diagnosis\n"
                f"### Telemetry & Evidence Correlation\n"
                f"### Immediate Mitigation Checklist\n"
                f"Keep each section direct, technical, and actionable for on-call engineers."
            )

            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            )
            payload = {"contents": [{"parts": [{"text": prompt}]}]}

            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_content.strip():
                            logger.info(f"Gemini LLM successfully generated RCA for monitor '{monitor_name}'.")
                            return text_content.strip()
                else:
                    logger.warning(
                        f"Gemini API returned HTTP {res.status_code}: {res.text[:200]}. Falling back to deterministic SRE engine."
                    )
        except Exception as exc:
            logger.warning(
                f"Gemini RCA call failed ({type(exc).__name__}: {exc}). Falling back to deterministic SRE engine."
            )

    # Mode 2: Deterministic SRE Heuristic Engine
    return _generate_deterministic_rca(
        monitor_name=monitor_name,
        target_url=target_url,
        method=method,
        trigger_error=trigger_error,
        status_code=status_code,
        response_snippet=response_snippet,
        recent_latencies=recent_latencies,
    )


async def populate_incident_rca(
    incident_id: uuid.UUID,
    response_snippet: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> Optional[str]:
    """
    Loads incident context, generates a Root-Cause Analysis report via the Dual-Mode Engine,
    persists it into PostgreSQL `incident.rca_summary`, and emits a structured log banner.
    """
    if db is not None:
        return await _execute_populate_rca(db, incident_id, response_snippet)

    async with AsyncSessionLocal() as session:
        return await _execute_populate_rca(session, incident_id, response_snippet)


async def _execute_populate_rca(
    session: AsyncSession,
    incident_id: uuid.UUID,
    response_snippet: Optional[str] = None,
) -> Optional[str]:
    incident = await session.get(Incident, incident_id)
    if not incident:
        logger.error(f"Cannot populate RCA: Incident {incident_id} not found.")
        return None

    monitor = await session.get(Monitor, incident.monitor_id)
    if not monitor:
        logger.error(f"Cannot populate RCA: Monitor {incident.monitor_id} not found.")
        return None

    # Fetch last 10 probe latencies for evidence correlation
    lat_stmt = (
        select(ProbeLog.latency_ms)
        .where(ProbeLog.monitor_id == monitor.id)
        .order_by(desc(ProbeLog.timestamp))
        .limit(10)
    )
    lat_res = await session.execute(lat_stmt)
    recent_latencies = list(lat_res.scalars().all())

    # Extract status code from trigger_error if available (e.g., 'got 503')
    status_code = None
    if incident.trigger_error:
        match = re.search(r"got\s+(\d{3})", incident.trigger_error)
        if match:
            status_code = int(match.group(1))

    rca_report = await generate_incident_rca(
        monitor_name=monitor.name,
        target_url=monitor.url,
        method=monitor.method,
        trigger_error=incident.trigger_error or "Unknown failure",
        status_code=status_code,
        response_snippet=response_snippet,
        recent_latencies=recent_latencies,
    )

    incident.rca_summary = rca_report
    await session.commit()

    logger.warning(
        "\n" + "=" * 65 + "\n"
        f"[AI RCA GENERATED] 🧠 INCIDENT ROOT-CAUSE ANALYSIS\n"
        f"Monitor:    {monitor.name} (ID: {monitor.id})\n"
        f"Incident:   {incident.id}\n"
        f"Trigger:    {incident.trigger_error}\n"
        f"Preview:\n{rca_report[:280]}...\n"
        + "=" * 65
    )

    return rca_report
