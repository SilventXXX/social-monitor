"""重要性评分

根据互动数、是否直接提及等计算 0-100 的分数。
"""

from typing import List

from collectors.base import RawItem


class ScoreProcessor:
    """计算内容重要性分数"""

    @staticmethod
    def _score_item(item: RawItem) -> int:
        """单条内容评分 0-100"""
        score = 0

        # 直接 @ 提及 +30
        if item.is_direct_mention:
            score += 30

        # 互动数：每 10 个互动 +1，上限 50
        engagement_score = min(50, item.engagement_count // 10)
        score += engagement_score

        # 基础分 20，确保有分
        score += 20

        return min(100, score)

    @staticmethod
    def process(items: List[RawItem]) -> List[tuple[RawItem, int]]:
        """为每条内容计算分数，返回 (item, score) 列表"""
        return [(item, ScoreProcessor._score_item(item)) for item in items]
