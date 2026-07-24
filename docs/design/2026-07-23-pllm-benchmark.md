# PLLM Benchmark 概要设计

日期：2026-07-23

---

## 1. 系统架构概述

### 整体架构

前后端分离，本地 Docker 部署，单用户个人工具，无需认证。

```
浏览器（原生 JS + TailwindCSS）
        │  HTTP / SSE
        ▼
FastAPI 后端（Python 3.11）
        │  SQLAlchemy ORM
        ▼
PostgreSQL 数据库
        │
        ▼（外部请求）
各 LLM API（OpenAI-compatible）
```

### 部署结构

```
docker-compose.yml
├── web（Nginx，托管前端静态文件，反代 /api 到后端）
├── api（FastAPI，uvicorn）
└── db（PostgreSQL 15）
```

- 前端静态文件放在 `frontend/` 目录，由 Nginx 直接服务
- 后端统一挂载 `/api` 前缀
- 数据库数据通过 Docker Volume 持久化

---

## 2. 数据库表结构设计

### 2.1 chat_models（Chat 模型）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| name | VARCHAR(100) | 显示名称 |
| api_base_url | VARCHAR(500) | API base URL |
| api_key | VARCHAR(500) | API 密钥 |
| model_name | VARCHAR(200) | 传给 API 的模型名 |
| default_params | JSONB | 默认参数，如 temperature、max_tokens |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 2.2 image_models（图片生成模型）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| name | VARCHAR(100) | 显示名称 |
| api_base_url | VARCHAR(500) | |
| api_key | VARCHAR(500) | |
| model_name | VARCHAR(200) | |
| default_params | JSONB | 默认参数，如 size、quality、style |
| provider_mode | VARCHAR(30) | **平台调用模式，必填**，枚举 `poe_chat` / `aicodewith_async`；决定图片生成走哪条调用流程（见下文）。chat_models 无此字段（chat 只有一种模式） |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

> **为何需要 provider_mode**：同一模型（如 gpt-image-2）在 POE 与 aicodewith 两个平台的调用方式完全不同，无法靠代码自动判断，必须显式配置。**只支持这两种平台模式，不为其他平台（OpenAI 官方等）预留、不做通用化。**

### 2.3 dimensions（评测维度）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| name | VARCHAR(100) | 维度名称，如写作、数学 |
| description | TEXT | 可选描述 |
| system_prompt | TEXT | 该维度固定的系统提示词；评测时作为 system role 传给 LLM，可为空 |
| created_at | TIMESTAMP | |

### 2.4 dimension_model_whitelist（维度模型白名单）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| dimension_id | UUID, FK → dimensions.id | |
| model_id | UUID | 对应 chat_models 或 image_models 的 id |
| model_type | VARCHAR(20) | 'chat' 或 'image' |

> 一个维度可以绑定多个模型；评测时模型选项从这张表过滤。

### 2.5 tasks（评测任务）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| dimension_id | UUID, FK → dimensions.id | |
| name | VARCHAR(200) | 任务名称 |
| task_type | VARCHAR(20) | 'open'（开放型）或 'closed'（封闭型） |
| prompt | TEXT | 任务提示词 |
| scoring_regex | VARCHAR(500) | 封闭型：从输出提取答案的正则 |
| expected_answer | VARCHAR(500) | 封闭型：标准答案 |
| scoring_rubric | TEXT | 开放型：评分说明/rubric |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 2.6 evaluations（评测场次）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| name | VARCHAR(200) | 本次评测名称（可自动生成） |
| status | VARCHAR(20) | 'pending' / 'running' / 'scoring' / 'done' / 'cancelled' |
| created_at | TIMESTAMP | |
| finished_at | TIMESTAMP | nullable |

### 2.7 evaluation_tasks（评测场次-任务关联）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| evaluation_id | UUID, FK → evaluations.id | |
| task_id | UUID, FK → tasks.id | |
| score_weight | INTEGER | 该任务赋分，1-20，默认 1 |

### 2.8 evaluation_models（评测场次-模型关联）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| evaluation_id | UUID, FK → evaluations.id | |
| model_id | UUID | |
| model_type | VARCHAR(20) | 'chat' 或 'image' |

