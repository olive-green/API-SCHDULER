import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Schedule, Target, ScheduleStatus
from app.schemas import ScheduleCreate, ScheduleUpdate, ScheduleResponse, MessageResponse
from app.scheduler import scheduler_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule: ScheduleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new schedule"""
    # Check if name already exists
    result = await db.execute(
        select(Schedule).filter(Schedule.name == schedule.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schedule with name '{schedule.name}' already exists"
        )
    
    # Check if target exists
    result = await db.execute(
        select(Target).filter(Target.id == schedule.target_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target {schedule.target_id} not found"
        )
    
    # Create schedule
    db_schedule = Schedule(
        name=schedule.name,
        target_id=schedule.target_id,
        schedule_type=schedule.schedule_type,
        interval_seconds=schedule.interval_seconds,
        duration_seconds=schedule.duration_seconds,
        status=ScheduleStatus.ACTIVE,
    )
    
    db.add(db_schedule)
    await db.commit()
    await db.refresh(db_schedule)
    
    # Add to scheduler
    try:
        await scheduler_service.add_job(db_schedule, db)
        logger.info(f"Created schedule {db_schedule.id}: {db_schedule.name}")
    except Exception as e:
        logger.error(f"Failed to add job for schedule {db_schedule.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule job: {str(e)}"
        )
    
    return db_schedule


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(
    status_filter: ScheduleStatus = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all schedules"""
    query = select(Schedule)
    
    if status_filter:
        query = query.filter(Schedule.status == status_filter)
    
    result = await db.execute(query.offset(skip).limit(limit))
    schedules = result.scalars().all()
    return schedules


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific schedule"""
    result = await db.execute(
        select(Schedule).filter(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    
    return schedule


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    schedule_update: ScheduleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a schedule"""
    result = await db.execute(
        select(Schedule).filter(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    
    # Update fields
    update_data = schedule_update.model_dump(exclude_unset=True)
    
    if 'name' in update_data:
        # Check if new name conflicts
        result = await db.execute(
            select(Schedule).filter(
                Schedule.name == update_data['name'],
                Schedule.id != schedule_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Schedule with name '{update_data['name']}' already exists"
            )
        schedule.name = update_data['name']
    
    if 'interval_seconds' in update_data:
        schedule.interval_seconds = update_data['interval_seconds']
    
    if 'duration_seconds' in update_data:
        schedule.duration_seconds = update_data['duration_seconds']
    
    await db.commit()
    await db.refresh(schedule)
    
    # Update scheduler if active
    if schedule.status == ScheduleStatus.ACTIVE:
        try:
            await scheduler_service.add_job(schedule, db)
            logger.info(f"Updated schedule {schedule.id}: {schedule.name}")
        except Exception as e:
            logger.error(f"Failed to update job for schedule {schedule.id}: {e}")
    
    return schedule


@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Pause a schedule"""
    result = await db.execute(
        select(Schedule).filter(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    
    if schedule.status != ScheduleStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schedule is not active (current status: {schedule.status.value})"
        )
    
    schedule.status = ScheduleStatus.PAUSED
    await db.commit()
    await db.refresh(schedule)
    
    # Pause in scheduler
    await scheduler_service.pause_job(schedule)
    
    logger.info(f"Paused schedule {schedule.id}: {schedule.name}")
    return schedule


@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Resume a paused schedule"""
    result = await db.execute(
        select(Schedule).filter(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    
    if schedule.status != ScheduleStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schedule is not paused (current status: {schedule.status.value})"
        )
    
    schedule.status = ScheduleStatus.ACTIVE
    await db.commit()
    await db.refresh(schedule)
    
    # Resume in scheduler
    await scheduler_service.resume_job(schedule, db)
    
    logger.info(f"Resumed schedule {schedule.id}: {schedule.name}")
    return schedule


@router.delete("/{schedule_id}", response_model=MessageResponse)
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a schedule"""
    result = await db.execute(
        select(Schedule).filter(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found"
        )
    
    # Remove from scheduler
    await scheduler_service.remove_job(schedule)
    
    await db.delete(schedule)
    await db.commit()
    
    logger.info(f"Deleted schedule {schedule_id}: {schedule.name}")
    return MessageResponse(message=f"Schedule {schedule_id} deleted successfully")

