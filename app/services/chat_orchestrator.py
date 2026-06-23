from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional, Tuple

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Conversation, Message, User
from app.providers import BaseProvider
from app.services.memory_service import MemoryService
from app.services.model_registry import ModelRegistry
from zxf_agent.skill_loader import Skill, load_skill

logger = logging.getLogger(__name__)

# Controls how often to update memory summary (every N turns)
MEMORY_UPDATE_INTERVAL = 5


def _sse(event_type: str, data) -> str:
    """Build a Server-Sent Event data line."""
    payload = json.dumps({"type": event_type, "content": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _load_skill() -> Skill:
    """Load the Zhang Xuefeng skill."""
    path = Path(settings.skill_path)
    if path.exists():
        return load_skill(path)
    logger.warning("Skill file not found at %s, using default system prompt", path)
    return Skill(
        name="default",
        description="General assistant",
        body="你是一个中文对话助手。",
        raw="你是一个中文对话助手。",
    )


# Cache the skill at module level
_skill: Optional[Skill] = None


def get_skill() -> Skill:
    global _skill
    if _skill is None:
        _skill = _load_skill()
    return _skill


class ChatOrchestrator:
    """Orchestrate the full chat flow: memory, skill, provider."""

    def __init__(
        self,
        db: AsyncSession,
        provider: BaseProvider,
        memory_service: MemoryService,
    ) -> None:
        self.db = db
        self.provider = provider
        self.memory_service = memory_service

    async def process_message(
        self,
        conversation_id: int,
        user_content: str,
        skip_save_user: bool = False,
    ) -> Tuple[Message, bool]:
        """
        Process a user message:
        1. Build context with skill, memory, and history
        2. Call the LLM
        3. Save user message and assistant response
        4. Update memory (facts + summary)
        Returns (assistant_message, memories_updated).
        """
        # Get conversation
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Save user message (if not already saved by the route handler)
        if not skip_save_user:
            user_msg = Message(
                conversation_id=conversation_id,
                role="user",
                content=user_content,
            )
            self.db.add(user_msg)
            await self.db.flush()

        # Get conversation history (last 20 turns)
        history_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(40)  # 20 user + 20 assistant
        )
        result = await self.db.execute(history_stmt)
        history_messages = list(reversed(result.scalars().all()))

        # Build system prompt
        system_prompt = await self._build_system_prompt(
            conversation.user_id, user_content
        )

        # Build message list
        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in history_messages:
            if msg.role in ("user", "assistant"):
                llm_messages.append({"role": msg.role, "content": msg.content})

        # Call provider
        assistant_content = await self.provider.complete(llm_messages)

        # Save assistant message
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
        )
        self.db.add(assistant_msg)

        # Generate title if first exchange
        if conversation.title is None or conversation.title.strip() == "":
            title = await self._generate_title(user_content)
            conversation.title = title[:200] if title else None

        await self.db.flush()

        # Update memory
        memories_updated = await self._update_memory(
            conversation.user_id,
            user_content,
            assistant_content,
            len(history_messages) // 2,  # approximate turn count
        )

        await self.db.commit()
        return assistant_msg, memories_updated

    async def process_message_stream(
        self,
        conversation_id: int,
        user_content: str,
        skip_save_user: bool = False,
    ) -> AsyncGenerator[str, None]:
        """流式处理，以 SSE data: 行格式 yield 事件：token / title / done / error"""
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if conversation is None:
            yield _sse("error", "会话不存在")
            return

        # 保存用户消息
        if not skip_save_user:
            user_msg = Message(conversation_id=conversation_id, role="user", content=user_content)
            self.db.add(user_msg)
            await self.db.flush()

        # 取历史
        history_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(40)
        )
        result = await self.db.execute(history_stmt)
        history_messages = list(reversed(result.scalars().all()))

        # 构建 system prompt + messages
        system_prompt = await self._build_system_prompt(conversation.user_id, user_content)
        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in history_messages:
            if msg.role in ("user", "assistant"):
                llm_messages.append({"role": msg.role, "content": msg.content})

        # 流式调用 provider
        collected = []
        try:
            async for token in self.provider.complete_stream(llm_messages):
                collected.append(token)
                yield _sse("token", token)
        except Exception as exc:
            logger.error("Stream error: %s", exc)
            yield _sse("error", str(exc))
            return

        full_text = "".join(collected).strip()

        # 存 assistant 消息
        assistant_msg = Message(conversation_id=conversation_id, role="assistant", content=full_text)
        self.db.add(assistant_msg)

        # 首轮生成标题
        if conversation.title is None or conversation.title.strip() == "":
            try:
                title = await self._generate_title(user_content)
                conversation.title = title[:200] if title else None
                yield _sse("title", conversation.title)
            except Exception as exc:
                logger.warning("Title gen failed: %s", exc)

        await self.db.flush()

        # 记忆更新
        memories_updated = False
        try:
            facts = await self.memory_service.extract_facts(
                conversation.user_id, user_content, full_text
            )
            if facts:
                memories_updated = True
            turn_count = len(history_messages) // 2
            if turn_count % MEMORY_UPDATE_INTERVAL == 0:
                summary = await self.memory_service.update_summary(
                    conversation.user_id, user_content, full_text
                )
                if summary:
                    memories_updated = True
        except Exception as exc:
            logger.error("Memory update failed: %s", exc)

        await self.db.commit()
        yield _sse("done", {"message_id": assistant_msg.id, "memories_updated": memories_updated})

    async def _build_system_prompt(
        self,
        user_id: int,
        user_message: str,
    ) -> str:
        """Build the system prompt with skill context and user memory."""
        skill = get_skill()

        # Get user summary
        summary = await self.memory_service.get_latest_summary(user_id)
        summary_section = ""
        if summary:
            summary_section = f"\n\n## 关于用户\n{summary}"

        # Get relevant facts
        facts = await self.memory_service.get_relevant_facts(user_id, user_message)
        facts_section = ""
        if facts:
            fact_texts = "\n".join(f"- {f.content}" for f in facts)
            facts_section = f"\n\n## 已知用户信息\n{fact_texts}"

        # Combine: base rules from agent.py + skill body + memory
        base_rules = """运行规则：
1. 你是以张雪峰视角和用户聊天，基于公开言论推断，非本人观点。
2. 用户说"退出""切回正常""不用扮演了"时，停止角色扮演。
3. 涉及具体专业、院校、行业、就业、薪资、录取、政策等事实问题时，不要凭空编数据。
4. 如果无法获取实时数据，必须先追问必要背景，或明确说需要查数据。
5. 回答要先给判断，再解释；短句、高密度、中文口语。
6. 给教育和职业建议时，优先追问分数/学历、省份、家庭资源、目标城市、风险承受能力。
7. 不要输出内部分类过程，直接像一个真实对话 agent 一样回答。"""

        return f"""你是一个对话 agent，必须严格基于下面的 Agent Skill 运作。

{base_rules}

以下是必须遵循的 skill 内容：

{skill.body}
{summary_section}
{facts_section}""".strip()

    async def _generate_title(self, first_message: str) -> str:
        """Generate a conversation title from the first user message."""
        try:
            response = await self.provider.complete([
                {
                    "role": "system",
                    "content": "用简洁的 4-8 个字概括用户问题的核心主题。只输出标题本身。",
                },
                {"role": "user", "content": first_message[:500]},
            ])
            return response.strip().strip('"').strip("'")
        except (RuntimeError, Exception) as exc:
            logger.warning("Failed to generate title: %s", exc)
            return first_message[:30] + "..."

    async def _update_memory(
        self,
        user_id: int,
        user_message: str,
        assistant_message: str,
        turn_count: int,
    ) -> bool:
        """Extract facts and update summary periodically."""
        updated = False
        try:
            facts = await self.memory_service.extract_facts(
                user_id, user_message, assistant_message
            )
            if facts:
                updated = True

            # Update summary every N turns
            if turn_count % MEMORY_UPDATE_INTERVAL == 0:
                summary = await self.memory_service.update_summary(
                    user_id, user_message, assistant_message
                )
                if summary:
                    updated = True
        except Exception as exc:
            logger.error("Memory update failed: %s", exc)

        return updated