### 2.9 results（评测结果）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| evaluation_id | UUID, FK → evaluations.id | |
| task_id | UUID, FK → tasks.id | |
| model_id | UUID | |
| model_type | VARCHAR(20) | |
| output_text | TEXT | 模型输出内容 |
| ttft_ms | FLOAT | 首字响应时间（ms） |
| total_duration_ms | FLOAT | 总生成耗时（ms） |
| output_char_count | INTEGER | 输出字符数，`len(output_text)` |
| char_per_sec | FLOAT | 生成速度（字符/秒） |
| score | FLOAT | nullable，封闭型自动填写，开放型人工填写 |
| auto_scored | BOOLEAN | 是否已自动判分 |
| status | VARCHAR(20) | 'success' / 'failed' / 'cancelled' |
| error | TEXT | nullable，失败或取消时的原因 |
| created_at | TIMESTAMP | |

### 2.10 open_scoring_sessions（开放型盲评会话）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID, PK | |
| evaluation_id | UUID, FK → evaluations.id | |
| task_id | UUID, FK → tasks.id | |
| shuffled_order | JSONB | result_id 列表，打乱顺序，用于前端展示 |
| current_index | INTEGER | 当前评到第几条 |
| completed | BOOLEAN | 该任务盲评是否完成 |
| created_at | TIMESTAMP | |

---

## 3. 后端 API 接口设计

统一前缀：`/api`，响应格式：`{"data": ..., "message": "ok"}`，错误：`{"detail": "..."}`

### 3.1 模型管理

#### Chat 模型

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/models/chat | 列表 |
| POST | /api/models/chat | 新增 |
| PUT | /api/models/chat/{id} | 修改 |
| DELETE | /api/models/chat/{id} | 删除 |
| POST | /api/models/chat/{id}/test | 可用性测试 |

POST /api/models/chat 请求体：
```json
{
  "name": "GPT-4o",
  "api_base_url": "https://api.openai.com",
  "api_key": "sk-xxx",
  "model_name": "gpt-4o",
  "default_params": {"temperature": 0.7, "max_tokens": 2048}
}
```

POST /api/models/chat/{id}/test 响应：
```json
{
  "data": {
    "available": true,
    "error": null
  }
}
```
> 测试逻辑：先调 `GET /v1/models`，若 404 则 fallback 发一条最小 chat 请求（`messages: [{"role":"user","content":"hi"}]`, `max_tokens: 1`）

#### 图片生成模型

与 Chat 模型结构相同，路径为 `/api/models/image`，字段中 `default_params` 内容不同（size、quality 等），并**多一个必填字段 `provider_mode`**（`poe_chat` / `aicodewith_async`，枚举校验）。create/update 请求体需带 `provider_mode`；列表/详情响应返回该字段。

> **可用性测试逻辑（图片模型专用，两种模式通用）**：只调 `GET {api_base_url}/v1/models`，返回 <400 即判可用。**不做**任何生成级 fallback（不打 `/v1/chat/completions`、也不打 `/v1/images/generations`）——图片生成慢且花钱，不适合作连通性探测。POE 与 aicodewith 两平台的 `GET /v1/models` 都通。

图片生成的实际调用分两种模式（`provider_mode` 决定），详见第 5 节评测主流程：

> **① `poe_chat`（POE 同步模式，base `https://api.poe.com`，已实测）**：
> 图片生成**走 `POST /v1/chat/completions`**，`stream=False`，与文本模型同端点同格式（`messages` 传 prompt），**不走** `/v1/images/generations`（POE 对其返回 404）。图片以 markdown 链接在 `choices[0].message.content` 返回：
> ```
> ![name.png](https://pfst.cf2.poecdn.net/base/image/xxxx?w=1024&h=1024)
> ```
> 用正则 `!\[[^\]]*\]\((https?://[^\s)]+)\)` 提取 URL 存入 `results.output_text`。
> POE 网关有 ~66s 响应上限，**只适合快模型**（flux-2-pro ~11s、nano-banana-2 ~12s）。base URL **不带** `/v1` 后缀，后端统一拼 `/v1/...`。

