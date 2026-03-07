"""飞书自定义机器人通知

使用飞书群聊自定义机器人 Webhook 发送监控内容。
支持签名校验（FEISHU_SECRET）和富文本卡片消息。

配置项：
  FEISHU_WEBHOOK_URL  飞书机器人 Webhook 地址（必填）
  FEISHU_SECRET       签名密钥（可选，开启「签名校验」时必填）
"""

import base64
import hashlib
import hmac
import logging
import time
from typing import List

import httpx

from config.settings import settings
from config.loader import get_min_score_to_notify
from models.item import MonitorItem
from .base import BaseNotifier

logger = logging.getLogger(__name__)

# 单次通知最多发送条数，避免刷屏
_MAX_ITEMS_PER_NOTIFY = 10


def _make_sign(secret: str, timestamp: int) -> str:
    """生成飞书签名：base64(hmac-sha256(timestamp + "\\n" + secret))"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _build_card(item: MonitorItem) -> dict:
    """将单条监控内容构建为飞书交互式卡片"""
    platform_label = {"twitter": "Twitter / X", "reddit": "Reddit"}.get(
        item.platform.value, item.platform.value
    )
    # 标题颜色：直接提及用红色，高分用橙色，普通用蓝色
    if item.is_direct_mention:
        color = "red"
    elif item.score >= 70:
        color = "orange"
    else:
        color = "blue"

    content_preview = item.content[:200].replace("\n", " ")
    if len(item.content) > 200:
        content_preview += "..."

    elements = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**平台**\n{platform_label}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**作者**\n{item.author}",
                    },
                },
            ],
        },
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**评分**\n{item.score} / 100",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**互动数**\n{item.engagement_count}",
                    },
                },
            ],
        },
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": content_preview,
            },
        },
    ]

    if item.url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看原文"},
                        "url": item.url,
                        "type": "default",
                    }
                ],
            }
        )

    title = "直接提及" if item.is_direct_mention else "新监控内容"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"content": f"【{title}】{platform_label}", "tag": "plain_text"},
                "template": color,
            },
            "elements": elements,
        },
    }


def _build_summary_text(items: List[MonitorItem]) -> dict:
    """多条内容合并为一条文本消息（超出上限时使用）"""
    lines = [f"共发现 {len(items)} 条新监控内容：\n"]
    for i, item in enumerate(items[:5], 1):
        platform_label = {"twitter": "Twitter", "reddit": "Reddit"}.get(
            item.platform.value, item.platform.value
        )
        lines.append(
            f"{i}. [{platform_label}] @{item.author}  评分:{item.score}\n"
            f"   {item.content[:100]}...\n"
            f"   {item.url or ''}\n"
        )
    if len(items) > 5:
        lines.append(f"... 还有 {len(items) - 5} 条，请登录面板查看")
    return {"msg_type": "text", "content": {"text": "".join(lines)}}


class FeishuNotifier(BaseNotifier):
    """飞书自定义机器人通知"""

    async def notify(self, items: List[MonitorItem]) -> None:
        min_score = get_min_score_to_notify()
        to_notify = [i for i in items if i.score >= min_score]
        if not to_notify:
            return

        webhook_url = settings.feishu_webhook_url
        if not webhook_url:
            logger.warning("未配置 FEISHU_WEBHOOK_URL，跳过飞书通知")
            return

        secret = settings.feishu_secret

        if len(to_notify) > _MAX_ITEMS_PER_NOTIFY:
            # 条数过多时发一条汇总文本
            payloads = [_build_summary_text(to_notify)]
        else:
            # 逐条发卡片
            payloads = [_build_card(item) for item in to_notify]

        async with httpx.AsyncClient() as client:
            for payload in payloads:
                # 签名校验
                if secret:
                    ts = int(time.time())
                    payload["timestamp"] = str(ts)
                    payload["sign"] = _make_sign(secret, ts)

                try:
                    r = await client.post(webhook_url, json=payload, timeout=10.0)
                    data = r.json()
                    if data.get("code") != 0:
                        logger.warning("飞书发送失败: %s", data)
                    else:
                        logger.debug("飞书消息发送成功")
                except Exception as e:
                    logger.exception("飞书通知失败: %s", e)

        logger.info("飞书通知已发送 %d 条", len(payloads))
