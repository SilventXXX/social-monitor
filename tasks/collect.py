"""采集与通知任务"""

import logging
from datetime import datetime, timezone

from config.settings import settings
from models.database import async_session_maker
from models.item import MonitorItem
from collectors.hackernews import HackerNewsCollector
from collectors.github_trending import GitHubTrendingCollector
from collectors.rss import RSSCollector
from collectors.gmail import GmailCollector
from processors.pipeline import process_items
from notifiers.email import EmailNotifier
from notifiers.feishu import FeishuNotifier
from notifiers.telegram import TelegramNotifier
from notifiers.webhook import WebhookNotifier

logger = logging.getLogger(__name__)


async def run_collect_and_notify():
    """执行采集、处理、入库、通知的完整流程"""
    all_raw = []

    # 1. 采集
    collectors = [RSSCollector(), HackerNewsCollector(), GitHubTrendingCollector(), GmailCollector()]

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

    # 显示分数分布，方便排查推送问题
    from config.loader import get_min_score_to_notify
    threshold = get_min_score_to_notify()
    above = [i for i in new_items if i.score >= threshold]
    logger.info("新入库 %d 条，其中 %d 条分数 ≥%d 将推送，分数分布: %s",
                len(new_items), len(above), threshold,
                sorted([i.score for i in new_items], reverse=True))

    # 3. 通知（只有成功后才标记为已通知）
    from sqlalchemy import update
    now = datetime.now(timezone.utc)
    notified_item_ids = set()

    for notifier in [
        FeishuNotifier(),
        TelegramNotifier(),
        EmailNotifier(),
        WebhookNotifier(),
    ]:
        try:
            await notifier.notify(new_items)
            # 记录成功通知的项
            for item in new_items:
                notified_item_ids.add(item.id)
            logger.info(f"{notifier.__class__.__name__} 通知成功，{len(new_items)} 条")
        except Exception as e:
            logger.exception(f"{notifier.__class__.__name__} 通知失败: %s", e)

    # 4. 更新 notified_at（只更新成功通知的项）
    if notified_item_ids:
        async with async_session_maker() as session:
            for item_id in notified_item_ids:
                await session.execute(
                    update(MonitorItem).where(MonitorItem.id == item_id).values(notified_at=now)
                )
            await session.commit()
            logger.info(f"已标记 {len(notified_item_ids)} 条为已通知")
