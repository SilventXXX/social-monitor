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
from typing import List, Optional

import httpx
from openai import AsyncOpenAI

from config.settings import settings
from config.loader import get_min_score_to_notify, get_requirements
from models.item import MonitorItem
from .base import BaseNotifier

logger = logging.getLogger(__name__)

# AI 客户端缓存
_ai_client: Optional[AsyncOpenAI] = None


def _get_ai_client() -> Optional[AsyncOpenAI]:
    """获取 AI 客户端"""
    global _ai_client
    if _ai_client is not None:
        return _ai_client
    if not settings.kimi_api_key:
        return None
    _ai_client = AsyncOpenAI(
        api_key=settings.kimi_api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )
    return _ai_client

# 单次通知最多发送条数，避免刷屏
_MAX_ITEMS_PER_NOTIFY = 10


async def _generate_summary_and_title(content: str, platform: str) -> tuple[str, str]:
    """使用 AI 生成一句话标题和总结
    
    Returns:
        (title, summary) - 标题(50字内)和完整总结(200字内)
    """
    client = _get_ai_client()
    if not client:
        # 无 AI 时返回默认
        default = content[:150] + "..." if len(content) > 150 else content
        return default[:50] + "...", default
    
    requirements = get_requirements()
    
    prompt = f"""你是一个信息筛选助手。请对以下监控内容生成：
1. 一句话标题（50字以内，概括核心观点，作为消息标题）
2. 完整总结（200字以内，解释为什么值得看）

用户监控需求：
{requirements}

内容来源：{platform}
内容：
{content[:1000]}

请严格按以下格式返回：
TITLE: 一句话标题（50字内）
SUMMARY: 
💡 核心观点：...
📌 为什么值得关注：...

只返回上述格式内容，不要其他说明。"""

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        text = resp.choices[0].message.content.strip()
        
        # 解析 TITLE 和 SUMMARY
        title = "新监控内容"
        summary = text
        
        if "TITLE:" in text:
            parts = text.split("SUMMARY:", 1)
            title_part = parts[0].replace("TITLE:", "").strip()
            title = title_part[:50] + "..." if len(title_part) > 50 else title_part
            if len(parts) > 1:
                summary = parts[1].strip()
        
        return title, summary
    except Exception as e:
        logger.exception("AI 总结生成失败: %s", e)
        # 失败时返回内容前50字作为标题，前150字作为总结
        default = content[:150] + "..." if len(content) > 150 else content
        return default[:50], default


def _make_sign(secret: str, timestamp: int) -> str:
    """生成飞书签名：base64(hmac-sha256(timestamp + "\\n" + secret))"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


async def _build_card(item: MonitorItem) -> dict:
    """将单条监控内容构建为飞书交互式卡片（包含 AI 总结）"""
    
    # 平台映射和细化
    platform_mapping = {
        "twitter": "Twitter/X",
        "reddit": "Reddit", 
        "github": "GitHub",
        "hackernews": "HackerNews",
        "rss": "RSS"
    }
    platform_label = platform_mapping.get(item.platform.value, item.platform.value)
    
    # 从 URL 提取更详细的平台信息（特别是 RSS）
    platform_detail = ""
    if item.url:
        if "techcrunch.com" in item.url:
            platform_detail = "TechCrunch"
        elif "wired.com" in item.url:
            platform_detail = "Wired"
        elif "theverge.com" in item.url:
            platform_detail = "The Verge"
        elif "arstechnica.com" in item.url:
            platform_detail = "Ars Technica"
        elif "technologyreview.com" in item.url:
            platform_detail = "MIT Tech Review"
        elif "venturebeat.com" in item.url:
            platform_detail = "VentureBeat"
        elif "producthunt.com" in item.url:
            platform_detail = "Product Hunt"
        elif "dev.to" in item.url:
            platform_detail = "Dev.to"
        elif "github.com/trending" in item.url:
            platform_detail = "GitHub Trending"
        elif "news.ycombinator.com" in item.url:
            platform_detail = "HackerNews"
    
    # 组合平台显示
    if platform_detail and platform_detail != platform_label:
        platform_display = f"{platform_label} · {platform_detail}"
    else:
        platform_display = platform_label
    
    # 标题颜色：直接提及用红色，高分用橙色，普通用蓝色
    if item.is_direct_mention:
        color = "red"
    elif item.score >= 70:
        color = "orange"
    else:
        color = "blue"

    # 生成 AI 标题和总结
    title, summary = await _generate_summary_and_title(item.content, platform_display)

    elements = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**来源**\n{platform_display}",
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
                        "content": f"**推荐分**\n{item.score}",
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
                "tag": "lark_md",
                "content": f"**💡 为什么值得看**\n{summary}",
            },
        },
        {
            "tag": "hr",
        },
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"原文：{item.content[:150]}..." if len(item.content) > 150 else f"原文：{item.content}",
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

    # 标题使用 AI 生成的一句话总结
    icon = "🔥" if item.is_direct_mention else "📰"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"content": f"{icon} {title}", "tag": "plain_text"},
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
            # 逐条发卡片（异步生成 AI 总结）
            payloads = []
            for item in to_notify:
                card = await _build_card(item)
                payloads.append(card)

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
