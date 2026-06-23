from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件：优先找项目根目录（config.py 的父目录的父目录）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path, override=False, encoding="utf-8")
else:
    # fallback: 当前工作目录
    load_dotenv(encoding="utf-8")


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
