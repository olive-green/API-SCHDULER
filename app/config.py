from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./scheduler.db"
    
    # Scheduler
    scheduler_timezone: str = "UTC"
    max_concurrent_jobs: int = 100
    
    # HTTP Client
    default_timeout: int = 30  # seconds
    max_retries: int = 0  # No automatic retries by default
    
    # Application
    app_title: str = "API Scheduler"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

