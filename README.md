# PLLM Benchmark

个人向的 LLM 评测台：在网页上管理模型与题库，选择不同模型跑评测，查看回答与性能指标（首字响应时间 TTFT、平均每 token 生成速度）。单用户本地工具，无鉴权，请勿暴露到公网。

## 功能

- **模型管理**：Chat 模型与图片生成模型两个独立模块，各自增删改查；一键可用性测试（`GET /v1/models`，404 时 fallback 到最小请求），列表显示可用 / 不可用及失败原因。
- **评测生成模型**：全局单选一个 Chat 模型，用于任务的 AI 辅助出题。
- **维度管理**：按写作、数学、画图等维度组织；配置各维度的模型白名单；卡片支持拖拽重排，顺序在所有下拉中保持一致。
- **任务管理**：任务归属维度，分开放型（人工盲评 + rubric）与封闭型（正则提取答案自动判分）；支持 AI 辅助生成题目（可用已填任务名作为出题提示）。
- **运行评测**：选维度、勾任务并赋分（满分 5/10/15/20），选白名单内模型；开放型任务走盲评（输出随机打乱、隐藏模型归属，逐条打 1-5 档）。
- **历史结果**：评测列表与详情，含每条输出的模型、得分、TTFT、生成速度。

## 技术栈

- 后端：Python 3.11 · FastAPI · SQLAlchemy (async) · Alembic · PostgreSQL 15
- 前端：原生 JS + TailwindCSS (CDN)
- 部署：Docker Compose（Nginx 反代 + FastAPI + Postgres）

## 快速开始

需要 Docker 与 Docker Compose。

```bash
# 1. 准备环境变量（填入各平台的 API key）
cp .env.example .env
# 编辑 .env，至少配置 DATABASE_URL 及所需模型平台的 key

# 2. 启动
docker compose up -d --build

# 3. 应用数据库迁移
docker compose exec api alembic upgrade head
```

访问：

- 前端 http://localhost:8080
- 后端 API http://localhost:8000/api

## 常用命令

```bash
# 改了后端代码后重建并重启 api
docker compose up -d --build api

# 前端是挂载卷，改完直接刷新页面即可（Nginx 已禁用静态资源缓存）

# 新增迁移后应用
docker compose exec api alembic upgrade head

# 查看日志
docker compose logs -f api
```

## 目录结构

```
app/            FastAPI 后端（api/routers、models、schemas、services、db）
alembic/        数据库迁移
frontend/       静态前端（html + assets/*.js）
docker/         nginx.conf
docs/           api.md / schema.md / workflows.md 等设计文档
docker-compose.yml
```

## 说明

- `.env` 含明文 API key，已被 `.gitignore` 排除，切勿提交。
- 无用户鉴权，仅供本机使用。
