import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Target
from app.schemas import TargetCreate, TargetUpdate, TargetResponse, MessageResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/targets", tags=["targets"])


def parse_target_headers(target: Target) -> Target:
    """Parse headers from JSON string to dict before returning"""
    if target.headers and isinstance(target.headers, str):
        try:
            target.headers = json.loads(target.headers)
        except (json.JSONDecodeError, TypeError):
            target.headers = None
    return target


@router.post("", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
async def create_target(
    target: TargetCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new target"""
    # Check if name already exists
    result = await db.execute(
        select(Target).filter(Target.name == target.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target with name '{target.name}' already exists"
        )
    
    # Create target
    db_target = Target(
        name=target.name,
        url=str(target.url),
        method=target.method,
        headers=json.dumps(target.headers) if target.headers else None,
        body_template=target.body_template,
    )
    
    db.add(db_target)
    await db.commit()
    await db.refresh(db_target)
    
    # Parse headers before returning
    parse_target_headers(db_target)
    
    logger.info(f"Created target {db_target.id}: {db_target.name}")
    return db_target


@router.get("", response_model=List[TargetResponse])
async def list_targets(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all targets"""
    result = await db.execute(
        select(Target).offset(skip).limit(limit)
    )
    targets = result.scalars().all()
    
    # Parse headers for all targets
    for target in targets:
        parse_target_headers(target)
    
    return targets


@router.get("/{target_id}", response_model=TargetResponse)
async def get_target(
    target_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific target"""
    result = await db.execute(
        select(Target).filter(Target.id == target_id)
    )
    target = result.scalar_one_or_none()
    
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target {target_id} not found"
        )
    
    # Parse headers before returning
    parse_target_headers(target)
    
    return target


@router.put("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: int,
    target_update: TargetUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a target"""
    result = await db.execute(
        select(Target).filter(Target.id == target_id)
    )
    target = result.scalar_one_or_none()
    
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target {target_id} not found"
        )
    
    # Update fields
    update_data = target_update.model_dump(exclude_unset=True)
    
    if 'name' in update_data:
        # Check if new name conflicts
        result = await db.execute(
            select(Target).filter(
                Target.name == update_data['name'],
                Target.id != target_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target with name '{update_data['name']}' already exists"
            )
        target.name = update_data['name']
    
    if 'url' in update_data:
        target.url = str(update_data['url'])
    
    if 'method' in update_data:
        target.method = update_data['method']
    
    if 'headers' in update_data:
        target.headers = json.dumps(update_data['headers']) if update_data['headers'] else None
    
    if 'body_template' in update_data:
        target.body_template = update_data['body_template']
    
    await db.commit()
    await db.refresh(target)
    
    # Parse headers before returning
    parse_target_headers(target)
    
    logger.info(f"Updated target {target.id}: {target.name}")
    return target


@router.delete("/{target_id}", response_model=MessageResponse)
async def delete_target(
    target_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a target"""
    result = await db.execute(
        select(Target).filter(Target.id == target_id)
    )
    target = result.scalar_one_or_none()
    
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target {target_id} not found"
        )
    
    await db.delete(target)
    await db.commit()
    
    logger.info(f"Deleted target {target_id}: {target.name}")
    return MessageResponse(message=f"Target {target_id} deleted successfully")

