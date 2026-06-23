from __future__ import annotations

from typing import AsyncGenerator, List, Optional

import httpx

from app.providers import BaseProvider


class ClaudeProvider(BaseProvider):
    """Provider for Anthropic Claude API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Extract system message and convert to Anthropic message format."""
        system: str | None = None
        converted: list[dict] = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # Anthropic uses a separate system parameter
                system = content if system is None else system + "\n" + content
            elif role == "user":
                converted.append({"role": "user", "content": content})
            elif role == "assistant":
                converted.append({"role": "assistant", "content": content})

        return system, converted

    async def complete(self, messages: list[dict]) -> str:
        system, converted = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": converted,
            "max_tokens": self.max_tokens,
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
            )
            if response.status_code != 200:
                detail = response.text
                raise RuntimeError(
                    f"Claude API request failed: HTTP {response.status_code}: {detail}"
                )
            body = response.json()
            content_blocks = body.get("content", [])
            texts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            return "".join(texts).strip()

    async def complete_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        system, converted = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": converted,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    detail = await response.aread()
                    raise RuntimeError(
                        f"Claude API stream failed: HTTP {response.status_code}: {detail.decode()}"
                    )

                buffer = ""
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line.removeprefix("data: ").strip()
                    if data_str == "[DONE]":
                        break
                    # SSE format: event: content_block_delta\n data: {...}
                    if line.startswith("event: "):
                        buffer = line[len("event: "):]
                        continue

                    import json
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if buffer == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
