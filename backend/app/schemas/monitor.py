from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.models.models import IncidentStatus, MonitorStatus


class MonitorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Monitor name")
    url: str = Field(..., min_length=1, max_length=2048, description="Target URL")
    method: str = Field(default="GET", max_length=10, description="HTTP Method")
    interval_seconds: int = Field(
        default=30, ge=5, le=3600, description="Probe interval in seconds"
    )
    timeout_seconds: float = Field(
        default=10.0, ge=1.0, le=60.0, description="Probe timeout in seconds"
    )
    expected_status: int = Field(
        default=200, ge=100, le=599, description="Expected HTTP response status"
    )


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    method: Optional[str] = Field(default=None, max_length=10)
    interval_seconds: Optional[int] = Field(default=None, ge=5, le=3600)
    timeout_seconds: Optional[float] = Field(default=None, ge=1.0, le=60.0)
    expected_status: Optional[int] = Field(default=None, ge=100, le=599)
    is_active: Optional[bool] = None


class ProbeLogResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    timestamp: datetime
    status_code: Optional[int] = None
    latency_ms: float
    is_success: bool
    error_message: Optional[str] = None
    is_anomaly: bool = False
    anomaly_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class MonitorResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: float
    expected_status: int
    current_status: MonitorStatus
    consecutive_failures: int = 0
    is_active: bool
    last_checked_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    status: IncidentStatus
    started_at: datetime
    resolved_at: Optional[datetime] = None
    failure_count: int = 3
    trigger_error: Optional[str] = None
    rca_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
