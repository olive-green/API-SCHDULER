import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import Run, RunStatus
from app.schemas import RunResponse, RunDetailResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=List[RunResponse])
async def list_runs(
    schedule_id: Optional[int] = Query(None, description="Filter by schedule ID"),
    status_filter: Optional[RunStatus] = Query(None, description="Filter by status"),
    start_time: Optional[datetime] = Query(None, description="Filter runs after this time"),
    end_time: Optional[datetime] = Query(None, description="Filter runs before this time"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """
    List runs with optional filters
    
    - **schedule_id**: Filter by schedule
    - **status**: Filter by run status
    - **start_time**: Only show runs after this timestamp
    - **end_time**: Only show runs before this timestamp
    """
    query = select(Run)
    
    filters = []
    if schedule_id is not None:
        filters.append(Run.schedule_id == schedule_id)
    
    if status_filter is not None:
        filters.append(Run.status == status_filter)
    
    if start_time is not None:
        filters.append(Run.started_at >= start_time)
    
    if end_time is not None:
        filters.append(Run.started_at <= end_time)
    
    if filters:
        query = query.filter(and_(*filters))
    
    query = query.order_by(Run.started_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return runs


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific run, including all attempts
    """
    result = await db.execute(
        select(Run)
        .options(selectinload(Run.attempts))
        .filter(Run.id == run_id)
    )
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found"
        )
    
    return run

