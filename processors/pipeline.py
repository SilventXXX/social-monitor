"""处理流水线：去重 -> AI评分 -> 入库

完全依赖AI根据requirements评分，跳过关键词预过滤
"""

import logging
from typing import List, Set

from sqlalchemy.ext.asyncio import AsyncSession

from collectors.base import RawItem
from models.item import MonitorItem
from config.loader import get_requirements
from .dedup import DedupProcessor
from .ai_scorer import score_items_relevance

logger = logging.getLogger(__name__)


async def process_items(
    session: AsyncSession,
    raw_items: List[RawItem],
) -> List[MonitorItem]:
    """完整处理流水线：去重、AI评分、入库，返回新入库的项
    
    注意：跳过关键词过滤，完全依赖AI根据requirements评分
    """
    # 跳过关键词过滤，直接对所有内容进行预评分标记
    pre_scored = [(item, 0) for item in raw_items]
    
    # 去重，只处理新内容
    new_items_raw = await DedupProcessor.filter_existing(session, pre_scored)

    if not new_items_raw:
        logger.info("无新内容需处理")
        return []

    new_raw_items = [item for item, _ in new_items_raw]
    requirements = get_requirements()
    
    # AI 评分：完全根据requirements判断相关性
    logger.info("对 %d 条内容进行AI评分...", len(new_raw_items))
    scored = await score_items_relevance(new_raw_items, requirements)

    saved: List[MonitorItem] = []
    seen_keys: Set[tuple[str, str]] = set()  # 防止同一批内有重复
    
    for raw, score in scored:
        key = (raw.platform.value, raw.external_id)
        if key in seen_keys:
            continue  # 跳过同一批内的重复
        seen_keys.add(key)

        if score < 50:
            continue  # 低于50分直接丢弃，不入库

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
            published_at=raw.published_at,  # 保存原始发布时间
        )
        session.add(item)
        saved.append(item)

    if saved:
        await session.commit()
        for item in saved:
            await session.refresh(item)
        logger.info("新入库 %d 条监控内容", len(saved))

    return saved
