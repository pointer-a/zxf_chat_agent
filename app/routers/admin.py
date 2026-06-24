from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Conversation,
    MemoryFact,
    MemorySummary,
    Message,
    Model,
    User,
)
from app.schemas import (
    AdminConversationRow,
    AdminMemoryFactResponse,
    AdminMessageResponse,
    AdminStats,
    AdminUserDetail,
    AdminUserRow,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    user_count = await db.scalar(select(func.count()).select_from(User))
    conversation_count = await db.scalar(select(func.count()).select_from(Conversation))
    message_count = await db.scalar(select(func.count()).select_from(Message))
    memory_fact_count = await db.scalar(select(func.count()).select_from(MemoryFact))

    return AdminStats(
        user_count=user_count or 0,
        conversation_count=conversation_count or 0,
        message_count=message_count or 0,
        memory_fact_count=memory_fact_count or 0,
    )


@router.get("/users", response_model=List[AdminUserRow])
async def list_users(db: AsyncSession = Depends(get_db)):
    """List all users with conversation and memory counts."""
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()

    rows = []
    for user in users:
        conv_count = await db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
        )
        mem_count = await db.scalar(
            select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == user.id)
        )
        rows.append(AdminUserRow(
            id=user.id,
            name=user.name,
            display_name=user.display_name,
            conversation_count=conv_count or 0,
            memory_fact_count=mem_count or 0,
            created_at=user.created_at,
        ))

    return rows


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single user's detail info."""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserDetail(
        id=user.id,
        name=user.name,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.get("/users/{user_id}/conversations", response_model=List[AdminConversationRow])
async def list_user_conversations(user_id: int, db: AsyncSession = Depends(get_db)):
    """List all conversations for a user with message counts."""
    # Verify user exists
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    conv_stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
    )
    conv_result = await db.execute(conv_stmt)
    conversations = conv_result.scalars().all()

    rows = []
    for conv in conversations:
        msg_count = await db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
        )
        model_name = None
        if conv.model_id:
            model_stmt = select(Model).where(Model.id == conv.model_id)
            model_result = await db.execute(model_stmt)
            model = model_result.scalar_one_or_none()
            if model:
                model_name = model.display_name or model.model_name

        rows.append(AdminConversationRow(
            id=conv.id,
            title=conv.title,
            model_name=model_name,
            message_count=msg_count or 0,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ))

    return rows


@router.get("/conversations/{conversation_id}/messages", response_model=List[AdminMessageResponse])
async def get_conversation_messages(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Get all messages in a conversation (oldest first)."""
    conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
    conv_result = await db.execute(conv_stmt)
    if conv_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()

    return [AdminMessageResponse.model_validate(m) for m in messages]


@router.get("/users/{user_id}/memories", response_model=List[AdminMemoryFactResponse])
async def list_user_memories(user_id: int, db: AsyncSession = Depends(get_db)):
    """List all memory facts for a user."""
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    mem_stmt = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id)
        .order_by(desc(MemoryFact.confidence), desc(MemoryFact.updated_at))
    )
    mem_result = await db.execute(mem_stmt)
    facts = mem_result.scalars().all()

    return [AdminMemoryFactResponse.model_validate(f) for f in facts]
