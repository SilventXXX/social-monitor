"""相关性过滤"""

from typing import List

from config.loader import get_keywords, get_hashtags, get_usernames
from collectors.base import RawItem


class FilterProcessor:
    """过滤与关键词/用户名不匹配的内容"""

    @staticmethod
    def process(items: List[RawItem]) -> List[RawItem]:
        """过滤：若未配置任何关键词/用户名，则全部通过；否则至少匹配其一"""
        keywords = [k.lower() for k in get_keywords()]
        hashtags = [h.lower() for h in get_hashtags()]
        usernames = [u.lower() for u in get_usernames()]

        if not keywords and not hashtags and not usernames:
            return items

        result = []
        for item in items:
            text = item.content.lower()
            if any(k in text for k in keywords):
                result.append(item)
                continue
            if any(f"#{h}" in text or h in text for h in hashtags):
                result.append(item)
                continue
            if any(f"@{u}" in text or f"/u/{u}" in text or f"u/{u}" in text for u in usernames):
                result.append(item)
                continue
            if item.is_direct_mention:
                result.append(item)

        return result