> **② `aicodewith_async`（aicodewith 异步任务模式，base `https://api.aicodewith.com`，已实测）**：
> `POST /v1/images/generations`（body `{model, prompt, n}`）**立即返回** task ID + `status:processing`；随后轮询 `GET /v1/tasks/{task_id}` 直到 `status:completed`，从响应 `result_data[].url`（或 `results[]`）取图片 URL 存入 `output_text`。**不受单请求时长限制**，适合慢模型（gpt-image-2 ~38s）。
> 背景：gpt-image-2 官方本是同步端点，**异步是 aicodewith 平台自己的封装**，非模型/官方行为——避免后人误以为该模型天生异步。

### 3.2 维度管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/dimensions | 列表（含白名单模型） |
| POST | /api/dimensions | 新增 |
| PUT | /api/dimensions/{id} | 修改名称/描述/system_prompt |
| DELETE | /api/dimensions/{id} | 删除（级联校验：有关联任务时拒绝） |
| PUT | /api/dimensions/{id}/whitelist | 更新模型白名单（全量替换） |

PUT /api/dimensions/{id}/whitelist 请求体：
```json
{
  "models": [
    {"model_id": "uuid", "model_type": "chat"},
    {"model_id": "uuid", "model_type": "image"}
  ]
}
```

### 3.3 任务管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/tasks | 列表，支持 ?dimension_id= 过滤 |
| POST | /api/tasks | 新增 |
| PUT | /api/tasks/{id} | 修改 |
| DELETE | /api/tasks/{id} | 删除 |

POST /api/tasks 请求体：
```json
{
  "dimension_id": "uuid",
  "name": "三角函数化简",
  "task_type": "closed",
  "prompt": "化简 sin²x + cos²x",
  "scoring_regex": "^1$",
  "expected_answer": "1",
  "scoring_rubric": null
}
```

### 3.4 评测管理

#### 创建并运行评测

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/evaluations | 评测列表 |
| POST | /api/evaluations | 创建评测（含任务、模型、赋分） |
| GET | /api/evaluations/{id} | 评测详情 |
| POST | /api/evaluations/{id}/run | 启动运行（异步） |
| POST | /api/evaluations/{id}/cancel | 取消正在运行的评测 |
| GET | /api/evaluations/{id}/status | 轮询运行状态 |

POST /api/evaluations 请求体：
```json
{
  "name": "2026-07 数学专项",
  "tasks": [
    {"task_id": "uuid", "score_weight": 5},
    {"task_id": "uuid", "score_weight": 3}
  ],
  "models": [
    {"model_id": "uuid", "model_type": "chat"}
  ]
}
```

POST /api/evaluations/{id}/run：后端异步执行所有 task × model 的组合请求，将结果写入 results 表。

POST /api/evaluations/{id}/cancel：请求取消正在运行的评测。后端设置取消标志，中断尚未开始或正在进行的 streaming 请求；已完成的结果保留。响应：
```json
{
  "data": {
    "status": "cancelled",
    "completed": 4,
    "cancelled": 6
  }
}
```
> 仅当 status 为 'running' 时可取消；非运行状态返回 409。

GET /api/evaluations/{id}/status 响应：
```json
{
  "data": {
    "status": "running",
    "total": 10,
    "completed": 4,
    "failed": 0,
    "cancelled": 0
  }
}
```

#### 评测结果

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/evaluations/{id}/results | 结果列表 |

响应条目：
```json
{
  "result_id": "uuid",
  "model_name": "GPT-4o",
  "task_name": "三角函数化简",
  "output_text": "1",
  "ttft_ms": 312.5,
  "total_duration_ms": 1850.0,
  "output_char_count": 89,
  "char_per_sec": 48.1,
  "score": 5,
  "auto_scored": true,
  "status": "success"
}
```

#### 开放型盲评

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/evaluations/{id}/scoring-sessions | 获取所有开放型任务的盲评会话列表 |
| GET | /api/evaluations/{eval_id}/scoring-sessions/{task_id} | 获取某任务当前待评条目（不含模型信息） |
| POST | /api/evaluations/{eval_id}/scoring-sessions/{task_id}/score | 提交当前条目得分并推进 |

