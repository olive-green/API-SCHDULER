import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Schedule, ScheduleStatus, ScheduleType
from app.database import AsyncSessionLocal
from app.services.executor import RequestExecutor

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages APScheduler and job lifecycle"""
    
    def __init__(self):
        # Configure APScheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # Combine multiple pending executions into one
            'max_instances': 1,  # Only one instance of a job runs at a time
            'misfire_grace_time': 60,  # Allow jobs to run up to 60s late
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=settings.scheduler_timezone,
        )
        
        self.executor = RequestExecutor()
        
        # Add event listeners
        self.scheduler.add_listener(
            self._job_executed_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown")
    
    async def load_schedules(self):
        """Load all active schedules from database on startup"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Schedule).filter(Schedule.status == ScheduleStatus.ACTIVE)
            )
            schedules = result.scalars().all()
            
            for schedule in schedules:
                try:
                    await self.add_job(schedule, db)
                    logger.info(f"Loaded schedule {schedule.id}: {schedule.name}")
                except Exception as e:
                    logger.error(f"Failed to load schedule {schedule.id}: {e}", exc_info=True)
    
    async def add_job(self, schedule: Schedule, db: AsyncSession):
        """
        Add a job to the scheduler
        
        Args:
            schedule: Schedule object
            db: Database session
        """
        job_id = f"schedule_{schedule.id}"
        
        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Add job based on schedule type
        if schedule.schedule_type == ScheduleType.INTERVAL:
            # Interval: run indefinitely every N seconds
            self.scheduler.add_job(
                self._execute_job,
                'interval',
                seconds=schedule.interval_seconds,
                args=[schedule.id],
                id=job_id,
                replace_existing=True,
            )
        
        elif schedule.schedule_type == ScheduleType.WINDOW:
            # Window: run every N seconds for M seconds total
            if not schedule.started_at:
                schedule.started_at = datetime.utcnow()
                await db.commit()
            
            end_time = schedule.started_at + timedelta(seconds=schedule.duration_seconds)
            
            # Check if already expired
            if datetime.utcnow() >= end_time:
                schedule.status = ScheduleStatus.STOPPED
                schedule.stopped_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Schedule {schedule.id} window already expired")
                return
            
            self.scheduler.add_job(
                self._execute_job,
                'interval',
                seconds=schedule.interval_seconds,
                args=[schedule.id],
                id=job_id,
                replace_existing=True,
                end_date=end_time,
            )
            
            # Schedule a job to mark the schedule as stopped
            self.scheduler.add_job(
                self._stop_window_schedule,
                'date',
                run_date=end_time,
                args=[schedule.id],
                id=f"{job_id}_stop",
                replace_existing=True,
            )
        
        # Update job_id in database
        schedule.job_id = job_id
        await db.commit()
        
        logger.info(
            f"Added job {job_id} for schedule {schedule.id} "
            f"(type={schedule.schedule_type.value}, interval={schedule.interval_seconds}s)"
        )
    
    async def remove_job(self, schedule: Schedule):
        """Remove a job from the scheduler"""
        if schedule.job_id and self.scheduler.get_job(schedule.job_id):
            self.scheduler.remove_job(schedule.job_id)
            logger.info(f"Removed job {schedule.job_id}")
        
        # Also remove stop job for window schedules
        stop_job_id = f"{schedule.job_id}_stop"
        if self.scheduler.get_job(stop_job_id):
            self.scheduler.remove_job(stop_job_id)
    
    async def pause_job(self, schedule: Schedule):
        """Pause a job"""
        if schedule.job_id and self.scheduler.get_job(schedule.job_id):
            self.scheduler.pause_job(schedule.job_id)
            logger.info(f"Paused job {schedule.job_id}")
    
    async def resume_job(self, schedule: Schedule, db: AsyncSession):
        """Resume a paused job"""
        if schedule.job_id and self.scheduler.get_job(schedule.job_id):
            self.scheduler.resume_job(schedule.job_id)
            logger.info(f"Resumed job {schedule.job_id}")
        else:
            # Job doesn't exist, recreate it
            await self.add_job(schedule, db)
    
    async def _execute_job(self, schedule_id: int):
        """Execute a scheduled job"""
        logger.debug(f"Executing schedule {schedule_id}")
        
        async with AsyncSessionLocal() as db:
            # Check if schedule is still active
            result = await db.execute(
                select(Schedule).filter(Schedule.id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            
            if not schedule:
                logger.warning(f"Schedule {schedule_id} not found, removing job")
                return
            
            if schedule.status != ScheduleStatus.ACTIVE:
                logger.debug(f"Schedule {schedule_id} is not active, skipping")
                return
            
            # Execute the request
            await self.executor.execute_schedule(schedule_id, db)
    
    async def _stop_window_schedule(self, schedule_id: int):
        """Mark a window schedule as stopped"""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Schedule)
                .where(Schedule.id == schedule_id)
                .values(status=ScheduleStatus.STOPPED, stopped_at=datetime.utcnow())
            )
            await db.commit()
            logger.info(f"Window schedule {schedule_id} stopped")
    
    def _job_executed_listener(self, event):
        """Listener for job execution events"""
        if event.exception:
            logger.error(f"Job {event.job_id} raised an exception: {event.exception}")
        else:
            logger.debug(f"Job {event.job_id} executed successfully")


# Global scheduler instance
scheduler_service = SchedulerService()

