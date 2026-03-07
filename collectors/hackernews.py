"""Hacker News 采集器

使用 HN 官方 Firebase API（免费，无需任何账号）。
采集 Top Stories 和 New Stories 中匹配关键词的内容。
API 文档：https://github.com/HackerNews/API
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from config.loader import get_keywords, get_usernames
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)

_HN_API = "https://hacker-news.firebaseio.com/v0"
_FETCH_TOP_N = 100  # 每次检查前 N 条
_MAX_CONCURRENT = 10  # 并发请求数


class HackerNewsCollector(BaseCollector):
    """Hacker News 采集器"""

    async def _fetch_json(self, client: httpx.AsyncClient, url: str) -> Optional[dict]:
        try:
            r = await client.get(url, timeout=10.0)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.debug("HN 请求失败 %s: %s", url, e)
            return None

    async def _fetch_story(self, client: httpx.AsyncClient, story_id: int) -> Optional[RawItem]:
        data = await self._fetch_json(client, f"{_HN_API}/item/{story_id}.json")
        if not data or data.get("type") not in ("story", "ask", "show"):
            return None
        if data.get("dead") or data.get("deleted"):
            return None

        title = data.get("title", "")
        text = data.get("text", "") or ""
        author = data.get("by", "unknown")
        item_id = str(data.get("id", story_id))
        score = data.get("score", 0)
        comments = data.get("descendants", 0)
        url = data.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        
        # 解析发布时间 (Unix timestamp)
        published_at = None
        if "time" in data:
            published_at = datetime.fromtimestamp(data["time"], tz=timezone.utc)

        keywords = [k.lower() for k in get_keywords()]
        usernames = [u.lower() for u in get_usernames()]
        combined = (title + " " + text).lower()

        keyword_match = any(k in combined for k in keywords)
        author_match = author.lower() in usernames
        # 无关键词配置时采集高分内容（score > 50）
        if not keywords and not usernames:
            if score < 50:
                return None
        elif not keyword_match and not author_match:
            return None

        content = title
        if text:
            content += f"\n\n{text[:500]}"

        return RawItem(
            platform=ItemPlatform.HACKERNEWS,
            external_id=item_id,
            content=content,
            author=author,
            author_id=None,
            url=url,
            engagement_count=score + comments,
            is_direct_mention=author_match,
            raw_data=json.dumps({"id": item_id, "score": score, "comments": comments}),
            published_at=published_at,
        )

    async def collect(self) -> List[RawItem]:
        """采集 HN Top Stories 和 New Stories"""
        async with httpx.AsyncClient() as client:
            # 同时获取 top 和 new 列表
            top_ids, new_ids = await asyncio.gather(
                self._fetch_json(client, f"{_HN_API}/topstories.json"),
                self._fetch_json(client, f"{_HN_API}/newstories.json"),
            )

        candidate_ids = list(
            dict.fromkeys(
                (top_ids or [])[:_FETCH_TOP_N] + (new_ids or [])[:50]
            )
        )

        if not candidate_ids:
            return []

        # 并发拉取故事详情
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def fetch_with_limit(story_id: int) -> Optional[RawItem]:
            async with semaphore:
                async with httpx.AsyncClient() as client:
                    return await self._fetch_story(client, story_id)

        results = await asyncio.gather(*[fetch_with_limit(sid) for sid in candidate_ids])
        items = [r for r in results if r is not None]
        logger.info("HackerNews 采集到 %d 条", len(items))
        return items
