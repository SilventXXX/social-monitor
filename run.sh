#!/bin/bash
cd "$(dirname "$0")"

# 若不存在 .env，从 .env.example 复制
if [ ! -f .env ]; then
  echo "未找到 .env，从 .env.example 复制..."
  cp .env.example .env
  echo "已创建 .env，可直接运行。配置 API 密钥后可监控真实数据。"
fi

# 激活虚拟环境（若存在）
if [ -d .venv ]; then
  source .venv/bin/activate
elif [ -d venv ]; then
  source venv/bin/activate
fi

echo ""
echo "启动 Social Monitor..."
echo "打开 http://localhost:8000 查看面板"
echo ""

exec uvicorn api.main:app --host 0.0.0.0 --port 8000
