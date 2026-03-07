"""处理流水线：过滤 -> 评分 -> 去重 -> 入库"""

import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from collectors.base import RawItem
from models.item import MonitorItem, ItemPlatform
from .filter import FilterProcessor
from .score import ScoreProcessor
from .dedup import DedupProcessor

logger = logging.getLogger(__name__)


async def process_items(
    session: AsyncSession,
    raw_items: List[RawItem],
) -> List[MonitorItem]:
    """完整处理流水线：过滤、评分、去重、入库，返回新入库的项"""
    filtered = FilterProcessor.process(raw_items)
    scored = ScoreProcessor.process(filtered)
    new_items = await DedupProcessor.filter_existing(session, scored)

    saved: List[MonitorItem] = []
    for raw, score in new_items:
        item = MonitorItem(
            platform=raw.platform,
            external_id=raw.external_id,
            content=raw.content[:10000],  # 限制长度
            author=raw.author[:256],
            author_id=raw.author_id,
            url=raw.url,
            score=score,
            engagement_count=raw.engagement_count,
            is_direct_mention=raw.is_direct_mention,
            raw_data=raw.raw_data,
        )
        session.add(item)
        saved.append(item)

    if saved:
        await session.commit()
        for item in saved:
            await session.refresh(item)
        logger.info("新入库 %d 条监控内容", len(saved))

    return saved
