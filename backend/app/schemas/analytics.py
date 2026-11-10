from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict


class MonitorMetricsSummary(BaseModel):
    monitor_id: uuid.UUID
    window_hours: int
    total_probes: int
    successful_probes: int
    failed_probes: int
    uptime_percentage: float
    avg_latency_ms: Optional[float] = None
    min_latency_ms: Optional[float] = None
    max_latency_ms: Optional[float] = None
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    anomaly_count_24h: int = 0

    model_config = ConfigDict(from_attributes=True)


class LatencyTimeseriesPoint(BaseModel):
    bucket_time: datetime
    probe_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    success_rate: float

    model_config = ConfigDict(from_attributes=True)


class PlatformOverviewMetrics(BaseModel):
    total_monitors: int
    healthy_monitors: int
    degraded_monitors: int
    down_monitors: int
    open_incidents_count: int
    overall_uptime_24h: float
    anomaly_count_24h: int = 0

    model_config = ConfigDict(from_attributes=True)

