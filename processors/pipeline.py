"""处理流水线：过滤 -> 去重 -> AI评分 -> 入库"""

import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from collectors.base import RawItem
from models.item import MonitorItem
from config.loader import get_requirements
from .filter import FilterProcessor
from .dedup import DedupProcessor
from .ai_scorer import score_items_relevance

logger = logging.getLogger(__name__)


async def process_items(
    session: AsyncSession,
    raw_items: List[RawItem],
) -> List[MonitorItem]:
    """完整处理流水线：过滤、去重、AI评分、入库，返回新入库的项"""
    filtered = FilterProcessor.process(raw_items)
    # 先去重，只对真正新内容调用 AI 评分（节省 API 费用）
    pre_scored = [(item, 0) for item in filtered]
    new_items_raw = await DedupProcessor.filter_existing(session, pre_scored)

    if not new_items_raw:
        return []

    new_raw_items = [item for item, _ in new_items_raw]
    requirements = get_requirements()
    scored = await score_items_relevance(new_raw_items, requirements)
    new_items = scored

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
