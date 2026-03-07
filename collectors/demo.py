"""演示模式采集器 - 返回模拟数据，无需 API 密钥"""

import random
from typing import List

from .base import RawItem, BaseCollector
from models.item import ItemPlatform


MOCK_ITEMS = [
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_1",
        content="This is a demo post about Python. Great discussion on async/await patterns!",
        author="demo_user_1",
        url="https://reddit.com/r/python/comments/demo1",
        engagement_count=42,
        is_direct_mention=False,
    ),
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_2",
        content="Someone mentioned your_project in r/programming - worth checking out!",
        author="demo_user_2",
        url="https://reddit.com/r/programming/comments/demo2",
        engagement_count=128,
        is_direct_mention=True,
    ),
    RawItem(
        platform=ItemPlatform.TWITTER,
        external_id="demo_twitter_1",
        content="Just saw @your_username's latest update. Really impressive work! #yourhashtag",
        author="demo_tweeter",
        url="https://x.com/i/status/demo1",
        engagement_count=56,
        is_direct_mention=True,
    ),
    RawItem(
        platform=ItemPlatform.TWITTER,
        external_id="demo_twitter_2",
        content="Discussion about your_product in the dev community. Lots of positive feedback.",
        author="tech_reviewer",
        url="https://x.com/i/status/demo2",
        engagement_count=203,
        is_direct_mention=False,
    ),
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_3",
        content="New to your_brand - any tips for getting started?",
        author="new_user",
        url="https://reddit.com/r/learnprogramming/comments/demo3",
        engagement_count=15,
        is_direct_mention=False,
    ),
]


class DemoCollector(BaseCollector):
    """演示模式采集器，返回预设模拟数据"""

    async def collect(self) -> List[RawItem]:
        # 每次随机返回 2-4 条，模拟真实采集
        count = random.randint(2, 4)
        return random.sample(MOCK_ITEMS, min(count, len(MOCK_ITEMS)))
