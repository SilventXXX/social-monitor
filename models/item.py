"""监控项数据模型"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Text, Boolean, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ItemPlatform(str, Enum):
    """内容来源平台"""

    TWITTER = "twitter"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    RSS = "rss"


class Base(DeclarativeBase):
    pass


class MonitorItem(Base):
    """监控到的内容项"""

    __tablename__ = "monitor_items"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_platform_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(SQLEnum(ItemPlatform), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(256))
    author_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)  # 重要性评分 0-100
    engagement_count: Mapped[int] = mapped_column(Integer, default=0)  # 互动数
    is_direct_mention: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否直接 @
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 原始 JSON
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 原始发布时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<MonitorItem {self.platform}:{self.external_id}>"
