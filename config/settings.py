"""应用配置，从环境变量加载敏感信息"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./social_monitor.db",
        description="数据库连接 URL",
    )

    # X (Twitter) API - 从 https://developer.x.com 获取
    twitter_bearer_token: Optional[str] = Field(default=None, description="X API Bearer Token")
    twitter_api_key: Optional[str] = Field(default=None, description="X API Key")
    twitter_api_secret: Optional[str] = Field(default=None, description="X API Secret")
    twitter_access_token: Optional[str] = Field(default=None, description="X Access Token")
    twitter_access_token_secret: Optional[str] = Field(default=None, description="X Access Token Secret")
    twitter_user_id: Optional[str] = Field(default=None, description="要监控的 X 用户 ID（用于 mentions）")

    # Reddit API - 从 https://www.reddit.com/prefs/apps 创建 App
    reddit_client_id: Optional[str] = Field(default=None, description="Reddit Client ID")
    reddit_client_secret: Optional[str] = Field(default=None, description="Reddit Client Secret")
    reddit_user_agent: str = Field(
        default="SocialMonitor/1.0",
        description="Reddit User-Agent（建议包含应用名和版本）",
    )
    reddit_username: Optional[str] = Field(default=None, description="要监控的 Reddit 用户名")

    # 监控关键词（逗号分隔，可在 config.yaml 覆盖）
    keywords: str = Field(default="", description="监控关键词，逗号分隔")
    hashtags: str = Field(default="", description="监控 Hashtag，逗号分隔")
    subreddits: str = Field(default="", description="监控的 subreddit，逗号分隔")

    # 通知 - Email
    smtp_host: Optional[str] = Field(default=None, description="SMTP 服务器")
    smtp_port: int = Field(default=587, description="SMTP 端口")
    smtp_user: Optional[str] = Field(default=None, description="SMTP 用户名")
    smtp_password: Optional[str] = Field(default=None, description="SMTP 密码")
    notify_email: Optional[str] = Field(default=None, description="接收通知的邮箱")

    # 通知 - Telegram
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram Bot Token")
    telegram_chat_id: Optional[str] = Field(default=None, description="Telegram Chat ID")

    # 通知 - Webhook
    webhook_url: Optional[str] = Field(default=None, description="Webhook URL（可选）")

    # 通知 - 飞书自定义机器人
    feishu_webhook_url: Optional[str] = Field(default=None, description="飞书机器人 Webhook 地址")
    feishu_secret: Optional[str] = Field(default=None, description="飞书签名密钥（开启签名校验时填写）")

    # AI 评分 - 智谱 API
    kimi_api_key: Optional[str] = Field(default=None, description="AI API Key（智谱/Kimi）")

    # 调度
    poll_interval_minutes: int = Field(default=60, description="轮询间隔（分钟）")

    # 演示模式：无 API 密钥时自动启用
    @property
    def demo_mode(self) -> bool:
        has_twitter = bool(self.twitter_bearer_token)
        has_reddit = bool(self.reddit_client_id and self.reddit_client_secret)
        return not (has_twitter or has_reddit)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
