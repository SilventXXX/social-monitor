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
from config.loader import get_min_score_to_notify, get_requirements, get_tara_context
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


def _extract_original_title(content: str) -> str:
    """从 content 第一行提取原始标题"""
    first_line = content.split("\n")[0].strip()
    return first_line[:80] + "..." if len(first_line) > 80 else first_line


async def _generate_summary(content: str, platform: str) -> str:
    """使用 AI 生成摘要，返回 summary 字符串"""
    client = _get_ai_client()
    if not client:
        return content[:200] + "..." if len(content) > 200 else content

    tara_context = get_tara_context()
    tara_section = f"\n我们正在做的产品 Tara 的核心上下文：\n{tara_context}\n" if tara_context else ""

    prompt = f"""你是一个资深产品分析师。请对以下监控内容生成摘要。
{tara_section}
内容来源：{platform}
内容：
{content[:1000]}

摘要要求（200-250字，分两段）：
第一段（130字左右）：详细描述这条内容讲了什么，包括产品形态、核心机制、用户场景、数据或融资情况等关键细节，让读者不用看原文就能完整理解。
第二段（60-80字）：结合 Tara 的产品定位，写1条真正有价值的观察——可能是验证了某个方向、暴露了某个盲点、带来可借鉴的机制或竞争信号。不要生硬套用，只说最关键的那一点。

直接输出两段文字，不要任何标签或前缀。"""

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("AI 总结生成失败: %s", e)
        return content[:200] + "..." if len(content) > 200 else content


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
    
    # 格式化发布时间: M月D日 HH:MM
    def format_time(dt):
        if not dt:
            return "未知"
        # 转换为北京时间 (UTC+8)
        from datetime import timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_beijing = dt.astimezone(beijing_tz)
        return dt_beijing.strftime("%m月%d日 %H:%M")
    
    time_str = format_time(item.published_at)
    
    # 平台映射和细化
    platform_mapping = {
        "twitter": "Twitter/X",
        "reddit": "Reddit",
        "github": "GitHub",
        "hackernews": "HackerNews",
        "rss": "RSS",
        "gmail": "Gmail Newsletter",
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
    
    # 标题颜色：直接提及用红色，60+用橙色，50-59用蓝色
    if item.is_direct_mention:
        color = "red"
    elif item.score >= 60:
        color = "orange"
    else:
        color = "blue"

    # 原始标题 + AI 摘要
    title = _extract_original_title(item.content)
    summary = await _generate_summary(item.content, platform_display)

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
                        "content": f"**时间**\n{time_str}",
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

    icon = "🔥" if item.is_direct_mention else "📰"
    if item.score >= 70:
        title = "【必看】" + title
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
            logger.info("没有 ≥%d 分的内容需要通知", min_score)
            return

        logger.info("准备通知 %d 条内容（阈值≥%d）", len(to_notify), min_score)
        
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
            for idx, payload in enumerate(payloads):
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
                        raise Exception(f"飞书API返回错误: {data}")
                    else:
                        logger.info("飞书消息发送成功: %s", payload.get("msg_type", "unknown"))
                except Exception as e:
                    logger.exception("飞书通知失败: %s", e)
                    raise  # 抛出异常让上层知道通知失败

        logger.info("飞书通知已发送 %d 条", len(payloads))
