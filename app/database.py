from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    from app.models import (  # noqa: F401 — ensure models are imported before create_all
        Base,
        Conversation,
        MemoryFact,
        MemorySummary,
        Message,
        Model,
        Provider,
        User,
        UserModelPref,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
