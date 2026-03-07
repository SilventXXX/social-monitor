"""定时采集任务"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from models.database import async_session_maker
from collectors.reddit import RedditCollector
from collectors.twitter import TwitterCollector
from processors.pipeline import process_items
from notifiers.telegram import TelegramNotifier
from notifiers.webhook import WebhookNotifier
from notifiers.email import EmailNotifier

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def collect_and_notify() -> None:
    """执行一次完整的采集 -> 处理 -> 通知流程"""
    logger.info("开始采集...")

    collectors = [RedditCollector(), TwitterCollector()]
    all_raw = []
    for collector in collectors:
        try:
            items = await collector.collect()
            all_raw.extend(items)
        except Exception as e:
            logger.exception("采集器 %s 失败: %s", collector.__class__.__name__, e)

    if not all_raw:
        logger.info("本次采集无新内容")
        return

    async with async_session_maker() as session:
        saved = await process_items(session, all_raw)

    if not saved:
        logger.info("无新入库内容，跳过通知")
        return

    notifiers = [TelegramNotifier(), WebhookNotifier(), EmailNotifier()]
    for notifier in notifiers:
        try:
            await notifier.notify(saved)
        except Exception as e:
            logger.exception("通知器 %s 失败: %s", notifier.__class__.__name__, e)


def start_scheduler() -> None:
    scheduler.add_job(
        collect_and_notify,
        "interval",
        minutes=settings.poll_interval_minutes,
        id="collect_and_notify",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("调度器已启动，每 %d 分钟采集一次", settings.poll_interval_minutes)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("调度器已停止")
