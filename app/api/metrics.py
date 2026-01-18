import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import List

from app.database import get_db
from app.models import Target, Schedule, Run, ScheduleStatus, RunStatus
from app.schemas import SystemMetrics, ScheduleMetrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=SystemMetrics)
async def get_system_metrics(
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall system metrics
    """
    # Count targets
    result = await db.execute(select(func.count(Target.id)))
    total_targets = result.scalar_one()
    
    # Count schedules by status
    result = await db.execute(select(func.count(Schedule.id)))
    total_schedules = result.scalar_one()
    
    result = await db.execute(
        select(func.count(Schedule.id))
        .filter(Schedule.status == ScheduleStatus.ACTIVE)
    )
    active_schedules = result.scalar_one()
    
    result = await db.execute(
        select(func.count(Schedule.id))
        .filter(Schedule.status == ScheduleStatus.PAUSED)
    )
    paused_schedules = result.scalar_one()
    
    result = await db.execute(
        select(func.count(Schedule.id))
        .filter(Schedule.status == ScheduleStatus.STOPPED)
    )
    stopped_schedules = result.scalar_one()
    
    # Count runs
    result = await db.execute(select(func.count(Run.id)))
    total_runs = result.scalar_one()
    
    # Runs in last hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    result = await db.execute(
        select(func.count(Run.id))
        .filter(Run.started_at >= one_hour_ago)
    )
    runs_last_hour = result.scalar_one()
    
    # Success rate
    result = await db.execute(
        select(func.count(Run.id))
        .filter(Run.status == RunStatus.SUCCESS)
    )
    successful_runs = result.scalar_one()
    
    success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0.0
    
    # Average latency
    result = await db.execute(
        select(func.avg(Run.latency_ms))
        .filter(Run.latency_ms.isnot(None))
    )
    avg_latency = result.scalar_one()
    
    return SystemMetrics(
        total_targets=total_targets,
        total_schedules=total_schedules,
        active_schedules=active_schedules,
        paused_schedules=paused_schedules,
        stopped_schedules=stopped_schedules,
        total_runs=total_runs,
        runs_last_hour=runs_last_hour,
        success_rate=round(success_rate, 2),
        avg_latency_ms=round(avg_latency, 2) if avg_latency else None,
    )


@router.get("/schedules", response_model=List[ScheduleMetrics])
async def get_schedule_metrics(
    db: AsyncSession = Depends(get_db)
):
    """
    Get metrics for each schedule
    """
    # Get all schedules
    result = await db.execute(select(Schedule))
    schedules = result.scalars().all()
    
    metrics = []
    
    for schedule in schedules:
        # Count runs
        result = await db.execute(
            select(func.count(Run.id))
            .filter(Run.schedule_id == schedule.id)
        )
        total_runs = result.scalar_one()
        
        # Count successful runs
        result = await db.execute(
            select(func.count(Run.id))
            .filter(Run.schedule_id == schedule.id, Run.status == RunStatus.SUCCESS)
        )
        successful_runs = result.scalar_one()
        
        # Count failed runs
        failed_runs = total_runs - successful_runs
        
        # Average latency
        result = await db.execute(
            select(func.avg(Run.latency_ms))
            .filter(Run.schedule_id == schedule.id, Run.latency_ms.isnot(None))
        )
        avg_latency = result.scalar_one()
        
        # Last run time
        result = await db.execute(
            select(func.max(Run.started_at))
            .filter(Run.schedule_id == schedule.id)
        )
        last_run_at = result.scalar_one()
        
        metrics.append(ScheduleMetrics(
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            total_runs=total_runs,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            avg_latency_ms=round(avg_latency, 2) if avg_latency else None,
            last_run_at=last_run_at,
        ))
    
    return metrics

