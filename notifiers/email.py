"""邮件通知"""

import logging
from typing import List

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config.settings import settings
from config.loader import get_min_score_to_notify
from models.item import MonitorItem
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """SMTP 邮件通知"""

    async def notify(self, items: List[MonitorItem]) -> None:
        min_score = get_min_score_to_notify()
        to_notify = [i for i in items if i.score >= min_score]
        if not to_notify:
            return

        if not settings.smtp_host or not settings.notify_email:
            logger.warning("未配置 SMTP 或通知邮箱，跳过邮件通知")
            return

        subject = f"[Social Monitor] 发现 {len(to_notify)} 条新内容"
        body_parts = []
        for item in to_notify:
            body_parts.append(
                f"---\n平台: {item.platform.value}\n"
                f"作者: {item.author}\n"
                f"内容: {item.content[:500]}...\n"
                f"链接: {item.url or 'N/A'}\n"
                f"评分: {item.score}\n"
            )
        body = "\n".join(body_parts)

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user or settings.notify_email
        msg["To"] = settings.notify_email
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=(settings.smtp_port == 465),
            )
            logger.info("邮件通知已发送至 %s", settings.notify_email)
        except Exception as e:
            logger.exception("邮件发送失败: %s", e)
