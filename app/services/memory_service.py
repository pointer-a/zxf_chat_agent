from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemoryFact, MemorySummary
from app.providers import BaseProvider

logger = logging.getLogger(__name__)

EXTRACT_FACT_PROMPT = """从下面的对话中提取关于用户的重要事实信息。
只提取确定的、有信息量的事实，忽略客套话和模糊表达。

请以 JSON 数组格式返回，每个元素包含:
- "content": 事实描述（简洁、具体）
- "category": 类别（background/education/career/family/preference/goal/experience/opinion）
- "confidence": 置信度 0-1

对话：
用户: {user_message}
助手: {assistant_message}

如果没有可提取的事实，返回 []。
只输出 JSON，不要额外文字。"""

UPDATE_SUMMARY_PROMPT = """你是用户画像分析师。基于当前画像摘要和新的对话内容，
更新用户画像摘要。摘要应该简洁（2-4句话），包含：
1. 用户的核心背景（教育、职业、家庭）
2. 当前面临的主要决策或问题
3. 已知的关键偏好或约束

当前摘要：
{current_summary}

最新对话：
用户: {user_message}
助手: {assistant_message}

请输出更新后的摘要文本（纯文本，不要 JSON 包装）。"""

RELEVANCE_CHECK_PROMPT = """你是记忆检索系统。判断以下记忆条目是否与用户当前问题相关。
只返回 "relevant" 或 "irrelevant"。

记忆: {fact}
用户问题: {user_message}

相关则返回 "relevant"，否则返回 "irrelevant"。"""


class MemoryService:
    """Manage long-term memory for users: facts, summaries, and retrieval."""

    def __init__(self, db: AsyncSession, provider: BaseProvider) -> None:
        self.db = db
        self.provider = provider

    async def extract_facts(
        self,
        user_id: int,
        user_message: str,
        assistant_message: str,
    ) -> List[MemoryFact]:
        """Extract memory facts from a conversation turn and save them."""
        prompt = EXTRACT_FACT_PROMPT.format(
            user_message=user_message[:2000],
            assistant_message=assistant_message[:2000],
        )
        try:
            response = await self.provider.complete([
                {"role": "system", "content": "你是一个精确的记忆提取助手。只提取确定的事实。"},
                {"role": "user", "content": prompt},
            ])
            facts_data = json.loads(response)
            if not isinstance(facts_data, list):
                return []
        except (json.JSONDecodeError, RuntimeError, Exception) as exc:
            logger.warning("Failed to extract facts: %s", exc)
            return []

        saved: List[MemoryFact] = []
        for item in facts_data[:5]:  # max 5 facts per turn
            content = item.get("content", "").strip()
            if not content or len(content) < 10:
                continue
            fact = MemoryFact(
                user_id=user_id,
                content=content,
                category=item.get("category"),
                confidence=min(float(item.get("confidence", 0.5)), 1.0),
            )
            self.db.add(fact)
            saved.append(fact)

        # 不在此 flush — 由调用方统一 commit，实现一轮保存一次
        return saved

    async def update_summary(
        self,
        user_id: int,
        user_message: str,
        assistant_message: str,
    ) -> Optional[MemorySummary]:
        """Update or create the user profile summary."""
        # Get latest summary
        stmt = (
            select(MemorySummary)
            .where(MemorySummary.user_id == user_id)
            .order_by(desc(MemorySummary.version))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest = result.scalar_one_or_none()
        current_summary = latest.summary if latest else "无现有摘要。"

        prompt = UPDATE_SUMMARY_PROMPT.format(
            current_summary=current_summary,
            user_message=user_message[:1500],
            assistant_message=assistant_message[:1500],
        )
        try:
            response = await self.provider.complete([
                {"role": "system", "content": "你是一个用户画像分析师。输出简洁的纯文本摘要。"},
                {"role": "user", "content": prompt},
            ])
            new_summary = response.strip()
            if not new_summary or len(new_summary) < 20:
                return latest
        except (RuntimeError, Exception) as exc:
            logger.warning("Failed to update summary: %s", exc)
            return latest

        summary = MemorySummary(
            user_id=user_id,
            summary=new_summary,
            version=(latest.version + 1) if latest else 1,
        )
        self.db.add(summary)
        # 不在此 flush — 由调用方统一 commit，实现一轮保存一次
        return summary

    async def get_relevant_facts(
        self,
        user_id: int,
        user_message: str,
        max_facts: int = 8,
    ) -> List[MemoryFact]:
        """Retrieve memory facts relevant to the current user message."""
        stmt = (
            select(MemoryFact)
            .where(MemoryFact.user_id == user_id)
            .order_by(desc(MemoryFact.confidence), desc(MemoryFact.updated_at))
        )
        result = await self.db.execute(stmt)
        all_facts: List[MemoryFact] = list(result.scalars().all())

        if not all_facts:
            return []

        scored: list[tuple[float, MemoryFact]] = []
        for fact in all_facts[:20]:  # check top 20 by confidence
            relevance = await self._check_relevance(fact.content, user_message)
            if relevance == "relevant":
                scored.append((fact.confidence, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [fact for _, fact in scored[:max_facts]]

    async def get_latest_summary(self, user_id: int) -> Optional[str]:
        """Get the latest user summary text."""
        stmt = (
            select(MemorySummary)
            .where(MemorySummary.user_id == user_id)
            .order_by(desc(MemorySummary.version))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()
        return summary.summary if summary else None

    async def _check_relevance(self, fact: str, user_message: str) -> str:
        """Check if a fact is relevant to the current message."""
        prompt = RELEVANCE_CHECK_PROMPT.format(fact=fact, user_message=user_message[:500])
        try:
            response = await self.provider.complete([
                {"role": "system", "content": "你是一个二元分类器。只返回 relevant 或 irrelevant。"},
                {"role": "user", "content": prompt},
            ])
            result = response.strip().lower()
            return "relevant" if "relevant" in result else "irrelevant"
        except (RuntimeError, Exception):
            return "relevant"  # default to relevant on error
