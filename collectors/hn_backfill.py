"""Hacker News 历史回溯采集器

使用 Algolia HN Search API（免费，无需认证）按关键词和时间范围回溯历史内容。
API 文档：https://hn.algolia.com/api
"""

import json
import logging
import time
from typing import List

import httpx

from config.loader import get_keywords, get_requirements
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)

_ALGOLIA_API = "https://hn.algolia.com/api/v1"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialMonitor/1.0)"}


class HNBackfillCollector(BaseCollector):
    """HN 历史回溯采集器（基于 Algolia 搜索 API）"""

    def __init__(self, days: int = 7):
        self.days = days

    async def collect(self) -> List[RawItem]:
        keywords = get_keywords()

        # 无关键词时用 requirements 里提取的核心词兜底
        if not keywords:
            requirements = get_requirements()
            # 简单提取引号内或常见英文词
            keywords = ["AI agent", "LLM", "social network", "openclaw", "moltbook"]
            logger.info("未配置关键词，使用默认关键词回溯")

        since_ts = int(time.time()) - self.days * 86400
        items: List[RawItem] = []
        seen_ids = set()

        async with httpx.AsyncClient(headers=_HEADERS) as client:
            for keyword in keywords[:10]:  # 限制关键词数量
                try:
                    page = 0
                    while page < 3:  # 每个关键词最多取 3 页
                        params = {
                            "query": keyword,
                            "tags": "story",
                            "numericFilters": f"created_at_i>{since_ts}",
                            "hitsPerPage": 50,
                            "page": page,
                        }
                        r = await client.get(
                            f"{_ALGOLIA_API}/search",
                            params=params,
                            timeout=15.0,
                        )
                        r.raise_for_status()
                        data = r.json()
                        hits = data.get("hits", [])
                        if not hits:
                            break

                        for hit in hits:
                            story_id = str(hit.get("objectID", ""))
                            if not story_id or story_id in seen_ids:
                                continue
                            seen_ids.add(story_id)

                            title = hit.get("title", "")
                            story_text = hit.get("story_text", "") or ""
                            author = hit.get("author", "unknown")
                            url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
                            points = hit.get("points") or 0
                            num_comments = hit.get("num_comments") or 0

                            content = title
                            if story_text:
                                import re
                                clean = re.sub(r"<[^>]+>", "", story_text).strip()
                                content += f"\n\n{clean[:500]}"

                            items.append(
                                RawItem(
                                    platform=ItemPlatform.HACKERNEWS,
                                    external_id=story_id,
                                    content=content,
                                    author=author,
                                    url=url,
                                    engagement_count=points + num_comments,
                                    is_direct_mention=False,
                                    raw_data=json.dumps({
                                        "id": story_id,
                                        "points": points,
                                        "comments": num_comments,
                                        "keyword": keyword,
                                    }),
                                )
                            )

                        if page >= data.get("nbPages", 1) - 1:
                            break
                        page += 1

                except Exception as e:
                    logger.warning("HN 回溯关键词 [%s] 失败: %s", keyword, e)

        logger.info("HN 历史回溯采集到 %d 条（最近 %d 天）", len(items), self.days)
        return items
