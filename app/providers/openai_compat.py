from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

import httpx

from app.providers import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    """Provider for any OpenAI-compatible chat API (OpenAI, DeepSeek, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        timeout: int = 90,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    async def complete(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 200:
                    detail = response.text
                    raise RuntimeError(
                        f"LLM request failed: HTTP {response.status_code}: {detail}"
                    )
                body = response.json()
                return body["choices"][0]["message"]["content"].strip()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"无法连接到 LLM 服务 ({self.base_url}): 连接被拒绝或超时") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"LLM 请求超时 ({self.timeout}s): {self.model}") from exc

    async def complete_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    detail = await response.aread()
                    raise RuntimeError(
                        f"LLM stream request failed: HTTP {response.status_code}: {detail.decode()}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line.removeprefix("data: ").strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