GET scoring-sessions/{task_id} 响应（盲评中不暴露 model_id）：
```json
{
  "data": {
    "task_name": "描述一幅风景画",
    "rubric": "评分标准...",
    "current_index": 0,
    "total": 3,
    "completed": false,
    "item": {
      "blind_id": "uuid（result_id 的 hash，前端不知道对应哪个模型）",
      "output_text": "模型输出内容..."
    }
  }
}
```

POST score 请求体：
```json
{
  "blind_id": "uuid",
  "score": 8
}
```

### 3.5 LLM 推理（内部，评测时由后端自调）

不暴露给前端，后端 `services/llm_runner.py` 封装：
- **Chat 模型**：使用 `httpx.AsyncClient` + SSE streaming 调用 OpenAI-compatible `POST /v1/chat/completions`，记录 TTFT、总生成耗时和字符速度（见第 5 节）
- **图片生成模型**（POE 模式，已实测）：调 `POST /v1/chat/completions`（与文本模型同端点同格式，**非** `/v1/images/generations`），**`stream=False`**（POE 官方推荐），一次性拿完整响应；从 `choices[0].message.content` 用正则 `!\[[^\]]*\]\((https?://[^\s)]+)\)` 提取 markdown 图片 URL 存入 `output_text`。TTFT 与总生成耗时同义，均为「从发请求到拿到图片 URL 的总耗时」（实测 ~30s）；字符速度不适用，`output_char_count` / `char_per_sec` 置空。**httpx read timeout 须 ≥180s（可配置）**，避免慢模型在服务端已生成成功时被客户端提前切断

---

## 4. 前端页面结构

### 4.1 页面列表

```
/                       → 重定向到 /models/chat
/models/chat            → Chat 模型管理
/models/image           → 图片生成模型管理
/dimensions             → 维度管理（含白名单配置）
/tasks                  → 任务管理（可按维度筛选）
/evaluations            → 评测列表
/evaluations/new        → 新建评测（选任务、赋分、选模型）
/evaluations/:id        → 评测详情（结果列表 + 图表）
/evaluations/:id/run    → 评测运行中（进度条轮询）
/evaluations/:id/score  → 开放型盲评页面
```

### 4.2 导航结构

左侧固定侧边栏：
- 模型管理（Chat / 图片）
- 维度管理
- 任务管理
- 评测管理

### 4.3 主要页面交互流程

#### 模型管理页

- 列表展示：名称、API base URL、模型名、状态标签（待测试 / 可用 / 不可用）
- 点击「新增」→ 侧滑面板填写表单 → 保存
- 点击「测试」→ 发 POST /test，状态实时更新为 spinner → 结果回来后更新标签
- 不可用时 hover 标签显示 tooltip 说明失败原因

#### 维度管理页

- 列表：维度名、模型白名单数量、任务数量
- 新增/编辑维度：名称、描述、system_prompt（多行文本框）
- 点击维度 → 展开面板，显示已绑定模型、多选框添加/移除模型

#### 任务管理页

- 顶部筛选维度下拉框
- 列表：任务名、维度、类型、提示词前 50 字
- 新增/编辑弹窗：根据任务类型动态展示封闭型字段（正则 + 标准答案）或开放型字段（rubric）

#### 新建评测页 `/evaluations/new`

三步流程（step indicator）：
1. 选择任务并赋分
2. 选择模型（从白名单过滤）
3. 确认并提交

#### 评测运行页 `/evaluations/:id/run`

- 进度条 + 当前完成数/总数，每 2s 轮询 `GET /api/evaluations/{id}/status`
- 「取消」按钮：调 `POST /api/evaluations/{id}/cancel`，确认后中断运行，已完成结果保留
- 完成后自动跳转到评测详情页
- 若存在开放型任务，显示「进入盲评」入口按钮

#### 盲评页 `/evaluations/:id/score`

- 左侧：任务列表，标记已完成/未完成
- 右侧：当前任务描述 + rubric + 单条输出文本
- 打分输入框（整数）+ 「提交并下一条」按钮
- 所有任务全部完成后显示「查看结果」

