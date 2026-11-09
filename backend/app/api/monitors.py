from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Incident, IncidentStatus, Monitor, ProbeLog
from app.schemas.analytics import (
    LatencyTimeseriesPoint,
    MonitorMetricsSummary,
    PlatformOverviewMetrics,
)
from app.schemas.monitor import (
    IncidentResponse,
    MonitorCreate,
    MonitorResponse,
    MonitorUpdate,
    ProbeLogResponse,
)
from app.services.analytics_service import (
    get_monitor_metrics,
    get_monitor_timeseries,
    get_platform_overview,
)
from app.services.prober import execute_probe

router = APIRouter(prefix="/api/v1/monitors", tags=["Monitors"])


@router.post("/", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    payload: MonitorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register and create a new endpoint monitor."""
    monitor = Monitor(
        name=payload.name,
        url=payload.url,
        method=payload.method.upper(),
        interval_seconds=payload.interval_seconds,
        timeout_seconds=payload.timeout_seconds,
        expected_status=payload.expected_status,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return monitor


@router.get("/", response_model=List[MonitorResponse])
async def list_monitors(
    db: AsyncSession = Depends(get_db),
):
    """List all registered monitors."""
    result = await db.execute(select(Monitor).order_by(desc(Monitor.created_at)))
    return result.scalars().all()


@router.get("/incidents/active", response_model=List[IncidentResponse])
async def list_active_incidents(
    db: AsyncSession = Depends(get_db),
):
    """List all currently OPEN incidents across all monitors."""
    stmt = (
        select(Incident)
        .where(Incident.status == IncidentStatus.OPEN)
        .order_by(desc(Incident.started_at))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/overview", response_model=PlatformOverviewMetrics)
async def platform_overview(
    db: AsyncSession = Depends(get_db),
):
    """Retrieve aggregated platform-wide monitor metrics and 24h SLA uptime."""
    return await get_platform_overview(db)


@router.get("/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(
    monitor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve details of a single monitor."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )
    return monitor


@router.patch("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: uuid.UUID,
    payload: MonitorUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update monitor configuration."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "method" and value:
            value = value.upper()
        setattr(monitor, key, value)
    await db.commit()
    await db.refresh(monitor)
    return monitor


@router.get("/{monitor_id}/incidents", response_model=List[IncidentResponse])
async def list_monitor_incidents(
    monitor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all incidents (OPEN and RESOLVED) for a specific monitor."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )

    stmt = (
        select(Incident)
        .where(Incident.monitor_id == monitor_id)
        .order_by(desc(Incident.started_at))
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{monitor_id}/metrics", response_model=MonitorMetricsSummary)
async def monitor_metrics(
    monitor_id: uuid.UUID,
    window_hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve time-series percentiles (P50, P95, P99), latency summary, and SLA uptime."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )
    return await get_monitor_metrics(db, monitor_id, window_hours=window_hours)


@router.get("/{monitor_id}/timeseries", response_model=List[LatencyTimeseriesPoint])
async def monitor_timeseries(
    monitor_id: uuid.UUID,
    window_hours: int = Query(default=1, ge=1, le=168),
    bucket_minutes: int = Query(default=1, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve rolled up time-bucketed latency percentiles and success rates."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )
    return await get_monitor_timeseries(
        db, monitor_id, window_hours=window_hours, bucket_minutes=bucket_minutes
    )


@router.post("/{monitor_id}/probe", response_model=ProbeLogResponse)
async def trigger_manual_probe(
    monitor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an immediate on-demand probe for a monitor."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )

    async with httpx.AsyncClient() as client:
        log = await execute_probe(monitor_id, client)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monitor is inactive or probe execution failed",
        )
    return log


@router.get("/{monitor_id}/logs", response_model=List[ProbeLogResponse])
async def get_monitor_logs(
    monitor_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the latest probe log history for a monitor."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )

    stmt = (
        select(ProbeLog)
        .where(ProbeLog.monitor_id == monitor_id)
        .order_by(desc(ProbeLog.timestamp))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a monitor and its associated probe logs."""
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor with id '{monitor_id}' not found",
        )
    await db.delete(monitor)
    await db.commit()
    return None
