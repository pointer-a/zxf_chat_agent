from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Model, Provider
from app.providers import BaseProvider
from app.providers.openai_compat import OpenAICompatibleProvider


class ModelRegistry:
    """Manages model providers and their lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_available_models(self) -> List[Model]:
        stmt = select(Model).where(Model.is_active == 1)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_model_with_provider(self, model_id: int) -> Optional[tuple[Model, Provider]]:
        stmt = select(Model, Provider).join(Provider, Model.provider_id == Provider.id).where(
            Model.id == model_id,
            Model.is_active == 1,
            Provider.is_active == 1,
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        return row if row is None else (row[0], row[1])

    async def create_provider(self, model_id: int) -> BaseProvider:
        """Create a provider instance for the given model ID."""
        row = await self.get_model_with_provider(model_id)
        if row is None:
            raise ValueError(f"Model {model_id} is not active or not found")
        model, provider = row
        return self._build_provider(model, provider)

    async def get_default_provider(self) -> BaseProvider:
        """Return a provider for the first active model, or build from env config."""
        models = await self.get_available_models()
        if models:
            return await self.create_provider(models[0].id)

        if settings.deepseek_api_key:
            return OpenAICompatibleProvider(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")

    def _build_provider(self, model: Model, provider: Provider) -> BaseProvider:
        ptype = provider.provider_type
        if ptype == "openai_compatible":
            api_key = provider.api_key or settings.deepseek_api_key
            base_url = provider.base_url or settings.deepseek_base_url
            return OpenAICompatibleProvider(
                model=model.model_name,
                api_key=api_key,
                base_url=base_url,
            )
        else:
            raise ValueError(f"Unsupported provider type: {ptype}")
