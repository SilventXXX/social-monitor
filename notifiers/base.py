"""通知基类"""

from abc import ABC, abstractmethod
from typing import List

from models.item import MonitorItem


class BaseNotifier(ABC):
    """通知器基类"""

    @abstractmethod
    async def notify(self, items: List[MonitorItem]) -> None:
        """发送通知"""
        pass
