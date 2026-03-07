"""采集与通知任务"""

import logging
from datetime import datetime, timezone

from config.settings import settings
from models.database import async_session_maker
from models.item import MonitorItem
from collectors.twitter import TwitterCollector
from collectors.reddit import RedditCollector
from collectors.demo import DemoCollector
from processors.pipeline import process_items
from notifiers.email import EmailNotifier
from notifiers.feishu import FeishuNotifier
from notifiers.telegram import TelegramNotifier
from notifiers.webhook import WebhookNotifier

logger = logging.getLogger(__name__)


async def run_collect_and_notify():
    """执行采集、处理、入库、通知的完整流程"""
    all_raw = []

    # 1. 采集（演示模式使用 DemoCollector）
    if settings.demo_mode:
        collectors = [DemoCollector()]
    else:
        collectors = [TwitterCollector(), RedditCollector()]

    for collector in collectors:
        try:
            items = await collector.collect()
            all_raw.extend(items)
            logger.info("%s 采集到 %d 条", collector.__class__.__name__, len(items))
        except Exception as e:
            logger.exception("采集失败: %s", e)

    if not all_raw:
        logger.info("本次无新采集内容")
        return

    # 2. 处理并入库
    async with async_session_maker() as session:
        new_items = await process_items(session, all_raw)

    if not new_items:
        logger.info("无新内容需通知")
        return

    # 3. 通知
    for notifier in [
        FeishuNotifier(),
        TelegramNotifier(),
        EmailNotifier(),
        WebhookNotifier(),
    ]:
        try:
            await notifier.notify(new_items)
        except Exception as e:
            logger.exception("通知失败: %s", e)

    # 4. 更新 notified_at
    async with async_session_maker() as session:
        from sqlalchemy import update
        now = datetime.now(timezone.utc)
        for item in new_items:
            await session.execute(
                update(MonitorItem).where(MonitorItem.id == item.id).values(notified_at=now)
            )
        await session.commit()
