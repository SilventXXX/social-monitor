"""X (Twitter) 采集器

使用 Mentions API 或关键词搜索采集提及内容。
需要配置 X API 凭证：TWITTER_BEARER_TOKEN 或 OAuth 1.0a 密钥。
"""

import asyncio
import json
import logging
from typing import List, Optional

from config.settings import settings
from config.loader import get_keywords, get_hashtags, get_usernames
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)


class TwitterCollector(BaseCollector):
    """X/Twitter 采集器"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """延迟初始化 Twitter 客户端"""
        if self._client is not None:
            return self._client

        try:
            import tweepy
        except ImportError:
            logger.warning("tweepy 未安装，跳过 Twitter 采集")
            return None

        token = settings.twitter_bearer_token
        if not token:
            logger.warning("未配置 TWITTER_BEARER_TOKEN，跳过 Twitter 采集")
            return None

        self._client = tweepy.Client(bearer_token=token)
        return self._client

    def _collect_sync(self) -> List[RawItem]:
        """同步采集逻辑（tweepy 为同步库）"""
        client = self._get_client()
        if not client:
            return []

        items: List[RawItem] = []
        user_id = settings.twitter_user_id

        # 1. 获取 mentions（需要 user_id）
        if user_id:
            try:
                mentions = client.get_users_mentions(
                    id=user_id,
                    max_results=50,
                    expansions=["author_id"],
                    tweet_fields=["created_at", "public_metrics"],
                    user_fields=["username"],
                )
                if mentions.data:
                    includes = getattr(mentions, "includes", None) or {}
                    users = {u.id: u for u in (includes.get("users") or [])}
                    for tweet in mentions.data:
                        author = users.get(tweet.author_id)
                        author_name = author.username if author else str(tweet.author_id)
                        metrics = tweet.public_metrics or {}
                        engagement = (
                            metrics.get("like_count", 0)
                            + metrics.get("retweet_count", 0)
                            + metrics.get("reply_count", 0)
                        )
                        items.append(
                            RawItem(
                                platform=ItemPlatform.TWITTER,
                                external_id=str(tweet.id),
                                content=tweet.text,
                                author=author_name,
                                author_id=str(tweet.author_id),
                                url=f"https://x.com/i/status/{tweet.id}",
                                engagement_count=engagement,
                                is_direct_mention=True,
                                raw_data=json.dumps(tweet.data) if hasattr(tweet, "data") else None,
                            )
                        )
            except Exception as e:
                logger.exception("Twitter mentions 采集失败: %s", e)

        # 2. 关键词搜索（构建 query）
        keywords = get_keywords()
        hashtags = get_hashtags()
        usernames = get_usernames()
        search_terms = keywords + [f"#{h}" for h in hashtags] + [f"@{u}" for u in usernames]
        if not search_terms:
            return items

        query = " OR ".join(f'"{t}"' for t in search_terms[:10])  # 限制数量
        try:
            search_response = client.search_recent_tweets(
                query=query,
                max_results=50,
                expansions=["author_id"],
                tweet_fields=["created_at", "public_metrics"],
                user_fields=["username"],
            )
            if search_response.data:
                includes = getattr(search_response, "includes", None) or {}
                users = {u.id: u for u in (includes.get("users") or [])}
                seen_ids = {i.external_id for i in items}
                for tweet in search_response.data:
                    if str(tweet.id) in seen_ids:
                        continue
                    author = users.get(tweet.author_id)
                    author_name = author.username if author else str(tweet.author_id)
                    metrics = tweet.public_metrics or {}
                    engagement = (
                        metrics.get("like_count", 0)
                        + metrics.get("retweet_count", 0)
                        + metrics.get("reply_count", 0)
                    )
                    items.append(
                        RawItem(
                            platform=ItemPlatform.TWITTER,
                            external_id=str(tweet.id),
                            content=tweet.text,
                            author=author_name,
                            author_id=str(tweet.author_id),
                            url=f"https://x.com/i/status/{tweet.id}",
                            engagement_count=engagement,
                            is_direct_mention=False,
                            raw_data=json.dumps(tweet.data) if hasattr(tweet, "data") else None,
                        )
                    )
        except Exception as e:
            logger.exception("Twitter 搜索采集失败: %s", e)

        return items

    async def collect(self) -> List[RawItem]:
        """采集 X 上的提及与关键词匹配内容"""
        return await asyncio.to_thread(self._collect_sync)
