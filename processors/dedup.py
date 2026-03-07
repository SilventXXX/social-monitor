"""去重：按 platform + external_id 检查是否已存在"""

from typing import List, Set

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from collectors.base import RawItem
from models.item import MonitorItem, ItemPlatform


class DedupProcessor:
    """去重处理器"""

    @staticmethod
    async def filter_existing(
        session: AsyncSession,
        items: List[tuple[RawItem, int]],
    ) -> List[tuple[RawItem, int]]:
        """过滤掉数据库中已存在的内容"""
        if not items:
            return []

        seen: Set[tuple[str, str]] = set()
        for item, score in items:
            key = (item.platform.value, item.external_id)
            seen.add(key)

        conditions = or_(
            *[
                (MonitorItem.platform == ItemPlatform(p)) & (MonitorItem.external_id == e)
                for p, e in seen
            ]
        )
        stmt = select(MonitorItem.platform, MonitorItem.external_id).where(conditions)
        result = await session.execute(stmt)
        existing = {
            (r[0].value if hasattr(r[0], "value") else r[0], r[1])
            for r in result
        }

        return [
            (item, score)
            for item, score in items
            if (item.platform.value, item.external_id) not in existing
        ]
