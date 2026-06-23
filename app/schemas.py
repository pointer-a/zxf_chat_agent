from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ── User ──

class UserCreate(BaseModel):
    name: str


class UserResponse(BaseModel):
    id: int
    name: str
    display_name: Optional[str] = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class UserLoginResponse(BaseModel):
    user: UserResponse
    is_new: bool
    token: str  # simple user_id-based token for now


# ── Provider & Model ──

class ProviderResponse(BaseModel):
    id: int
    name: str
    provider_type: str
    base_url: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ModelResponse(BaseModel):
    id: int
    provider_id: int
    model_name: str
    display_name: Optional[str] = None
    capabilities: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ModelDetailResponse(BaseModel):
    id: int
    model_name: str
    display_name: Optional[str] = None
    provider: ProviderResponse

    model_config = ConfigDict(from_attributes=True)


# ── Conversation ──

class ConversationCreate(BaseModel):
    title: Optional[str] = None
    model_id: Optional[int] = None


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    model_id: Optional[int] = None
    title: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationWithModelResponse(BaseModel):
    id: int
    user_id: int
    model_id: Optional[int] = None
    title: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model: Optional[ModelDetailResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationSetModel(BaseModel):
    model_id: int


# ── Message ──

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    content: str


class ChatResponse(BaseModel):
    message: MessageResponse
    memories_updated: bool = False


# ── Memory ──

class MemoryFactResponse(BaseModel):
    id: int
    content: str
    category: Optional[str] = None
    confidence: float
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class MemorySummaryResponse(BaseModel):
    id: int
    summary: str
    version: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
