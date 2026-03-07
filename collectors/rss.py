"""RSS 多源采集器

采集主流海外科技媒体的 RSS/Atom Feed，无需任何 API Key。
可在 monitor_config.yaml 的 rss_feeds 中自定义信息源。
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from config.loader import get_keywords, get_rss_feeds
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)

# 内置默认信息源
_DEFAULT_FEEDS = [
    {"name": "TechCrunch",          "url": "https://techcrunch.com/feed/"},
    {"name": "Wired",               "url": "https://www.wired.com/feed/rss"},
    {"name": "Ars Technica",        "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "The Verge",           "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "MIT Tech Review",     "url": "https://www.technologyreview.com/feed/"},
    {"name": "VentureBeat",         "url": "https://venturebeat.com/feed/"},
    {"name": "Dev.to",              "url": "https://dev.to/feed"},
    {"name": "InfoQ",               "url": "https://feed.infoq.com/"},
    {"name": "Product Hunt",        "url": "https://www.producthunt.com/feed"},
    {"name": "Hacker News Blog",    "url": "https://hnrss.org/frontpage"},
]

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialMonitor/1.0)"}
_MAX_CONCURRENT = 5


class RSSCollector(BaseCollector):
    """RSS 多源采集器"""

    async def _fetch_feed(self, client: httpx.AsyncClient, name: str, url: str) -> List[RawItem]:
        try:
            r = await client.get(url, timeout=15.0, headers=_HEADERS, follow_redirects=True)
            r.raise_for_status()
        except Exception as e:
            logger.warning("RSS 拉取失败 [%s]: %s", name, e)
            return []

        feed = feedparser.parse(r.text)
        keywords = [k.lower() for k in get_keywords()]
        items: List[RawItem] = []

        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "") or ""
            link = entry.get("link", "")
            author = entry.get("author", name)

            # 解析发布时间
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            # 去除 HTML 标签
            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()

            combined = (title + " " + summary_clean).lower()

            # 关键词过滤：无关键词时采集全部
            if keywords and not any(k in combined for k in keywords):
                continue

            # 用 URL 做唯一 ID
            external_id = hashlib.md5(link.encode()).hexdigest()[:16]
            content = title
            if summary_clean:
                content += f"\n\n{summary_clean[:500]}"

            items.append(
                RawItem(
                    platform=ItemPlatform.RSS,
                    external_id=external_id,
                    content=content,
                    author=author,
                    url=link,
                    engagement_count=0,
                    is_direct_mention=False,
                    raw_data=json.dumps({"source": name, "title": title}),
                    published_at=published_at,
                )
            )

        return items

    async def collect(self) -> List[RawItem]:
        # 合并默认 + 用户自定义信息源
        custom_feeds = get_rss_feeds()
        feeds = _DEFAULT_FEEDS + custom_feeds

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def fetch_with_limit(name: str, url: str) -> List[RawItem]:
            async with semaphore:
                async with httpx.AsyncClient() as client:
                    return await self._fetch_feed(client, name, url)

        results = await asyncio.gather(
            *[fetch_with_limit(f["name"], f["url"]) for f in feeds]
        )
        items = [item for sublist in results for item in sublist]
        logger.info("RSS 采集到 %d 条", len(items))
        return items
