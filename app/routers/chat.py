from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, Message, Model, User, UserModelPref
from app.providers import BaseProvider
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationSetModel,
    ConversationWithModelResponse,
    MessageResponse,
    ModelDetailResponse,
    ProviderResponse,
)
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.memory_service import MemoryService
from app.services.model_registry import ModelRegistry

router = APIRouter(prefix="/api/conversations", tags=["chat"])


async def _get_user(user_id: int, db: AsyncSession) -> User:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _resolve_provider(
    user_id: int,
    conversation: Conversation,
    db: AsyncSession,
) -> BaseProvider:
    """Resolve which provider to use for this conversation."""
    registry = ModelRegistry(db)
    model_id = conversation.model_id

    if model_id is None:
        # Try user default
        pref_stmt = (
            select(UserModelPref)
            .where(UserModelPref.user_id == user_id, UserModelPref.is_default == 1)
        )
        result = await db.execute(pref_stmt)
        pref = result.scalar_one_or_none()
        if pref:
            model_id = pref.model_id

    if model_id:
        try:
            return await registry.create_provider(model_id)
        except ValueError:
            pass

    # Fallback to default
    return await registry.get_default_provider()


# ── List conversations ──

@router.get("", response_model=List[ConversationWithModelResponse])
async def list_conversations(
    user_id: int = Query(..., description="User ID"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for a user."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    responses = []
    for conv in conversations:
        model_detail = None
        if conv.model_id:
            registry = ModelRegistry(db)
            row = await registry.get_model_with_provider(conv.model_id)
            if row:
                m, p = row
                model_detail = ModelDetailResponse(
                    id=m.id,
                    model_name=m.model_name,
                    display_name=m.display_name or m.model_name,
                    provider=ProviderResponse(
                        id=p.id,
                        name=p.name,
                        provider_type=p.provider_type,
                        base_url=p.base_url,
                        is_active=bool(p.is_active),
                    ),
                )
        responses.append(ConversationWithModelResponse(
            id=conv.id,
            user_id=conv.user_id,
            model_id=conv.model_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            model=model_detail,
        ))
    return responses


# ── Create conversation ──

@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    await _get_user(user_id, db)

    conv = Conversation(
        user_id=user_id,
        model_id=body.model_id,
        title=body.title,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


# ── Get conversation ──

@router.get("/{conversation_id}", response_model=ConversationWithModelResponse)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get conversation details."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    model_detail = None
    if conv.model_id:
        registry = ModelRegistry(db)
        row = await registry.get_model_with_provider(conv.model_id)
        if row:
            m, p = row
            model_detail = ModelDetailResponse(
                id=m.id,
                model_name=m.model_name,
                display_name=m.display_name or m.model_name,
                provider=ProviderResponse(
                    id=p.id,
                    name=p.name,
                    provider_type=p.provider_type,
                    base_url=p.base_url,
                    is_active=bool(p.is_active),
                ),
            )

    return ConversationWithModelResponse(
        id=conv.id,
        user_id=conv.user_id,
        model_id=conv.model_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        model=model_detail,
    )


# ── Get messages ──

@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: int,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get messages in a conversation."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = list(reversed(result.scalars().all()))
    return [MessageResponse.model_validate(m) for m in messages]


# ── Chat (send message) ──

@router.post("/{conversation_id}/chat", response_model=ChatResponse)
async def chat(
    conversation_id: int,
    body: ChatRequest,
    user_id: int = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and get an AI response."""
    # Get conversation
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your conversation")

    # Resolve provider
    provider = await _resolve_provider(user_id, conversation, db)

    # Save user message immediately so it persists even if LLM fails
    from app.models import Message as MessageORM
    user_msg = MessageORM(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
    )
    db.add(user_msg)
    await db.commit()

    # Create memory service (use same provider for memory extraction)
    memory_service = MemoryService(db, provider)

    # Create orchestrator
    orchestrator = ChatOrchestrator(db, provider, memory_service)

    # Process message (orchestrator will skip saving user msg)
    try:
        assistant_msg, memories_updated = await orchestrator.process_message(
            conversation_id,
            body.content,
            skip_save_user=True,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ChatResponse(
        message=MessageResponse.model_validate(assistant_msg),
        memories_updated=memories_updated,
    )


# ── Set conversation model ──

@router.put("/{conversation_id}/model", response_model=ConversationResponse)
async def set_conversation_model(
    conversation_id: int,
    body: ConversationSetModel,
    db: AsyncSession = Depends(get_db),
):
    """Switch the model used for a conversation."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify model exists
    model_stmt = select(Model).where(Model.id == body.model_id, Model.is_active == 1)
    model_result = await db.execute(model_stmt)
    model = model_result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found or inactive")

    conversation.model_id = body.model_id
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)
