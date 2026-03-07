"""演示模式采集器 - 返回模拟数据，无需 API 密钥"""

import random
from typing import List

from .base import RawItem, BaseCollector
from models.item import ItemPlatform


MOCK_ITEMS = [
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_ai1",
        content="Pika Labs just launched their new AI Self feature! You can now create a digital twin of yourself in minutes. This is a game changer for content creators. #AISelf #DigitalTwin",
        author="ai_enthusiast",
        url="https://reddit.com/r/artificial/comments/demo1",
        engagement_count=342,
        is_direct_mention=False,
    ),
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_ai2",
        content="Someone mentioned AI分身 technology in r/MachineLearning - this new startup is doing amazing work with digital avatars! Worth checking out for anyone interested in AI clone tech.",
        author="ml_researcher",
        url="https://reddit.com/r/MachineLearning/comments/demo2",
        engagement_count=528,
        is_direct_mention=True,
    ),
    RawItem(
        platform=ItemPlatform.TWITTER,
        external_id="demo_twitter_ai1",
        content="Just tried the new Pika AI Self feature. The digital twin quality is insane! This is the future of personalized content creation. @pika_labs",
        author="tech_influencer",
        url="https://x.com/i/status/demo1",
        engagement_count=1256,
        is_direct_mention=True,
    ),
    RawItem(
        platform=ItemPlatform.TWITTER,
        external_id="demo_twitter_ai2",
        content="HeyGen vs Pika AI - which one has better AI avatar generation? Here's my comparison after testing both platforms for a week. #AIavatar #digitaltwin",
        author="product_reviewer",
        url="https://x.com/i/status/demo2",
        engagement_count=893,
        is_direct_mention=False,
    ),
    RawItem(
        platform=ItemPlatform.REDDIT,
        external_id="demo_reddit_ai3",
        content="New research paper on AI digital twin technology - the implications for virtual presence and remote work are huge. Character.AI is just the beginning.",
        author="ai_researcher",
        url="https://reddit.com/r/singularity/comments/demo3",
        engagement_count=215,
        is_direct_mention=False,
    ),
]


class DemoCollector(BaseCollector):
    """演示模式采集器，返回预设模拟数据"""

    async def collect(self) -> List[RawItem]:
        # 每次随机返回 2-4 条，模拟真实采集
        count = random.randint(2, 4)
        return random.sample(MOCK_ITEMS, min(count, len(MOCK_ITEMS)))
