from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MemoryFact, MemorySummary
from app.schemas import MemoryFactResponse, MemorySummaryResponse

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("/facts", response_model=List[MemoryFactResponse])
async def list_facts(
    user_id: int = Query(..., description="User ID"),
    category: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List memory facts for a user."""
    stmt = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id)
        .order_by(desc(MemoryFact.confidence), desc(MemoryFact.updated_at))
    )
    if category:
        stmt = stmt.where(MemoryFact.category == category)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    facts = result.scalars().all()
    return [MemoryFactResponse.model_validate(f) for f in facts]


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a memory fact."""
    stmt = select(MemoryFact).where(MemoryFact.id == fact_id)
    result = await db.execute(stmt)
    fact = result.scalar_one_or_none()
    if fact is None:
        raise HTTPException(status_code=404, detail="Memory fact not found")
    await db.delete(fact)
    await db.commit()


@router.get("/summary", response_model=Optional[MemorySummaryResponse])
async def get_summary(
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest user summary."""
    stmt = (
        select(MemorySummary)
        .where(MemorySummary.user_id == user_id)
        .order_by(desc(MemorySummary.version))
        .limit(1)
    )
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()
    if summary is None:
        return None
    return MemorySummaryResponse.model_validate(summary)
