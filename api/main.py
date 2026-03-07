"""FastAPI 主应用"""

from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from models.database import init_db, async_session_maker
from models.item import MonitorItem, ItemPlatform
from tasks.collect import run_collect_and_notify

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(
        run_collect_and_notify,
        IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="collect",
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Social Monitor API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db():
    async with async_session_maker() as session:
        yield session


@app.get("/")
async def root():
    """返回 Web 面板"""
    index_path = Path(__file__).parent.parent / "web" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"service": "Social Monitor", "status": "ok"}


@app.get("/status")
async def status():
    """返回当前运行模式，供面板显示"""
    if settings.demo_mode:
        mode = "demo"
    elif settings.reddit_client_id and settings.reddit_client_secret:
        mode = "reddit" if not settings.twitter_bearer_token else "full"
    else:
        mode = "full" if settings.twitter_bearer_token else "demo"
    return {"mode": mode, "service": "Social Monitor"}


@app.get("/items")
async def list_items(
    db: AsyncSession = Depends(get_db),
    platform: Optional[ItemPlatform] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """获取监控内容列表"""
    stmt = select(MonitorItem).order_by(desc(MonitorItem.created_at))
    if platform:
        stmt = stmt.where(MonitorItem.platform == platform)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": i.id,
                "platform": i.platform.value,
                "external_id": i.external_id,
                "content": i.content,
                "author": i.author,
                "url": i.url,
                "score": i.score,
                "engagement_count": i.engagement_count,
                "is_direct_mention": i.is_direct_mention,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "read_at": i.read_at.isoformat() if i.read_at else None,
            }
            for i in items
        ]
    }


@app.post("/items/{item_id}/read")
async def mark_read(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    """标记为已读"""
    from datetime import datetime, timezone

    stmt = select(MonitorItem).where(MonitorItem.id == item_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        return {"ok": False, "error": "not found"}
    item.read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@app.post("/collect")
async def trigger_collect():
    """手动触发一次采集（供调度器或外部调用）"""
    from tasks.collect import run_collect_and_notify

    await run_collect_and_notify()
    return {"ok": True}


@app.post("/backfill")
async def backfill(days: int = Query(default=7, ge=1, le=30)):
    """回溯历史内容（默认最近 7 天，最多 30 天）"""
    from collectors.hn_backfill import HNBackfillCollector
    from processors.pipeline import process_items
    from notifiers.feishu import FeishuNotifier

    collector = HNBackfillCollector(days=days)
    raw_items = await collector.collect()

    async with async_session_maker() as session:
        saved = await process_items(session, raw_items)

    if saved:
        await FeishuNotifier().notify(saved)

    return {"ok": True, "collected": len(raw_items), "saved": len(saved)}
