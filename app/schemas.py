from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from app.models import HTTPMethod, ScheduleStatus, ScheduleType, RunStatus



class TargetBase(BaseModel):
    """Base target schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Unique target name")
    url: HttpUrl = Field(..., description="Target URL")
    method: HTTPMethod = Field(default=HTTPMethod.GET, description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(default=None, description="HTTP headers")
    body_template: Optional[str] = Field(default=None, description="Request body template")


class TargetCreate(TargetBase):
    """Schema for creating a target"""
    pass


class TargetUpdate(BaseModel):
    """Schema for updating a target"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[HttpUrl] = None
    method: Optional[HTTPMethod] = None
    headers: Optional[Dict[str, str]] = None
    body_template: Optional[str] = None


class TargetResponse(TargetBase):
    """Schema for target response"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    @model_validator(mode='before')
    @classmethod
    def parse_json_fields(cls, data):
        """Parse JSON string fields back to proper types"""
        # Handle SQLAlchemy model objects
        if hasattr(data, '__dict__'):
            # It's a SQLAlchemy object, modify it directly
            if hasattr(data, 'headers') and isinstance(data.headers, str):
                try:
                    data.headers = json.loads(data.headers) if data.headers else None
                except (json.JSONDecodeError, TypeError):
                    data.headers = None
        # Handle dictionaries
        elif isinstance(data, dict):
            if 'headers' in data and isinstance(data['headers'], str):
                try:
                    data['headers'] = json.loads(data['headers']) if data['headers'] else None
                except (json.JSONDecodeError, TypeError):
                    data['headers'] = None
        return data
    
    class Config:
        from_attributes = True


# ========== Schedule Schemas ==========

class ScheduleBase(BaseModel):
    """Base schedule schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Unique schedule name")
    target_id: int = Field(..., description="Target ID to execute")
    schedule_type: ScheduleType = Field(..., description="Type of schedule")
    interval_seconds: int = Field(..., gt=0, description="Interval in seconds")
    duration_seconds: Optional[int] = Field(None, gt=0, description="Duration in seconds (for WINDOW type)")
    
    @field_validator('duration_seconds')
    @classmethod
    def validate_duration(cls, v, info):
        """Validate duration_seconds is required for WINDOW type"""
        schedule_type = info.data.get('schedule_type')
        if schedule_type == ScheduleType.WINDOW and v is None:
            raise ValueError("duration_seconds is required for WINDOW schedule type")
        return v


class ScheduleCreate(ScheduleBase):
    """Schema for creating a schedule"""
    pass


class ScheduleUpdate(BaseModel):
    """Schema for updating a schedule"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    interval_seconds: Optional[int] = Field(None, gt=0)
    duration_seconds: Optional[int] = Field(None, gt=0)


class ScheduleResponse(ScheduleBase):
    """Schema for schedule response"""
    id: int
    status: ScheduleStatus
    created_at: datetime
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    job_id: Optional[str]
    
    class Config:
        from_attributes = True


# ========== Run Schemas ==========

class AttemptResponse(BaseModel):
    """Schema for attempt response"""
    id: int
    attempt_number: int
    status: RunStatus
    started_at: datetime
    completed_at: Optional[datetime]
    status_code: Optional[int]
    latency_ms: Optional[float]
    error_message: Optional[str]
    error_type: Optional[str]
    
    class Config:
        from_attributes = True


class RunResponse(BaseModel):
    """Schema for run response"""
    id: int
    schedule_id: int
    status: RunStatus
    started_at: datetime
    completed_at: Optional[datetime]
    status_code: Optional[int]
    latency_ms: Optional[float]
    response_size_bytes: Optional[int]
    error_message: Optional[str]
    error_type: Optional[str]
    request_url: str
    request_method: str
    
    class Config:
        from_attributes = True


class RunDetailResponse(RunResponse):
    """Schema for detailed run response with attempts"""
    request_headers: Optional[str]
    request_body: Optional[str]
    response_headers: Optional[str]
    response_body: Optional[str]
    attempts: List[AttemptResponse] = []
    
    class Config:
        from_attributes = True


# ========== Metrics Schemas ==========

class ScheduleMetrics(BaseModel):
    """Metrics for a specific schedule"""
    schedule_id: int
    schedule_name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    avg_latency_ms: Optional[float]
    last_run_at: Optional[datetime]


class SystemMetrics(BaseModel):
    """Overall system metrics"""
    total_targets: int
    total_schedules: int
    active_schedules: int
    paused_schedules: int
    stopped_schedules: int
    total_runs: int
    runs_last_hour: int
    success_rate: float
    avg_latency_ms: Optional[float]


# ========== Common Schemas ==========

class MessageResponse(BaseModel):
    """Generic message response"""
    message: str


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str

