"""Gmail 订阅邮件采集器

通过 Gmail API (OAuth2) 读取订阅邮件（含退订链接的邮件）。

首次运行会自动打开浏览器完成 Google 授权，之后 token 自动刷新。

使用前准备：
1. 前往 https://console.cloud.google.com/ 创建项目
2. 启用 Gmail API
3. 创建 OAuth2 凭据（桌面应用），下载 JSON 保存为 gmail_credentials.json
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Optional

from config.loader import get_gmail_sender_domains
from .base import RawItem, BaseCollector
from models.item import ItemPlatform

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


GMAIL_API = "https://www.googleapis.com/gmail/v1/users/me"


def _get_authorized_session(credentials_file: str, token_file: str):
    """返回已授权的 requests.Session，使用系统网络栈"""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request, AuthorizedSession

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return AuthorizedSession(creds)


def _extract_text(payload: dict) -> str:
    """递归提取邮件正文，优先 text/plain，其次 text/html"""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if mime == "text/html" and body_data:
        html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        # 去除 HTML 标签，保留文字
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return text

    for part in payload.get("parts", []):
        text = _extract_text(part)
        if text.strip():
            return text

    return ""


def _fetch_gmail_items(
    credentials_file: str,
    token_file: str,
    hours_back: int,
    extra_query: str,
) -> List[RawItem]:
    session = _get_authorized_session(credentials_file, token_file)

    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    domains = get_gmail_sender_domains()
    if not domains:
        logger.warning("gmail_sender_domains 未配置，跳过 Gmail 采集")
        return []
    domain_query = " OR ".join(f"from:(@{d})" for d in domains)
    query = f"({domain_query}) after:{int(since.timestamp())}"
    if extra_query:
        query += f" {extra_query}"

    resp = session.get(f"{GMAIL_API}/messages", params={"q": query, "maxResults": 50}, timeout=30)
    resp.raise_for_status()
    messages = resp.json().get("messages", [])
    logger.info("Gmail 查询到 %d 封邮件", len(messages))

    items: List[RawItem] = []
    for msg in messages:
        try:
            r = session.get(f"{GMAIL_API}/messages/{msg['id']}", params={"format": "full"}, timeout=30)
            r.raise_for_status()
            full = r.json()
            headers = {
                h["name"].lower(): h["value"]
                for h in full.get("payload", {}).get("headers", [])
            }

            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "unknown")
            message_id = headers.get("message-id", msg["id"])
            date_str = headers.get("date", "")

            published_at = None
            if date_str:
                try:
                    published_at = parsedate_to_datetime(date_str).astimezone(timezone.utc)
                except Exception:
                    pass

            body = _extract_text(full.get("payload", {}))
            body_clean = re.sub(r"\s+", " ", body).strip()[:800]

            external_id = hashlib.md5(message_id.encode()).hexdigest()[:16]
            content = subject
            if body_clean:
                content += f"\n\n{body_clean}"

            items.append(
                RawItem(
                    platform=ItemPlatform.GMAIL,
                    external_id=external_id,
                    content=content,
                    author=sender,
                    url=f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}",
                    engagement_count=0,
                    is_direct_mention=False,
                    raw_data=json.dumps({"subject": subject, "from": sender}),
                    published_at=published_at,
                )
            )
        except Exception as e:
            logger.warning("解析邮件失败 [%s]: %s", msg["id"], e)

    return items


class GmailCollector(BaseCollector):
    """Gmail 订阅邮件采集器"""

    def __init__(
        self,
        credentials_file: str = "gmail_credentials.json",
        token_file: str = "gmail_token.json",
        hours_back: int = 24,
        extra_query: str = "",
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.hours_back = hours_back
        self.extra_query = extra_query

    async def collect(self) -> List[RawItem]:
        if not os.path.exists(self.credentials_file):
            logger.debug("gmail_credentials.json 不存在，跳过 Gmail 采集")
            return []

        items = await asyncio.to_thread(
            _fetch_gmail_items,
            self.credentials_file,
            self.token_file,
            self.hours_back,
            self.extra_query,
        )
        logger.info("Gmail 采集到 %d 封邮件", len(items))
        return items