#### 评测详情页 `/evaluations/:id`

- 顶部汇总：参与模型数、任务数、总得分排行
- 表格：模型 | 任务 | 得分 | 输出 | TTFT | 字符速度
- 表格支持按模型或维度分组切换

---

## 5. 评测运行主流程（含 TTFT 和字符速度采集）

> **性能指标口径**：统一采集三个客观值——TTFT（首字响应时间）、总生成耗时、输出字符数。
> 生成速度 = `len(output_text) / 总生成时间`，单位「字符/秒」。不做中英文加权，直接用 `len(text)`。
> 不使用 token 计数（各厂商切分口径不统一，跨模型对比 token/秒 不公平）。

### 5.1 整体流程

```
POST /api/evaluations/{id}/run
        │
        ▼
后端 BackgroundTask 启动 async 任务
        │
        ├── 遍历 evaluation_tasks × evaluation_models 的笛卡尔积
        │
        ▼（每个 task × model 组合）
llm_runner.run_single(task, model)
        │
        ├── 构造 messages：维度有 system_prompt 时先放 {"role":"system","content":dimension.system_prompt}，再放 {"role":"user","content":task.prompt}
        ├── 合并 model.default_params
        ├── 追加 stream: true
        │
        ▼
httpx.AsyncClient.stream("POST", api_base_url + "/v1/chat/completions", ...)
        │
        ├── 记录 t_start = time.monotonic()
        ├── 遍历 SSE 事件流
        │     ├── 每个 chunk 前先检查取消标志（见 5.5），已取消则 break
        │     ├── 收到第一个含文本的 delta chunk
        │     │     └── ttft_ms = (time.monotonic() - t_start) * 1000
        │     └── 累积输出文本片段
        │
        ▼
计算指标：
  - ttft_ms：已记录
  - total_duration_ms = (t_end - t_start) * 1000
  - output_char_count = len(output_text)
  - char_per_sec = output_char_count / (total_duration_ms / 1000)  [字符/秒]
        │
        ▼
写入 results 表（status='success'）
封闭型任务：自动执行正则匹配判分，更新 score、auto_scored=true
开放型任务：score=null，auto_scored=false，等待盲评
        │
        ▼
所有组合完成 → evaluation.status = 'scoring'（若有开放型）或 'done'
若中途被取消 → evaluation.status = 'cancelled'，未完成组合写入 status='cancelled'
```

> **图片模型分支（model_type='image'）**：
> 上面的 SSE streaming 流程仅适用于 chat 模型。图片模型 `run_single` 走独立分支，并**再按 `provider_mode` 分两条子路径**。两者共同点：`ttft_ms == total_duration_ms`（从发请求到拿到图片 URL 的总耗时）；`output_char_count` / `char_per_sec` 置空；提取不到 URL 则 `status='failed'`，error 记录原始响应。
>
> **① `poe_chat`（POE 同步，已实测）**：
> - `POST {base}/v1/chat/completions`，**`stream=False`**（POE 官方推荐：图片/视频/音频类 bot 应以 stream=False 调用）。`t_start` 后一次性 `await` 完整响应。
> - 从 `choices[0].message.content` 用正则 `!\[[^\]]*\]\((https?://[^\s)]+)\)` 提取图片 URL 存入 `output_text`。
> - **超时须放足够大**：httpx read timeout **≥180s（可配置）**。实测 `gpt-image-1` 快（~27-35s），但慢模型（如从 POE 打 gpt-image-2）稳定在 ~66s 被切断（HTTP 000），而平台侧其实已生成成功、积分已扣——即生成成功但连接在响应回传前被提前切断，read timeout 过小会「白扣积分却拿不到结果」。POE 网关 ~66s 上限使该模式只适合快模型。
>
> **② `aicodewith_async`（aicodewith 异步任务，已实测）**：
> - `POST {base}/v1/images/generations`（body `{model, prompt, n}`）立即返回 task ID + `status:processing`。
> - 轮询 `GET {base}/v1/tasks/{task_id}`（间隔如 2-3s，设最大轮询时长上限）直到 `status:completed`，从 `result_data[].url`（或 `results[]`）取图片 URL 存入 `output_text`；`status:failed` 则记为失败。
> - **不受单请求时长限制**，慢模型（gpt-image-2 ~38s）用此模式绕开 POE 的 ~66s 上限。异步是 aicodewith 平台封装，非模型/官方行为。
>
> **备注**：图片生成长耗时被中途切断是**图片生成 API 的通病**（撞 socket / 中间层超时），非 POE 独有。实际部署在 Docker 容器内直连 POE 时是否仍受本地观察到的 ~66s 限制，**待第 4 阶段实测确认**。

