import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.scheduler import scheduler_service
from app.api import targets, schedules, runs, metrics

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scheduler.log')
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    Ensures graceful handling of server restarts
    """
    # Startup
    logger.info("Starting API Scheduler...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Start scheduler
    scheduler_service.start()
    logger.info("Scheduler started")
    
    # Load existing schedules from database
    await scheduler_service.load_schedules()
    logger.info("Existing schedules loaded")
    
    logger.info("API Scheduler is ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Scheduler...")
    scheduler_service.shutdown()
    logger.info("Scheduler stopped")
    logger.info("API Scheduler shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="""
    API Scheduler - A cron-like service for scheduling HTTP requests
    
    ## Features
    
    * **Targets**: Define HTTP endpoints with method, headers, and body templates
    * **Schedules**: Create interval-based or window-based schedules
    * **Runs**: Track execution history with detailed metrics
    * **Metrics**: Monitor system health and performance
    
    ## Scheduling Types
    
    * **INTERVAL**: Run indefinitely every N seconds
    * **WINDOW**: Run every N seconds for M seconds, then automatically stop
    
    ## Observability
    
    * Request/response tracking
    * Error classification (timeout, DNS, connection, HTTP errors)
    * Latency and response size metrics
    * Success rate monitoring
    """,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(targets.router)
app.include_router(schedules.router)
app.include_router(runs.router)
app.include_router(metrics.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "API Scheduler",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "scheduler_running": scheduler_service.scheduler.running,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )

