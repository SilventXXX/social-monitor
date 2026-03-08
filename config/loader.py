"""加载 YAML 监控配置"""

import yaml
from pathlib import Path
from typing import List, Optional

_config_cache: Optional[dict] = None


def get_monitor_config() -> dict:
    """加载监控配置，优先从 YAML 读取"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = Path(__file__).parent / "monitor_config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    _config_cache = raw.get("monitor", {})
    return _config_cache


def get_keywords() -> List[str]:
    """获取监控关键词列表"""
    config = get_monitor_config()
    return config.get("keywords", [])


def get_hashtags() -> List[str]:
    """获取监控 Hashtag 列表"""
    config = get_monitor_config()
    return config.get("hashtags", [])


def get_usernames() -> List[str]:
    """获取监控用户名列表"""
    config = get_monitor_config()
    return config.get("usernames", [])


def get_subreddits() -> List[str]:
    """获取监控 subreddit 列表"""
    config = get_monitor_config()
    return config.get("subreddits", [])


def get_min_score_to_notify() -> int:
    """获取最低通知分数"""
    config = get_monitor_config()
    return config.get("min_score_to_notify", 0)


def get_requirements() -> str:
    """获取自然语言监控需求描述"""
    config = get_monitor_config()
    return config.get("requirements", "")


def get_rss_feeds() -> list:
    """获取用户自定义 RSS 信息源列表"""
    config = get_monitor_config()
    return config.get("rss_feeds", [])


def get_gmail_sender_domains() -> List[str]:
    """获取 Gmail 发件域名白名单"""
    config = get_monitor_config()
    return config.get("gmail_sender_domains", [])


def get_tara_context() -> str:
    """读取本地 Tara 产品上下文文档（不进 git）"""
    from pathlib import Path
    path = Path(__file__).parent.parent / "TARA_PRODUCT_CONTEXT.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    # 只取核心章节：1句话定义、核心判断、当前共识，控制 token 消耗
    sections = []
    keep = False
    for line in text.splitlines():
        if line.startswith("## 1.") or line.startswith("## 2.") or line.startswith("## 17."):
            keep = True
        elif line.startswith("## ") and not any(line.startswith(f"## {n}.") for n in ["1", "2", "17"]):
            keep = False
        if keep:
            sections.append(line)
    return "\n".join(sections)[:2000]
