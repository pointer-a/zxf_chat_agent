from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Model as ModelORM
from app.models import Provider as ProviderORM
from app.schemas import ModelDetailResponse, ProviderResponse
from app.services.model_registry import ModelRegistry

router = APIRouter(prefix="/api/models", tags=["models"])


class SetupProviderRequest(BaseModel):
    name: str
    provider_type: str = "openai_compatible"
    api_key: str
    base_url: Optional[str] = None
    models: List[str]


@router.post("/setup", status_code=201)
async def setup_provider(body: SetupProviderRequest, db: AsyncSession = Depends(get_db)):
    """Add a new OpenAI-compatible provider and its models at runtime."""
    if body.provider_type != "openai_compatible":
        raise HTTPException(status_code=400, detail=f"仅支持 openai_compatible 类型")

    provider = ProviderORM(
        name=body.name,
        provider_type="openai_compatible",
        base_url=body.base_url or "",
        api_key=body.api_key,
        is_active=1,
    )
    db.add(provider)
    await db.flush()

    created = []
    for model_name in body.models:
        m = ModelORM(
            provider_id=provider.id,
            model_name=model_name,
            display_name=model_name,
            is_active=1,
        )
        db.add(m)
        created.append(model_name)

    await db.commit()
    await db.refresh(provider)

    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "provider_type": provider.provider_type,
        "models_created": created,
    }


@router.post("/setup/deepseek", status_code=201)
async def setup_deepseek(
    api_key: str,
    base_url: str = "https://api.deepseek.com/v1",
    db: AsyncSession = Depends(get_db),
):
    """一键配置 DeepSeek，注册主流模型。"""
    provider = ProviderORM(
        name="DeepSeek",
        provider_type="openai_compatible",
        base_url=base_url,
        api_key=api_key,
        is_active=1,
    )
    db.add(provider)
    await db.flush()

    models_info = [
        ("deepseek-v4-flash", "DeepSeek v4 Flash"),
        ("deepseek-v4-pro", "DeepSeek v4 Pro"),
    ]
    created = []
    for model_name, display_name in models_info:
        m = ModelORM(
            provider_id=provider.id,
            model_name=model_name,
            display_name=display_name,
            is_active=1,
        )
        db.add(m)
        created.append(model_name)

    await db.commit()
    await db.refresh(provider)

    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "models_created": created,
    }


@router.get("", response_model=List[ModelDetailResponse])
async def list_models(db: AsyncSession = Depends(get_db)):
    """列出所有可用模型及其供应商信息。"""
    registry = ModelRegistry(db)
    models = await registry.get_available_models()
    results = []
    for model in models:
        row = await registry.get_model_with_provider(model.id)
        if row:
            m, p = row
            results.append(ModelDetailResponse(
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
            ))
    return results


@router.get("/providers", response_model=List[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """列出所有供应商。"""
    stmt = select(ProviderORM).where(ProviderORM.is_active == 1)
    result = await db.execute(stmt)
    providers = result.scalars().all()
    return [ProviderResponse.model_validate(p) for p in providers]
