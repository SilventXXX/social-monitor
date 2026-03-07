"""采集器模块"""

from .base import RawItem, BaseCollector
from .twitter import TwitterCollector
from .reddit import RedditCollector
from .demo import DemoCollector

__all__ = [
    "RawItem",
    "BaseCollector",
    "TwitterCollector",
    "RedditCollector",
    "DemoCollector",
]
