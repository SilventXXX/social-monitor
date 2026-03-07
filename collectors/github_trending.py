"""GitHub Trending 采集器

爬取 GitHub Trending 页面，无需任何 API Key。
支持按关键词过滤，无关键词时采集全部 Trending 项目。
"""

import json
import logging
from datetime import datetime, timezone
from typing import List

import httpx
from bs4 import BeautifulSoup

from config.loader import get_keywords
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)

_TRENDING_URL = "https://github.com/trending"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SocialMonitor/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


class GitHubTrendingCollector(BaseCollector):
    """GitHub Trending 采集器"""

    async def collect(self) -> List[RawItem]:
        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
                r = await client.get(_TRENDING_URL, timeout=15.0)
                r.raise_for_status()
        except Exception as e:
            logger.exception("GitHub Trending 请求失败: %s", e)
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        repo_articles = soup.select("article.Box-row")

        keywords = [k.lower() for k in get_keywords()]
        items: List[RawItem] = []

        for article in repo_articles:
            try:
                # 仓库名
                h2 = article.select_one("h2 a")
                if not h2:
                    continue
                repo_path = h2.get("href", "").strip("/")  # owner/repo
                if not repo_path or "/" not in repo_path:
                    continue
                owner, repo_name = repo_path.split("/", 1)

                # 描述
                desc_el = article.select_one("p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                # 今日 Star 数
                stars_today_el = article.select("span.d-inline-block.float-sm-right")
                stars_today_text = stars_today_el[0].get_text(strip=True) if stars_today_el else "0"
                stars_today = int(
                    "".join(filter(str.isdigit, stars_today_text)) or "0"
                )

                # 总 Star 数
                star_el = article.select_one("a[href$='/stargazers']")
                total_stars = int(
                    "".join(filter(str.isdigit, star_el.get_text(strip=True))) or "0"
                ) if star_el else 0

                # 语言
                lang_el = article.select_one("span[itemprop='programmingLanguage']")
                language = lang_el.get_text(strip=True) if lang_el else ""

                combined = f"{repo_name} {description}".lower()

                # 关键词过滤：无关键词时采集全部
                if keywords and not any(k in combined for k in keywords):
                    continue

                content = f"{repo_path}\n{description}"
                if language:
                    content += f"\n语言: {language}"

                # GitHub Trending 没有原始发布时间，使用当前时间
                published_at = datetime.now(timezone.utc)

                items.append(
                    RawItem(
                        platform=ItemPlatform.GITHUB,
                        external_id=repo_path.replace("/", "_"),
                        content=content,
                        author=owner,
                        author_id=None,
                        url=f"https://github.com/{repo_path}",
                        engagement_count=total_stars,
                        is_direct_mention=False,
                        raw_data=json.dumps({
                            "repo": repo_path,
                            "stars_today": stars_today,
                            "total_stars": total_stars,
                            "language": language,
                        }),
                        published_at=published_at,
                    )
                )
            except Exception as e:
                logger.debug("解析 GitHub Trending 条目失败: %s", e)

        logger.info("GitHub Trending 采集到 %d 条", len(items))
        return items
