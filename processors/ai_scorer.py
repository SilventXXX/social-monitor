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
    """批量评分 - 方案B：标题+前100字，更快更省token"""
    
    # 安全提取标题（第一句或前80字）
    def get_title(content: str) -> str:
        if not content:
            return ""
        # 尝试用句号分割取第一句
        sentences = content.split('.')
        first = sentences[0] if sentences else content
        return first[:80].strip()
    
    items_text = "\n\n".join(
        f"[{idx}] 标题:{get_title(item.content)} | 内容:{item.content[:100]}"
        for idx, item in enumerate(items)
    )

    prompt = f"""你是一个信息筛选助手。根据用户的监控需求，对每条内容进行4维度评分，最终给出综合分（0-100）。

用户监控需求：
{requirements}

4个评分维度（权重）：
- 产品创新度（30%）：是否有新颖的产品形态、交互方式或商业模式
- 竞争威胁（25%）：是否对同类产品构成竞争压力，包含用户增长/融资/大厂入场等信号
- 融资价值（25%）：是否涉及融资、收购、战略合作等资本动向
- 用户洞察（20%）：是否包含真实用户反馈、使用场景、痛点或需求

强制规则（满足任一直接给0分）：
- 纯技术教程或代码实现
- 学术论文或技术研究
- 开发者工具/SDK/API介绍（非C端产品）

待评分内容（标题+前100字）：
{items_text}

返回 JSON：{{"scores": [分数0, 分数1, ...]}}
只返回JSON，不要解释。"""

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        
        # 调试：打印原始返回
        logger.info(f"AI评分原始返回: {text[:500]}")
        
        # 提取JSON
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                if "{" in part and "}" in part:
                    text = part.replace("json", "").strip()
                    break
        
        data = json.loads(text)
        scores = data.get("scores", [])

        if len(scores) != len(items):
            logger.warning(f"AI评分数量不匹配: 期望{len(items)}, 实际{len(scores)}, 返回内容: {text[:200]}")
            return [(item, 50) for item in items]

        return [(item, max(0, min(100, int(s)))) for item, s in zip(items, scores)]
    except Exception as e:
        logger.exception("AI 评分失败: %s", e)
        return [(item, 50) for item in items]
