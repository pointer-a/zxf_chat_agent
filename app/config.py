from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_VAR_RE = re.compile(r"\$([A-Z_][A-Z0-9_]*|\{[A-Z_][A-Z0-9_]*\})")


def _load_env_file() -> None:
    """加载 .env，然后递归展开 $VAR / ${VAR} 引用，兼容 Linux shell 风格。"""
    # 优先找项目根目录下的 .env（按 config.py 自身路径定位）
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, encoding="utf-8")
    else:
        load_dotenv(encoding="utf-8")

    # 展开 $VAR / ${VAR} 引用（兼容 API_KEY="$OTHER_VAR" 这种写法）
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
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
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
