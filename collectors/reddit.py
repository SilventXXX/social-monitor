"""Reddit 采集器

使用 PRAW 监听 subreddit 中的关键词、用户提及。
需要配置 Reddit API：REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET。
"""

import asyncio
import json
import logging
from typing import List

from config.settings import settings
from config.loader import get_keywords, get_usernames, get_subreddits
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """Reddit 采集器"""

    def __init__(self):
        self._reddit = None

    def _get_reddit(self):
        """延迟初始化 Reddit 客户端"""
        if self._reddit is not None:
            return self._reddit

        try:
            import praw
        except ImportError:
            logger.warning("praw 未安装，跳过 Reddit 采集")
            return None

        cid = settings.reddit_client_id
        csecret = settings.reddit_client_secret
        if not cid or not csecret:
            logger.warning("未配置 Reddit API，跳过 Reddit 采集")
            return None

        self._reddit = praw.Reddit(
            client_id=cid,
            client_secret=csecret,
            user_agent=settings.reddit_user_agent,
        )
        return self._reddit

    def _collect_sync(self) -> List[RawItem]:
        """同步采集逻辑（PRAW 为同步库）"""
        reddit = self._get_reddit()
        if not reddit:
            return []

        items: List[RawItem] = []
        keywords = [k.lower() for k in get_keywords()]
        usernames = [u.lower() for u in get_usernames()]
        subreddit_names = get_subreddits() or ["all"]

        def matches_keyword(text: str) -> bool:
            t = text.lower()
            return any(k in t for k in keywords) or any(
                f"/u/{u}" in t or f"u/{u}" in t for u in usernames
            )

        try:
            for sub_name in subreddit_names[:5]:  # 限制 subreddit 数量
                try:
                    sub = reddit.subreddit(sub_name)
                    for submission in sub.new(limit=50):
                        if matches_keyword(submission.title or "") or matches_keyword(
                            submission.selftext or ""
                        ):
                            items.append(
                                RawItem(
                                    platform=ItemPlatform.REDDIT,
                                    external_id=submission.id,
                                    content=f"{submission.title}\n\n{submission.selftext or ''}",
                                    author=submission.author.name if submission.author else "[deleted]",
                                    author_id=str(submission.author.id) if submission.author else None,
                                    url=f"https://reddit.com{submission.permalink}",
                                    engagement_count=submission.score + submission.num_comments,
                                    is_direct_mention=any(
                                        f"/u/{u}" in (submission.title or "").lower()
                                        or f"/u/{u}" in (submission.selftext or "").lower()
                                        for u in usernames
                                    ),
                                    raw_data=json.dumps(
                                        {
                                            "id": submission.id,
                                            "title": submission.title,
                                            "subreddit": sub_name,
                                        }
                                    ),
                                )
                            )
                        # 检查评论中的提及（避免加载 MoreComments）
                        try:
                            submission.comments.replace_more(limit=0)
                        except Exception:
                            pass
                        for comment in submission.comments.list()[:20]:
                            if not hasattr(comment, "body") or not comment.body:
                                continue
                            if matches_keyword(comment.body):
                                items.append(
                                    RawItem(
                                        platform=ItemPlatform.REDDIT,
                                        external_id=comment.id,
                                        content=comment.body,
                                        author=comment.author.name if comment.author else "[deleted]",
                                        author_id=str(comment.author.id) if comment.author else None,
                                        url=f"https://reddit.com{submission.permalink}",
                                        engagement_count=comment.score,
                                        is_direct_mention=any(
                                            f"/u/{u}" in comment.body.lower()
                                            for u in usernames
                                        ),
                                        raw_data=json.dumps(
                                            {"id": comment.id, "submission_id": submission.id}
                                        ),
                                    )
                                )
                except Exception as e:
                    logger.warning("Reddit subreddit %s 采集失败: %s", sub_name, e)

        except Exception as e:
            logger.exception("Reddit 采集失败: %s", e)

        return items

    async def collect(self) -> List[RawItem]:
        """采集 Reddit 上的相关内容"""
        return await asyncio.to_thread(self._collect_sync)
