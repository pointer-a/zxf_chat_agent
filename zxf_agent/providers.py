from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


Message = dict[str, str]


class ChatProvider(Protocol):
    def complete(self, messages: list[Message]) -> str:
        ...


@dataclass
class OpenAICompatibleProvider:
    model: str
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.7
    timeout: int = 90

    @classmethod
    def from_env(cls, model: str | None = None) -> "OpenAICompatibleProvider | None":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        return cls(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        )

    def complete(self, messages: list[Message]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

        return body["choices"][0]["message"]["content"].strip()


class OfflineDemoProvider:
    """Small deterministic fallback so the agent can be tried without an API key."""

    def complete(self, messages: list[Message]) -> str:
        system_text = messages[0]["content"] if messages else ""
        user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        prefix = ""
        if "第一次以该视角回答" in system_text:
            prefix = "我以张雪峰视角和你聊，基于公开言论推断，非本人观点。\n\n"

        if any(word in user_text for word in ["退出", "切回正常", "不用扮演"]):
            return "行，切回正常模式。你接着说需求，我按普通助手方式帮你。"

        if any(word in user_text for word in ["高考", "志愿", "专业", "学校", "大学", "考研", "就业", "行业", "薪资"]):
            return (
                prefix
                + "先别急着下结论，这事缺数据就不能瞎整。\n\n"
                + "你先把四个信息给我：多少分或什么学历？哪个省？家里是做什么的？目标城市和能接受的行业是什么？\n\n"
                + "我跟你说，涉及具体专业、学校、行业，就得看就业率、薪资中位数、录取线和普通毕业生去向。没有这些，张嘴就说前景好，那是忽悠普通家庭。"
            )

        return (
            prefix
            + "我跟你说，普通家庭做选择，第一件事不是谈理想，是看这个选择能不能让你站稳。\n\n"
            + "社会就是个筛子。学历筛一遍，城市筛一遍，行业再筛一遍。你手里没资源，就别拿热爱硬扛风险。先谋生，再谋爱；先站稳，再登高。"
        )
