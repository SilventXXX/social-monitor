#!/bin/bash
# Social Monitor - 简单监控脚本
# 使用 Brave 搜索 + OpenClaw 飞书通知

KEYWORDS="AI分身 OR digital twin OR Pika AI OR AI Self OR AI avatar"
FEISHU_TO="oc_aba44f0e48b32b2df69153fa3ff854f0"

# 获取当前时间
NOW=$(date '+%Y-%m-%d %H:%M')

# 搜索 Reddit 相关内容
echo "🔍 搜索 Reddit AI相关内容..."

# 使用 web_search 工具（通过 OpenClaw API）
# 这里只输出日志，实际搜索需要在外部调用

echo "✅ 监控完成: $NOW"