> **调用路径与 stream/超时约定汇总**：
> | 模型类型 / 模式 | 端点 | stream | 超时（httpx read） |
> |---|---|---|---|
> | chat | `/v1/chat/completions` | `True` | 维持原设计（streaming 逐 chunk） |
> | image · poe_chat | `/v1/chat/completions` | `False` | ≥180s，可配置 |
> | image · aicodewith_async | `/v1/images/generations` + 轮询 `/v1/tasks/{id}` | 不适用 | 单请求短；靠轮询总时长上限控制 |

### 5.2 SSE 解析关键逻辑（Python 伪代码）

```python
async def run_single(task, model, dimension) -> RunResult:
    messages = []
    if dimension.system_prompt:
        messages.append({"role": "system", "content": dimension.system_prompt})
    messages.append({"role": "user", "content": task.prompt})

    payload = {
        "model": model.model_name,
        "messages": messages,
        "stream": True,
        **model.default_params,
    }
    headers = {"Authorization": f"Bearer {model.api_key}"}

    t_start = time.monotonic()
    ttft_ms = None
    chunks = []

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{model.api_base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            async for line in resp.aiter_lines():
                # 每个 chunk 前检查取消标志，命中则主动中断 streaming
                if cancel_event.is_set():
                    return RunResult(status="cancelled",
                                     output_text="".join(chunks))
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                chunk = json.loads(raw)

                # 提取 delta 文本
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta and ttft_ms is None:
                    ttft_ms = (time.monotonic() - t_start) * 1000

                chunks.append(delta)

    t_end = time.monotonic()
    output_text = "".join(chunks)

    duration_s = t_end - t_start
    output_char_count = len(output_text)
    char_per_sec = output_char_count / duration_s if duration_s > 0 else 0

    return RunResult(
        output_text=output_text,
        ttft_ms=ttft_ms,
        total_duration_ms=duration_s * 1000,
        output_char_count=output_char_count,
        char_per_sec=char_per_sec,
        status="success",
    )
```

### 5.3 并发控制

- 同一评测内，所有 task × model 组合以 `asyncio.gather` 并发执行
- 为避免对同一 API 过载，可加 `asyncio.Semaphore(n=5)` 限制同时进行的请求数

### 5.4 封闭型自动判分

规则：
- `scoring_regex` 默认 `[A-D]`（选择题；建任务时前端预填，可编辑以应对数学题等其他题型）。
- 用 `re.search` 取**第一个**匹配（不做"取最后一个"的兜底——靠系统提示词引导模型直接报选项；模型若啰嗦输出不额外处理）。
- 提取值：正则**有捕获组**时取 `group(1)`（如 `ans\{(\d+)\}` → `42`），**无捕获组**时取 `group(0)`（如 `[A-D]` → `B`）。
- 提取值 == `expected_answer` → 全分（score_weight），否则 0 分。不兼容小写。

```python
import re

def auto_score(result: RunResult, task: Task, score_weight: int) -> float:
    match = re.search(task.scoring_regex, result.output_text, re.DOTALL)
    if not match:
        return 0
    # 有捕获组取 group(1)，否则取整个匹配 group(0)
    extracted = (match.group(1) if match.groups() else match.group(0)).strip()
    if extracted == task.expected_answer.strip():
        return score_weight  # 全分
    return 0
```

### 5.5 开放型盲评流程

