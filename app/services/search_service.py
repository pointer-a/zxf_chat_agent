"""实时搜索服务 — 集成搜索能力（Bing 后端，零配置）。

使用 cn.bing.com（国内可访问）搜索页，无需 API key 和浏览器。
外部搜索结果格式化后直接插入 system prompt 供 LLM 使用。
"""

from __future__ import annotations

import logging
import random
from urllib.parse import quote_plus

import httpx
from selectolax.parser import HTMLParser

from app.config import settings

logger = logging.getLogger(__name__)

# Bing 搜索页
BING_URL = "https://www.bing.com/search"

# 搜索超时（秒）
SEARCH_TIMEOUT = 15.0

# 最小查询长度
MIN_QUERY_LEN = 4

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

_SKIP_KEYWORDS = [
    "你好", "hello", "hi", "早上好", "下午好", "晚上好",
    "再见", "拜拜", "bye", "谢谢", "感谢", "thanks",
    "你是谁", "你能做什么", "重复", "再说一遍",
]


def _should_search(query: str) -> bool:
    """判断是否需要搜索。"""
    q = query.strip()
    if len(q) < MIN_QUERY_LEN:
        return False
    q_lower = q.lower()
    for kw in _SKIP_KEYWORDS:
        if kw in q_lower or kw in q:
            return False
    return True


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
    }


class SearchService:
    """实时搜索服务 — 使用 Bing 后端，无需 API key。"""

    def __init__(self) -> None:
        self.enabled = settings.search_enabled
        self.count = settings.search_count or 5

    async def search(self, query: str) -> str | None:
        """执行搜索，返回 Markdown 格式化结果。失败或无需搜索则返回 None。"""
        if not self.enabled:
            logger.debug("Search disabled, skipping.")
            return None
        if not _should_search(query):
            logger.debug("Query too short or greeting, skipping search.")
            return None

        logger.info("Searching: %s", query[:100])

        try:
            results = await self._search_bing(query)
            if not results:
                logger.info("Bing returned no results.")
                return None
            return self._format_results(query, results)
        except Exception as exc:
            logger.error("Search failed: %s", exc)
            return None

    async def _search_bing(self, query: str) -> list[tuple[str, str, str]]:
        """抓取 Bing 搜索页并解析结果。"""
        encoded = quote_plus(query)
        url = f"{BING_URL}?q={encoded}"

        async with httpx.AsyncClient(
            headers=_get_headers(),
            timeout=httpx.Timeout(SEARCH_TIMEOUT),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        return self._parse_bing_html(html)

    def _parse_bing_html(self, html: str) -> list[tuple[str, str, str]]:
        """用 selectolax 解析 Bing 搜索结果。"""
        tree = HTMLParser(html)
        results: list[tuple[str, str, str]] = []

        # Bing 的搜索结果在 <li class="b_algo"> 中
        for element in tree.css("li.b_algo")[:self.count]:
            try:
                # 标题和链接
                h2 = element.css_first("h2")
                if not h2:
                    continue
                link = h2.css_first("a")
                if not link:
                    continue

                title = link.text(strip=True)
                href = link.attributes.get("href", "")
                if not title or not href:
                    continue

                # 摘要
                snippet = ""
                p = element.css_first(".b_caption p")
                if p:
                    snippet = p.text(strip=True)

                results.append((title, href, snippet))
            except Exception:
                continue

        return results

    @staticmethod
    def _format_results(query: str, results: list[tuple[str, str, str]]) -> str:
        """格式化为 Markdown。"""
        lines = [f"## 实时搜索结果", f'查询："{query}"', ""]
        for i, (title, url, snippet) in enumerate(results, 1):
            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
            lines.append("")
        return "\n".join(lines)
