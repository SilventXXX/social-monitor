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

    # 批量处理，每批最多 10 条，保证每条有足够上下文
    results = []
    batch_size = 10
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
    
    # 内容过短（<30字）无法判断，直接给0分跳过
    short_items = {i for i, item in enumerate(items) if len(item.content.strip()) < 30}
    valid_items = [(i, item) for i, item in enumerate(items) if i not in short_items]

    # 使用连续索引 [0][1][2]，避免 AI 因非连续索引返回错误数量
    items_text = "\n\n".join(
        f"[{seq}] {item.content[:200]}"
        for seq, (_, item) in enumerate(valid_items)
    )

    prompt = f"""你是一个严格的信息筛选助手。对每条内容进行严格的三级评分。

用户监控需求：
{requirements}

【第一级：范围判断】（必须严格执行）
先判断内容是否在监控范围内：

✅ 【范围内】必须是以下之一：
- AI在社交/陪伴/连接场景的应用
- AI社交助手、数字分身、AI陪伴产品
- A2A社交网络、AI帮助人与人连接
- OpenClaw生态中的C端产品动态
- 基于OpenClaw构建的社交类应用、用户增长、产品创新

❌ 【范围外 - 直接给0分】包括但不限于：
- VC/风险投资/投资分析/估值类（除非是AI社交产品融资）
- 纯技术教程、代码实现、开发文档
- 学术论文、理论研究
- 企业级AI服务、B端产品
- 通用AI助手（如GPT、Claude本身的功能更新）
- AI在医疗/金融/制造等行业的应用（非社交场景）
- 硬件产品（除非是AI陪伴硬件）

【第二级：范围外细分】
如果判断为范围外，给以下分数：
- 完全无关（如VC投资、纯技术教程）：0分
- 弱相关（如AI行业报告、通用AI新闻）：10-20分

【第三级：范围内评分】（仅对范围内内容）
对范围内的内容，根据以下维度：
- 内容价值（40%）：信息是否新颖、有洞察，产品/商业模式是否值得关注
- 竞争相关度（35%）：是否涉及竞品动态、用户增长、融资、大厂入场
- 用户洞察（25%）：是否包含真实用户反馈、场景、痛点

评分标准：
- 90-100分：非常相关且高价值（如竞品重大发布、重要融资、用户里程碑）
- 70-89分：相关且有价值（如产品更新、功能介绍、使用案例）
- 50-69分：弱相关（如行业分析中提到相关概念，但非重点）

【输出要求】
只返回分数，范围外内容必须给0-20分，不要给中间分数。

待评分内容：
{items_text}

返回 JSON：{{"scores": [分数0, 分数1, ...]}}
只返回JSON，不要解释。"""

    # 全部是短内容则跳过 AI
    if not valid_items:
        return [(item, 0) for item in items]

    try:
        resp = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        logger.info(f"AI评分原始返回: {text[:500]}")

        if "```" in text:
            parts = text.split("```")
            for part in parts:
                if "{" in part and "}" in part:
                    text = part.replace("json", "").strip()
                    break

        data = json.loads(text)
        ai_scores = data.get("scores", [])

        # 合并短内容(0分)和AI评分结果
        # 处理 AI 返回数量不匹配的情况：用 AI 返回的分数填充，不够的给默认分50
        final_scores = {}
        
        # 短内容给 0 分
        for i in short_items:
            final_scores[i] = 0
        
        # AI 评分的内容
        for seq, (orig_idx, _) in enumerate(valid_items):
            if seq < len(ai_scores):
                final_scores[orig_idx] = max(0, min(100, int(ai_scores[seq])))
            else:
                # AI 返回分数不够，给默认分 50
                final_scores[orig_idx] = 50
        
        if len(ai_scores) != len(valid_items):
            logger.warning(f"AI评分数量不匹配: 期望{len(valid_items)}, 实际{len(ai_scores)}, 缺失的用50分填充")
        
        return [(item, final_scores.get(i, 50)) for i, item in enumerate(items)]
    except Exception as e:
        logger.exception("AI 评分失败: %s", e)
        return [(item, 50) for item in items]
