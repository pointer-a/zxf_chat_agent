from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List


class BaseProvider(ABC):
    """Abstract base class for all LLM providers."""

    model: str

    @abstractmethod
    async def complete(self, messages: list[dict]) -> str:
        """Send a chat completion request and return the full response text."""
        ...

    async def complete_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Optional streaming support. Default yields the full response at once."""
        yield await self.complete(messages)
