"""数据库连接与会话管理"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from config.settings import settings
from .item import Base, MonitorItem


# SQLite 需要特殊处理 async
def _get_engine():
    url = settings.database_url
    if "sqlite" in url:
        return create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
    return create_async_engine(url, echo=False)


engine = _get_engine()
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def init_db():
    """初始化数据库，创建表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """获取异步数据库会话"""
    async with async_session_maker() as session:
        yield session
