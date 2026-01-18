from sqlalchemy import (
    Column, Integer, String, DateTime, Float, 
    Boolean, Text, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class HTTPMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ScheduleStatus(str, enum.Enum):
    """Schedule status"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"  # Stopped due to window expiry


class ScheduleType(str, enum.Enum):
    """Schedule type"""
    INTERVAL = "INTERVAL"  # Run every N seconds
    WINDOW = "WINDOW"  # Run for N seconds then stop


class RunStatus(str, enum.Enum):
    """Run execution status"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    DNS_ERROR = "DNS_ERROR"
    CONNECTION_ERROR = "CONNECTION_ERROR"


class Target(Base):
    """HTTP target configuration"""
    __tablename__ = "targets"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    url = Column(String(2048), nullable=False)
    method = Column(SQLEnum(HTTPMethod), default=HTTPMethod.GET, nullable=False)
    headers = Column(Text, nullable=True)  # JSON string
    body_template = Column(Text, nullable=True)  # JSON string or plain text
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    schedules = relationship("Schedule", back_populates="target", cascade="all, delete-orphan")


class Schedule(Base):
    """Schedule configuration"""
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False)
    
    # Schedule configuration
    schedule_type = Column(SQLEnum(ScheduleType), nullable=False)
    interval_seconds = Column(Integer, nullable=False)  # How often to run
    duration_seconds = Column(Integer, nullable=True)  # For WINDOW type: how long to run
    
    # Status
    status = Column(SQLEnum(ScheduleStatus), default=ScheduleStatus.ACTIVE, nullable=False)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # When it actually started running
    stopped_at = Column(DateTime, nullable=True)  # When it stopped (for WINDOW type)
    
    # APScheduler job id
    job_id = Column(String(255), nullable=True, unique=True)
    
    # Relationships
    target = relationship("Target", back_populates="schedules")
    runs = relationship("Run", back_populates="schedule", cascade="all, delete-orphan")


class Run(Base):
    """Individual execution of a schedule"""
    __tablename__ = "runs"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Execution details
    status = Column(SQLEnum(RunStatus), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    # HTTP details
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)
    
    # Error details
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)  # timeout, dns, connection, http_error
    
    # Request snapshot
    request_url = Column(String(2048), nullable=False)
    request_method = Column(String(10), nullable=False)
    request_headers = Column(Text, nullable=True)
    request_body = Column(Text, nullable=True)
    
    # Response snapshot (optional, can be large)
    response_headers = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)  # Consider truncating large responses
    
    # Relationships
    schedule = relationship("Schedule", back_populates="runs")
    attempts = relationship("Attempt", back_populates="run", cascade="all, delete-orphan")


class Attempt(Base):
    """Individual attempt within a run (for retries)"""
    __tablename__ = "attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)  # 1, 2, 3...
    
    status = Column(SQLEnum(RunStatus), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)
    
    # Relationships
    run = relationship("Run", back_populates="attempts")

