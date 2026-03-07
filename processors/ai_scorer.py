"""AI 相关性评分

使用 Kimi API（OpenAI 兼容格式）对采集内容打相关性分，
并支持从自然语言需求描述中提取关键词。
"""

import json
import logging
from typing import List, Optional

from openai import AsyncOpenAI

from config.settings import settings
from collectors.base import RawItem

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is not None:
        return _client
    if not settings.kimi_api_key:
        return None
    _client = AsyncOpenAI(
        api_key=settings.kimi_api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )
    return _client


async def extract_keywords(requirements: str) -> List[str]:
    """从自然语言需求中提取关键词列表"""
    client = _get_client()
    if not client:
        logger.warning("未配置 KIMI_API_KEY，跳过关键词提取")
        return []

    prompt = f"""你是一个信息监控助手。用户描述了他的监控需求，请提取出适合用于内容过滤的英文关键词列表。

用户需求：
{requirements}

要求：
- 提取 10-20 个关键词
- 包含英文关键词（因为信息源主要是英文）
- 包含品牌名、产品名、技术术语
- 返回 JSON 格式：{{"keywords": ["keyword1", "keyword2", ...]}}
- 只返回 JSON，不要其他内容"""

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        # 提取 JSON
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        data = json.loads(text)
        keywords = data.get("keywords", [])
        logger.info("AI 提取关键词 %d 个: %s", len(keywords), keywords)
        return keywords
    except Exception as e:
        logger.exception("关键词提取失败: %s", e)
        return []


async def score_items_relevance(
    items: List[RawItem],
    requirements: str,
) -> List[tuple[RawItem, int]]:
    """批量对内容打相关性分（0-100），返回 (item, score) 列表"""
    client = _get_client()
    if not client or not requirements:
        # 无 AI 时返回默认分 50
        return [(item, 50) for item in items]

    if not items:
        return []

    # 批量处理，每批最多 20 条，控制 token 消耗
    results = []
    batch_size = 20
    for i in range(0, len(items), batch_size):
        batch = items[i: i + batch_size]
        batch_results = await _score_batch(client, batch, requirements)
        results.extend(batch_results)
    return results


async def _score_batch(
    client: AsyncOpenAI,
    items: List[RawItem],
    requirements: str,
) -> List[tuple[RawItem, int]]:
    items_text = "\n\n".join(
        f"[{idx}] 来源:{item.platform.value} 标题/内容:{item.content[:200]}"
        for idx, item in enumerate(items)
    )

    prompt = f"""你是一个信息筛选助手。根据用户的监控需求，对每条内容打相关性分（0-100）。

用户需求：
{requirements}

待评分内容：
{items_text}

评分标准：
- 90-100：高度相关，直接涉及用户关注的核心内容
- 60-89：相关，有参考价值
- 30-59：弱相关，勉强值得关注
- 0-29：不相关，可忽略

返回 JSON 格式：{{"scores": [分数0, 分数1, ...]}}
scores 数组长度必须和内容条数一致，只返回 JSON。"""

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        data = json.loads(text)
        scores = data.get("scores", [])

        if len(scores) != len(items):
            logger.warning("AI 评分数量不匹配，使用默认分 50")
            return [(item, 50) for item in items]

        return [(item, max(0, min(100, int(s)))) for item, s in zip(items, scores)]
    except Exception as e:
        logger.exception("AI 评分失败: %s", e)
        return [(item, 50) for item in items]
