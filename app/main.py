from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import async_session_factory, init_db
from app.models import Model, Provider

logger = logging.getLogger(__name__)


async def seed_default_provider() -> None:
    from sqlalchemy import func, select

    async with async_session_factory() as db:
        result = await db.execute(select(func.count()).select_from(Provider))
        count = result.scalar()
        if count and count > 0:
            return

        if not settings.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY 未设置，跳过自动注册。")
            return

        logger.info("正在自动注册 DeepSeek 模型...")

        provider = Provider(
            name="DeepSeek",
            provider_type="openai_compatible",
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            is_active=1,
        )
        db.add(provider)
        await db.flush()

        for name, label in [
            ("deepseek-v4-flash", "DeepSeek v4 Flash"),
            ("deepseek-v4-pro", "DeepSeek v4 Pro"),
        ]:
            db.add(Model(
                provider_id=provider.id,
                model_name=name,
                display_name=label,
                is_active=1,
            ))

        await db.commit()
        logger.info("DeepSeek 模型注册完成。")


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    await init_db()
    logger.info("数据库初始化完成。")
    await seed_default_provider()

    # 打印 API key 状态（仅前后几位，不暴露完整 key）
    key = settings.deepseek_api_key
    if key:
        logger.info("DeepSeek API key 已加载 (前8=%s 后8=%s len=%d)", key[:8], key[-8:], len(key))
    else:
        logger.warning("DeepSeek API key 未设置！")
    yield
    logger.info("服务关闭。")


app = FastAPI(
    title="ZXF Dialogue Agent",
    description="在线对话 Agent — 张雪峰视角，纯 DeepSeek 驱动",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API routes ──
from app.routers import admin, auth, chat, memories, models_api  # noqa: E402

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(models_api.router)
app.include_router(memories.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


# ── Static file serving & SPA fallback ──
@app.api_route("/{path:path}", methods=["GET"])
async def serve_frontend(request: Request, path: str):
    if path.startswith("api/"):
        raise StarletteHTTPException(status_code=404)

    if path:
        rel_path = path.removeprefix("static/")
        file_path = STATIC_DIR / rel_path
        if file_path.exists() and file_path.is_file():
            media_type, _ = mimetypes.guess_type(str(file_path))
            return FileResponse(str(file_path), media_type=media_type)

    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    raise StarletteHTTPException(status_code=404)