```
evaluation.status = 'scoring'
        │
前端打开 /evaluations/:id/score
        │
GET /api/evaluations/{id}/scoring-sessions
  → 后端查询所有 open 型 task，为每个 task 创建（如未存在）scoring_session，
    打乱 result_id 顺序存入 shuffled_order
        │
对每个 task，逐条取 blind_id + output_text（不含 model_id）展示
        │
用户打分 → POST score → 后端写入 results.score，推进 current_index
        │
所有 task 的 session 全部 completed
        │
evaluation.status = 'done'
```

### 5.6 异步任务管理与取消

**运行任务的跟踪**

- 后端进程内维护一个全局注册表 `running_tasks: dict[eval_id, RunContext]`
- `RunContext` 包含：
  - `task: asyncio.Task` — `run()` 启动时创建的顶层协程任务
  - `cancel_event: asyncio.Event` — 取消信号
- `POST /run` 时创建 `RunContext` 并登记；评测结束（done / cancelled）时移除
- 单进程 uvicorn worker 假设下注册表在内存即可；若多 worker，需改用 DB 标志位轮询（本期单 worker，暂用内存）

**取消的传播**

`POST /cancel` 的处理：
1. 校验 evaluation.status == 'running'，否则返回 409
2. 从注册表取出 `RunContext`，`cancel_event.set()`
3. 立即返回，实际中断异步进行

取消信号在两个层面生效：
- **未开始的组合**：`run()` 的调度循环在取出下一个 task × model 前检查 `cancel_event`，命中则跳过，直接标记 `status='cancelled'`
- **进行中的 streaming**：`run_single` 每收到一个 SSE 行前检查 `cancel_event`（见 5.2），命中则跳出循环，`httpx` 的 `stream` 上下文退出会关闭底层连接，中断请求

**取消后的结果处理**

- 已成功完成的组合：结果保留，`status='success'`，得分照常
- 进行中被打断的组合：写入 results，`status='cancelled'`，保存已收到的部分文本，指标字段置空（不参与统计）
- 未开始的组合：写入 results，`status='cancelled'`，`output_text` 为空
- `evaluation.status = 'cancelled'`，`finished_at` 记录取消时刻
- 结果页对 `status != 'success'` 的条目单独标注，统计只计入 success

---

## 6. 已确认结论

1. **图片生成模型的调用方式与性能口径**（已实测修正）：图片模型对接 **POE 与 aicodewith 两个平台，调用方式完全不同，靠 `image_models.provider_mode` 字段（`poe_chat` / `aicodewith_async`）显式区分**，只支持这两种、不通用化。
   - `poe_chat`（POE 同步）：走 `POST /v1/chat/completions`（**非** `/v1/images/generations`），`stream=False`（POE 官方推荐），图片以 markdown 链接返回在 `content`，正则提取 URL；POE 网关 ~66s 上限，只适合快模型；httpx read timeout ≥180s（可配置），避免慢模型服务端已生成成功却因连接被切断而白扣积分。
   - `aicodewith_async`（aicodewith 异步）：`POST /v1/images/generations` 建任务 → 轮询 `GET /v1/tasks/{id}` → 取 `result_data[].url`；不受单请求时长限制，适合慢模型（gpt-image-2 ~38s）。异步是 aicodewith 平台封装，非模型/官方行为。
   - 两模式性能口径一致：非 streaming，TTFT=总生成耗时，字符速度不适用。可用性测试两模式都仅靠 `GET /v1/models`，不做生成级探测。图片长耗时被切断是图片生成 API 通病，Docker 内实际限制待第 4 阶段实测。
2. **统计图表**：本期不实现，保持 TBA，后续再补充设计。
3. **性能指标口径**：弃用 token 计数与 tiktoken 方案（各厂商 token 切分口径不统一，跨模型对比不公平）。统一采集三个客观值——TTFT、总生成耗时、输出字符数；生成速度 = `len(output_text) / 总生成时间`，单位「字符/秒」，不做中英文加权。数据库、API、streaming 采集逻辑已全部改为字符数/字符速度。
4. **评测运行支持中途取消**：已支持。方案见 5.6——内存注册表跟踪运行中评测，`asyncio.Event` 传播取消信号，中断进行中的 streaming 请求；已完成结果保留，未完成组合标记为 cancelled。取消端点为 `POST /api/evaluations/{id}/cancel`。
