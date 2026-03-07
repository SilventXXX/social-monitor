# 外网信息监控系统 (Social Monitor)

监控 X (Twitter)、Reddit 等平台上与「你」相关且值得关注的内容，包括提及、关键词、Hashtag 等。

## 功能

- **多平台采集**：X (Twitter)、Reddit
- **过滤与评分**：关键词、用户名、Hashtag 匹配；重要性评分
- **去重**：按平台 + 内容 ID 去重
- **通知**：邮件、Telegram、Webhook
- **Web 面板**：浏览器查看、标记已读、手动触发采集
- **演示模式**：零配置即可体验，无需 API 密钥

---

## 零配置体验

无需任何配置，直接运行即可看到演示数据：

```bash
cd social-monitor
pip install -r requirements.txt
./run.sh
```

打开 http://localhost:8000 查看面板，点击「立即采集」获取演示数据。

---

## 5 分钟 Reddit 上手（免费）

配置 Reddit 后即可监控真实内容，无需 X API 付费订阅。

### 1. 创建 Reddit App

1. 登录 https://www.reddit.com
2. 打开 https://www.reddit.com/prefs/apps
3. 点击「create another app...」
4. 填写：name 随意（如 `SocialMonitor`）、类型选「script」
5. 创建后得到 `client_id`（在 app 名称下方）和 `client_secret`

### 2. 配置 .env

```bash
cp .env.example .env
```

在 `.env` 中填写：

```
REDDIT_CLIENT_ID=你的client_id
REDDIT_CLIENT_SECRET=你的client_secret
REDDIT_USER_AGENT=SocialMonitor/1.0
```

### 3. 配置监控关键词

编辑 `config/monitor_config.yaml`，设置要监控的 subreddit 和关键词：

```yaml
monitor:
  keywords: ["你的项目名", "你的品牌"]
  subreddits: ["python", "programming", "你关心的板块"]
```

### 4. 运行

```bash
./run.sh
```

打开 http://localhost:8000，点击「立即采集」即可获取 Reddit 上的相关内容。

---

## 快速开始（完整配置）

### 1. 安装依赖

```bash
cd social-monitor
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env`，填写 API 凭证与通知配置：

```bash
cp .env.example .env
```

编辑 `config/monitor_config.yaml` 配置监控关键词、用户名、subreddit 等。

### 3. 运行

```bash
./run.sh
```

或：

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- 面板: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 调度器会按 `POLL_INTERVAL_MINUTES` 间隔自动采集

### 4. Docker

```bash
docker-compose up -d
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | Web 面板 |
| GET | /status | 运行模式（demo/reddit/full） |
| GET | /items | 获取监控内容列表 |
| POST | /items/{id}/read | 标记已读 |
| POST | /collect | 手动触发采集 |

## 配置说明

### 环境变量 (.env)

- `TWITTER_BEARER_TOKEN`：X API Bearer Token（需付费订阅）
- `TWITTER_USER_ID`：要监控的 X 用户 ID
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`：Reddit App 凭证
- `SMTP_*` / `TELEGRAM_*` / `WEBHOOK_URL`：通知渠道
- `POLL_INTERVAL_MINUTES`：轮询间隔，默认 15

### 监控配置 (config/monitor_config.yaml)

- `usernames`：要监控的用户名/品牌
- `keywords`：关键词
- `hashtags`：Hashtag
- `subreddits`：Reddit 子版块
- `min_score_to_notify`：最低通知分数 (0-100)

## 项目结构

```
social-monitor/
├── config/           # 配置
├── collectors/       # 采集器 (Twitter, Reddit, Demo)
├── processors/       # 过滤、评分、去重
├── notifiers/        # 通知 (邮件、Telegram、Webhook)
├── api/              # FastAPI 后端
├── web/              # Web 面板
├── models/           # 数据模型
├── tasks/            # 采集任务
├── run.sh            # 一键启动
├── docker-compose.yml
└── README.md
```
