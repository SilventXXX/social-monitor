"""采集器基类与数据模型"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from models.item import ItemPlatform


@dataclass
class RawItem:
    """采集到的原始内容项"""

    platform: ItemPlatform
    external_id: str
    content: str
    author: str
    author_id: Optional[str] = None
    url: Optional[str] = None
    engagement_count: int = 0
    is_direct_mention: bool = False
    raw_data: Optional[str] = None


class BaseCollector(ABC):
    """采集器基类"""

    @abstractmethod
    async def collect(self) -> List[RawItem]:
        """执行采集，返回原始内容列表"""
        pass
