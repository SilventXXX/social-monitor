"""Webhook 通知"""

import json
import logging
from typing import List

import httpx

from config.settings import settings
from config.loader import get_min_score_to_notify
from models.item import MonitorItem
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class WebhookNotifier(BaseNotifier):
    """HTTP Webhook 通知"""

    async def notify(self, items: List[MonitorItem]) -> None:
        min_score = get_min_score_to_notify()
        to_notify = [i for i in items if i.score >= min_score]
        if not to_notify:
            return

        if not settings.webhook_url:
            return

        payload = {
            "count": len(to_notify),
            "items": [
                {
                    "platform": item.platform.value,
                    "external_id": item.external_id,
                    "author": item.author,
                    "content": item.content[:500],
                    "url": item.url,
                    "score": item.score,
                }
                for item in to_notify
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    settings.webhook_url,
                    json=payload,
                    timeout=10.0,
                    headers={"Content-Type": "application/json"},
                )
                if r.status_code >= 400:
                    logger.warning("Webhook 请求失败: %s %s", r.status_code, r.text)
                else:
                    logger.info("Webhook 通知已发送")
        except Exception as e:
            logger.exception("Webhook 通知失败: %s", e)
