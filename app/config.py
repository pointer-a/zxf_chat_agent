from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_VAR_RE = re.compile(r"\$([A-Z_][A-Z0-9_]*|\{[A-Z_][A-Z0-9_]*\})")


def _load_env_file() -> None:
    """加载 .env，兼容 MokioAgent 的方式：不指定路径，由 CWD 向上搜索。
    然后展开 $VAR / ${VAR} 引用。
    """
    load_dotenv(encoding="utf-8", override=True)

    # 展开 $VAR / ${VAR} 引用（兼容 API_KEY="$OTHER_VAR"）
    for key in list(os.environ):
        val = os.environ[key]
        if "$" not in val:
            continue
        expanded = _VAR_RE.sub(
            lambda m: os.environ.get(m.group(1).strip("{}"), m.group(0)),
            val,
        )
        if expanded != val:
            os.environ[key] = expanded


_load_env_file()


def _get_env(key: str, *fallbacks: str, default: str = "") -> str:
    """依次尝试 key, *fallbacks，返回第一个非空值。"""
    for name in (key, *fallbacks):
        val = os.getenv(name)
        if val:
            return val
    return default


@dataclass
class Settings:
    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "sqlite+aiosqlite:///./data/chat.db?timeout=15",
        )
    )

    # DeepSeek (OpenAI-compatible API)
    # 兼容 MokioAgent 的 API_KEY / MODEL / BASE_URL 变量名
    deepseek_api_key: str = field(
        default_factory=lambda: _get_env("DEEPSEEK_API_KEY", "API_KEY")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: _get_env(
            "DEEPSEEK_BASE_URL", "BASE_URL", default="https://api.deepseek.com/v1"
        ).rstrip("/")
    )
    deepseek_model: str = field(
        default_factory=lambda: _get_env("DEEPSEEK_MODEL", "MODEL", default="deepseek-v4-flash")
    )

    # Skill file path
    skill_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SKILL_PATH", str(Path.cwd() / "SKILL.md"))
        )
    )

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")


settings = Settings()
