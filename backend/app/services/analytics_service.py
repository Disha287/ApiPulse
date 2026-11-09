from typing import List
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.analytics import (
    LatencyTimeseriesPoint,
    MonitorMetricsSummary,
    PlatformOverviewMetrics,
)


async def get_monitor_metrics(
    db: AsyncSession,
    monitor_id: uuid.UUID,
    window_hours: int = 24,
) -> MonitorMetricsSummary:
    """
    Computes time-series percentiles (P50, P95, P99), latency min/avg/max,
    and SLA uptime percentage for a given monitor in a single optimized SQL query.
    """
    query = text(
        """
        SELECT
            COUNT(*)::int AS total_probes,
            COUNT(*) FILTER (WHERE is_success = true)::int AS successful_probes,
            COUNT(*) FILTER (WHERE is_success = false)::int AS failed_probes,
            AVG(latency_ms) AS avg_latency_ms,
            MIN(latency_ms) AS min_latency_ms,
            MAX(latency_ms) AS max_latency_ms,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency_ms
        FROM probe_logs
        WHERE monitor_id = :monitor_id
          AND timestamp >= NOW() - (:window_hours * INTERVAL '1 hour')
        """
    )

    result = await db.execute(
        query, {"monitor_id": monitor_id, "window_hours": window_hours}
    )
    row = result.mappings().one()

    total_probes = row["total_probes"] or 0
    successful_probes = row["successful_probes"] or 0
    failed_probes = row["failed_probes"] or 0

    if total_probes > 0:
        uptime_percentage = round((successful_probes / total_probes) * 100.0, 2)
    else:
        uptime_percentage = 100.0

    return MonitorMetricsSummary(
        monitor_id=monitor_id,
        window_hours=window_hours,
        total_probes=total_probes,
        successful_probes=successful_probes,
        failed_probes=failed_probes,
        uptime_percentage=uptime_percentage,
        avg_latency_ms=round(row["avg_latency_ms"], 2)
        if row["avg_latency_ms"] is not None
        else None,
        min_latency_ms=round(row["min_latency_ms"], 2)
        if row["min_latency_ms"] is not None
        else None,
        max_latency_ms=round(row["max_latency_ms"], 2)
        if row["max_latency_ms"] is not None
        else None,
        p50_latency_ms=round(row["p50_latency_ms"], 2)
        if row["p50_latency_ms"] is not None
        else None,
        p95_latency_ms=round(row["p95_latency_ms"], 2)
        if row["p95_latency_ms"] is not None
        else None,
        p99_latency_ms=round(row["p99_latency_ms"], 2)
        if row["p99_latency_ms"] is not None
        else None,
    )


async def get_monitor_timeseries(
    db: AsyncSession,
    monitor_id: uuid.UUID,
    window_hours: int = 1,
    bucket_minutes: int = 1,
) -> List[LatencyTimeseriesPoint]:
    """
    Rolls up probe logs into fixed-size time buckets within window_hours,
    calculating bucket probe count, average latency, P95/P99 latency, and success rate.
    """
    bucket_seconds = bucket_minutes * 60

    query = text(
        """
        SELECT
            to_timestamp(floor(extract(epoch from timestamp) / :bucket_seconds) * :bucket_seconds) AS bucket_time,
            COUNT(*)::int AS probe_count,
            ROUND(AVG(latency_ms)::numeric, 2)::float AS avg_latency_ms,
            ROUND((PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2)::float AS p95_latency_ms,
            ROUND((PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms))::numeric, 2)::float AS p99_latency_ms,
            ROUND((COUNT(*) FILTER (WHERE is_success = true)::numeric / NULLIF(COUNT(*), 0)) * 100.0, 2)::float AS success_rate
        FROM probe_logs
        WHERE monitor_id = :monitor_id
          AND timestamp >= NOW() - (:window_hours * INTERVAL '1 hour')
        GROUP BY bucket_time
        ORDER BY bucket_time ASC
        """
    )

    result = await db.execute(
        query,
        {
            "monitor_id": monitor_id,
            "window_hours": window_hours,
            "bucket_seconds": bucket_seconds,
        },
    )
    rows = result.mappings().all()

    points: List[LatencyTimeseriesPoint] = []
    for r in rows:
        points.append(
            LatencyTimeseriesPoint(
                bucket_time=r["bucket_time"],
                probe_count=r["probe_count"],
                avg_latency_ms=r["avg_latency_ms"] or 0.0,
                p95_latency_ms=r["p95_latency_ms"] or 0.0,
                p99_latency_ms=r["p99_latency_ms"] or 0.0,
                success_rate=r["success_rate"]
                if r["success_rate"] is not None
                else 100.0,
            )
        )
    return points


async def get_platform_overview(
    db: AsyncSession,
) -> PlatformOverviewMetrics:
    """
    Computes platform-wide observability metrics: monitor status distributions,
    active open incidents, and 24h global probe uptime.
    """
    # 1. Monitor status counts
    monitor_stmt = text(
        """
        SELECT
            COUNT(*)::int AS total_monitors,
            COUNT(*) FILTER (WHERE current_status = 'HEALTHY')::int AS healthy_monitors,
            COUNT(*) FILTER (WHERE current_status = 'DEGRADED')::int AS degraded_monitors,
            COUNT(*) FILTER (WHERE current_status = 'DOWN')::int AS down_monitors
        FROM monitors
        """
    )
    monitor_res = await db.execute(monitor_stmt)
    m_row = monitor_res.mappings().one()

    # 2. Open incidents count
    incident_stmt = text(
        """
        SELECT COUNT(*)::int AS open_incidents_count
        FROM incidents
        WHERE status = 'OPEN'
        """
    )
    incident_res = await db.execute(incident_stmt)
    inc_row = incident_res.mappings().one()

    # 3. Overall 24-hour uptime percentage across all probes
    uptime_stmt = text(
        """
        SELECT
            COUNT(*)::int AS total_probes,
            COUNT(*) FILTER (WHERE is_success = true)::int AS successful_probes
        FROM probe_logs
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
        """
    )
    uptime_res = await db.execute(uptime_stmt)
    up_row = uptime_res.mappings().one()

    total_probes = up_row["total_probes"] or 0
    successful_probes = up_row["successful_probes"] or 0

    if total_probes > 0:
        overall_uptime_24h = round((successful_probes / total_probes) * 100.0, 2)
    else:
        overall_uptime_24h = 100.0

    return PlatformOverviewMetrics(
        total_monitors=m_row["total_monitors"] or 0,
        healthy_monitors=m_row["healthy_monitors"] or 0,
        degraded_monitors=m_row["degraded_monitors"] or 0,
        down_monitors=m_row["down_monitors"] or 0,
        open_incidents_count=inc_row["open_incidents_count"] or 0,
        overall_uptime_24h=overall_uptime_24h,
    )

