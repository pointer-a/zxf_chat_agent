"""实时搜索服务 — 在 LLM 调用前获取最新信息。

支持两种后端：
1. Bing Web Search API v7（需要 API key，推荐）
2. Direct web fetch（零配置，稳定性略低）

搜索结果的格式设计为可直接插入 system prompt 供 LLM 使用。
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Bing API 端点
BING_API_URL = "https://api.bing.microsoft.com/v7.0/search"
# Bing 公共搜索页（用于备用方案）
BING_PUBLIC_URL = "https://www.bing.com/search"

# 搜索超时（秒）
SEARCH_TIMEOUT = 10.0

# 最小查询长度（太短不搜）
MIN_QUERY_LEN = 4

# 简单启发式：非事实类关键词，命中任一就不搜
_SKIP_KEYWORDS = [
    "你好", "hello", "hi", "早上好", "下午好", "晚上好",
    "再见", "拜拜", "bye", "谢谢", "感谢", "thanks",
    "你是谁", "你能做什么", "重复", "再说一遍",
]


def _should_search(query: str) -> bool:
    """判断用户消息是否需要搜索。"""
    q = query.strip()
    if len(q) < MIN_QUERY_LEN:
        return False
    q_lower = q.lower()
    for kw in _SKIP_KEYWORDS:
        if kw in q_lower or kw in q:
            return False
    return True


class SearchService:
    """实时搜索服务。"""

    def __init__(self) -> None:
        self.enabled = settings.search_enabled
        self.api_key = settings.search_api_key
        self.mkt = settings.search_mkt
        self.count = settings.search_count
        self.fallback = settings.search_fallback

    async def search(self, query: str) -> str | None:
        """执行搜索，返回格式化结果文本。失败或无需搜索则返回 None。"""
        if not self.enabled:
            logger.debug("Search disabled, skipping.")
            return None
        if not _should_search(query):
            logger.debug("Query too short or greeting, skipping search.")
            return None

        logger.info("Searching for: %s", query[:100])

        # 尝试 Bing API
        if self.api_key:
            try:
                result = await self._search_bing_api(query)
                if result:
                    return result
                logger.warning("Bing API returned no results, %s.",
                               "falling back to fetch" if self.fallback else "skipping")
            except Exception as exc:
                logger.warning("Bing API search failed: %s", exc)
                if not self.fallback:
                    return None
        else:
            logger.info("No Bing API key configured, using fetch fallback.")

        # 备用：直接抓取搜索页
        if self.fallback:
            try:
                return await self._search_fetch(query)
            except Exception as exc:
                logger.warning("Fetch fallback also failed: %s", exc)

        return None

    async def _search_bing_api(self, query: str) -> str | None:
        """通过 Bing Web Search API v7 搜索。"""
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {
            "q": query,
            "count": self.count,
            "mkt": self.mkt,
            "textFormat": "Raw",
        }
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(BING_API_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        pages = (data.get("webPages") or {}).get("value", [])
        if not pages:
            return None

        lines = [f"## 实时搜索结果", f'查询："{query}"', ""]
        for i, page in enumerate(pages[:self.count], 1):
            name = (page.get("name") or "").strip()
            snippet = (page.get("snippet") or "").strip()
            url = (page.get("url") or "").strip()
            lines.append(f"{i}. **{name}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        return "\n".join(lines)

    async def _search_fetch(self, query: str) -> str | None:
        """备用方案：直接抓取 Bing 搜索页并提取结果片段。"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        params = {
            "q": query,
            "count": self.count,
            "mkt": self.mkt,
            "cc": "cn",
        }
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(BING_PUBLIC_URL, headers=headers, params=params)
            resp.raise_for_status()
            html = resp.text

        results = self._parse_bing_html(html)
        if not results:
            return None

        lines = [f"## 实时搜索结果", f'查询："{query}"', ""]
        for i, (title, snippet, url) in enumerate(results[:self.count], 1):
            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _parse_bing_html(html: str) -> list[tuple[str, str, str]]:
        """从 Bing 搜索结果页 HTML 中解析标题、摘要、URL。"""
        results: list[tuple[str, str, str]] = []

        # 提取 <li class="b_algo"> 块（Bing 移动端/桌面版通用）
        algo_pattern = re.compile(
            r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
            re.IGNORECASE | re.DOTALL,
        )
        for block in algo_pattern.findall(html):
            # 跳过 CSS 样式块（没有标题链接）
            if not re.search(r'<h2', block, re.IGNORECASE):
                continue

            # 提取标题和 URL（href 可能在任意属性位置）
            link_match = re.search(
                r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.IGNORECASE | re.DOTALL,
            )
            if not link_match:
                continue
            url = link_match.group(1).strip()
            title = re.sub(r"<[^>]+>", "", link_match.group(2)).strip()

            # 提取摘要
            snippet = ""
            p_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.IGNORECASE | re.DOTALL)
            if p_match:
                snippet = re.sub(r"<[^>]+>", "", p_match.group(1)).strip()

            # 清理空白
            title = re.sub(r"\s+", " ", title).strip()
            snippet = re.sub(r"\s+", " ", snippet).strip()

            if title:
                results.append((title, snippet, url))

        # 备选方案：如果上面的 b_algo 匹配不到结果，尝试 <div class="b_caption"> 结构
        if not results:
            li_blocks = re.findall(
                r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?</li>',
                html,
                re.IGNORECASE | re.DOTALL,
            )
            for block in li_blocks:
                link_match = re.search(
                    r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    block,
                    re.IGNORECASE | re.DOTALL,
                )
                if not link_match:
                    continue
                url = link_match.group(1).strip()
                title = re.sub(r"<[^>]+>", "", link_match.group(2)).strip()
                snippet = ""
                # look for <p> or <span class="b_lineclamp"> for snippet
                p_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.IGNORECASE | re.DOTALL)
                if p_match:
                    snippet = re.sub(r"<[^>]+>", "", p_match.group(1)).strip()
                title = re.sub(r"\s+", " ", title).strip()
                snippet = re.sub(r"\s+", " ", snippet).strip()
                if title:
                    results.append((title, snippet, url))

        return results
