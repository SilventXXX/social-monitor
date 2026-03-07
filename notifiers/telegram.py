"""Telegram 通知"""

import html
import logging
from typing import List

import httpx

from config.settings import settings
from config.loader import get_min_score_to_notify
from models.item import MonitorItem
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    """Telegram Bot 通知"""

    async def notify(self, items: List[MonitorItem]) -> None:
        min_score = get_min_score_to_notify()
        to_notify = [i for i in items if i.score >= min_score]
        if not to_notify:
            return

        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            logger.warning("未配置 Telegram Bot，跳过 Telegram 通知")
            return

        for item in to_notify:
            text = (
                f"<b>新监控内容</b>\n\n"
                f"平台: {html.escape(item.platform.value)}\n"
                f"作者: {html.escape(item.author)}\n"
                f"内容: {html.escape(item.content[:300])}...\n"
                f"链接: {html.escape(item.url or 'N/A')}\n"
                f"评分: {item.score}"
            )
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(url, json=payload, timeout=10.0)
                    if r.status_code != 200:
                        logger.warning("Telegram 发送失败: %s", r.text)
            except Exception as e:
                logger.exception("Telegram 通知失败: %s", e)

        logger.info("Telegram 通知已发送 %d 条", len(to_notify))
