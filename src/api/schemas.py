from typing import Optional
from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    user_id: str
    ip: str
    country: str = "unknown"
    region: str = "unknown"
    city: str = "unknown"
    asn: int = 0
    os_name: str = "unknown"
    os_version: str = ""
    browser_name: str = "unknown"
    browser_version: str = ""
    device_type: str = "unknown"
    timezone: str = "UTC"
    timezone_offset: int = 0
    webgl_renderer: str = ""
    webgl_vendor: str = ""
    login_timestamp: Optional[str] = None
    is_success: bool = True
    store_event: bool = True


class PredictResponse(BaseModel):
    is_anomaly: bool
    risk_score: float
    event_id: Optional[int] = None


class LabelRequest(BaseModel):
    is_attack: bool
    is_account_takeover: bool = False


class TrainRequest(BaseModel):
    start_date: Optional[str] = Field(None, example="2025-01-01T00:00:00")
    end_date: Optional[str] = Field(None, example="2025-06-01T23:59:59")
    recent_days: Optional[int] = Field(None, example=30)
    fine_tune_trees: int = Field(50, ge=10, le=500)


class TrainResponse(BaseModel):
    job_id: str
    status: str
    message: str


class TrainStatusResponse(BaseModel):
    job_id: str
    status: str
    params: Optional[dict] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    active_model: str
    model_loaded: bool
    labeled_events: int
