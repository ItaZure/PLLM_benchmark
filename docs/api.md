# API 文档

统一前缀：`/api`
成功响应：`{"data": ..., "message": "ok"}`
错误响应：`{"detail": "..."}`

> 未做鉴权（个人本地工具），勿暴露公网。

## 阶段 1（已实现）

### GET /api/health

健康检查，包含数据库连通性。

响应：
```json
{
  "data": { "status": "ok", "database": "ok" },
  "message": "ok"
}
```

- `database` 为 `ok` 表示 `SELECT 1` 成功，否则为 `error`。

### GET /

根路径，返回应用名。

```json
{ "data": { "app": "PLLM Benchmark" }, "message": "ok" }
```

## 阶段 2（已实现）：模型管理

Chat 模型与图片生成模型共用同一套接口结构，仅前缀不同：
- Chat：`/api/models/chat`
- 图片：`/api/models/image`

下面以 chat 为例。image 结构基本一致（`default_params` 语义为 size/quality/style 等），但**多一个必填字段 `provider_mode`**（枚举 `poe_chat` / `aicodewith_async`）：
- create（POST）：`provider_mode` 必填，非法/缺失返回 422
- update（PUT）：`provider_mode` 可选，传则更新
- 列表/详情响应：额外返回 `provider_mode`

> `provider_mode` 决定图片生成的调用方式（POE 同步 `/v1/chat/completions` vs aicodewith 异步 `/v1/images/generations` + 轮询），详见概要设计 3.1 / 第 5 节。可用性测试两模式相同，不受影响。

### GET /api/models/chat — 列表

响应 `data` 为数组，每项：
```json
{
  "id": "uuid",
  "name": "GPT-4o",
  "api_base_url": "https://api.openai.com",
  "model_name": "gpt-4o",
  "default_params": {"temperature": 0.7},
  "api_key_masked": "sk-x••••7890",
  "api_key_set": true,
  "test_status": "ok",
  "test_error": null,
  "last_tested_at": "2026-07-23T13:38:25Z",
  "created_at": "...",
  "updated_at": "..."
}
```
> `api_key` 明文不回显，仅返回脱敏后的 `api_key_masked` 与是否已设置 `api_key_set`。
> `test_status`：`null` 未测试 / `ok` 可用 / `error` 不可用。

### POST /api/models/chat — 新增

请求体：
```json
{
  "name": "GPT-4o",
  "api_base_url": "https://api.openai.com",
  "api_key": "sk-xxx",
  "model_name": "gpt-4o",
  "default_params": {"temperature": 0.7, "max_tokens": 2048}
}
```
`api_key` 必填。响应同列表条目。

### PUT /api/models/chat/{id} — 修改

请求体所有字段可选，仅更新传入字段。**`api_key` 留空或不传 = 保持原 key 不变**；传新字符串则替换。

### DELETE /api/models/chat/{id} — 删除

响应：`{"data": {"id": "uuid"}, "message": "ok"}`

### POST /api/models/chat/{id}/test — 可用性测试

无请求体。后端调用外部端点验证，并将结果持久化到该模型（`test_status` / `test_error` / `last_tested_at`）。

响应：
```json
{
  "data": {"available": true, "error": null, "tested_at": "2026-07-23T13:38:25Z"},
  "message": "ok"
}
```

测试逻辑（chat 与 image 不同，代码中显式分开）：

**Chat 模型**（`/api/models/chat/{id}/test`）：
1. `GET {api_base_url}/v1/models`（Bearer 鉴权）验证连通性 + 鉴权
2. 若返回 404，fallback 到最小 chat 请求：`POST {api_base_url}/v1/chat/completions`，body `{model, messages:[{role:"user",content:"hi"}], max_tokens:1}`
3. 超时：connect 5s / read 10s

**图片模型**（`/api/models/image/{id}/test`）：
1. **只调** `GET {api_base_url}/v1/models`，返回 <400 即判可用
2. **不做**任何生成级 fallback（图片生成走 `/v1/chat/completions`，慢 ~30s 且花钱，不适合做连通性测试）
3. 超时同上

> 图片模型的 base URL 需配置为**不带** `/v1` 后缀（如 `https://api.poe.com`），后端统一拼 `/v1/models`。若填成 `https://api.poe.com/v1` 会导致 `/v1/v1/models` → 404 误判为不可用。

失败原因分类（`error` 字段）：
- `连接超时` / `读取超时` / `请求超时`
- `连接失败：地址不可达或端口未开放`
- `401/403 鉴权失败：API key 无效或无权限`
- `429 触发限流`
- `5xx 服务端错误`
- `HTTP {code}`（其它 4xx）

未找到模型时返回 404 `{"detail": "模型不存在"}`。

## 阶段 3（已实现）：维度管理

### GET /api/dimensions — 列表

按 `sort_order` 升序返回（同序再按 created_at 倒序）。前端所有下拉（运行评测、任务管理）与维度管理列表共用此顺序，保证一致。每项包含任务数、排序值与白名单模型（白名单条目带模型显示名）：
```json
{
  "id": "uuid",
  "name": "写作",
  "description": "中文创作",
  "system_prompt": "你是写作助手",
  "task_count": 6,
  "sort_order": 0,
  "whitelist": [
    {"model_id": "uuid", "model_type": "chat", "name": "GPT-4o"}
  ],
  "created_at": "..."
}
```

### PUT /api/dimensions/reorder — 拖拽重排序

请求体：`{"ids": ["uuid", "uuid", ...]}`（维度 id 的完整有序列表）。按列表位置写入 `sort_order`（0、1、2…）；未包含的 id 追加到末尾并保持相对顺序。响应返回重排后的完整列表（同 GET）。

### POST /api/dimensions — 新增

请求体：`{"name": "写作", "description": null, "system_prompt": null}`（仅 name 必填）。新增维度的 `sort_order` 取当前最大值 +1，排到列表末尾。

### PUT /api/dimensions/{id} — 修改

仅更新传入字段（name / description / system_prompt）。

### DELETE /api/dimensions/{id} — 删除

级联校验：**维度下有关联任务时拒绝**，返回 409 `{"detail": "该维度下有 N 个任务，请先删除这些任务再删除维度"}`。无任务时删除成功。

### PUT /api/dimensions/{id}/whitelist — 全量替换白名单

请求体：
```json
{"models": [{"model_id": "uuid", "model_type": "chat"}, {"model_id": "uuid", "model_type": "image"}]}
```
- 全量替换该维度的白名单（先清空再写入）。
- 校验每个 `model_id` 在对应的 `chat_models` / `image_models` 表存在，否则 400 `{"detail": "模型不存在：..."}`。
- 响应返回更新后的维度对象。

维度不存在时返回 404 `{"detail": "维度不存在"}`。

## 阶段 3（已实现）：任务管理

### GET /api/tasks — 列表

支持 `?dimension_id={uuid}` 过滤。每项：
```json
{
  "id": "uuid",
  "dimension_id": "uuid",
  "dimension_name": "数学",
  "name": "三角函数化简",
  "task_type": "closed",
  "prompt": "化简 sin²x + cos²x",
  "scoring_regex": "^1$",
  "expected_answer": "1",
  "scoring_rubric": null,
  "created_at": "...",
  "updated_at": "..."
}
```

### POST /api/tasks — 新增 / PUT /api/tasks/{id} — 修改

请求体（PUT 为全量替换）：
```json
{
  "dimension_id": "uuid",
  "name": "三角函数化简",
  "task_type": "closed",
  "prompt": "...",
  "scoring_regex": "^1$",
  "expected_answer": "1",
  "scoring_rubric": null
}
```

字段校验（422）：
- `task_type` 只能是 `open` / `closed`
- `closed`：`scoring_regex` 与 `expected_answer` 必填
- `open`：`scoring_rubric` 必填
- `dimension_id` 对应维度不存在时返回 400 `{"detail": "所属维度不存在"}`

### DELETE /api/tasks/{id} — 删除

响应：`{"data": {"id": "uuid"}, "message": "ok"}`。任务不存在返回 404。

## 阶段 4（已实现）：评测运行（含图片模型 / 取消 / 删除）

> **概念（方式 A）**：一个 evaluation = 一次组卷 = 一次运行 = 一份独立的历史报告。运行只发生一次；已运行过的评测不可重跑，「重新评测」请新建评测重新组卷。
> chat 与图片模型均已执行。图片模型按 `image_models.provider_mode` 分两种调用模式（见 `/run`）。

### POST /api/evaluations — 创建评测

请求体：
```json
{
  "name": "2026-07 中文写作专项",
  "tasks": [{"task_id": "uuid", "score_weight": 5}],
  "models": [{"model_id": "uuid", "model_type": "chat"}]
}
```
- `score_weight` 1-20；`tasks` / `models` 至少各一项。
- 校验 task_id / model_id 存在（否则 400）。
- 创建后 `status='pending'`。响应 `{"data": {"id", "status"}}`。

### GET /api/evaluations — 列表

每项：`id, name, status, task_count, model_count, created_at, finished_at, has_open_tasks, awaiting_scoring`。
`status`：`pending` / `running` / `scoring`（有开放型待盲评）/ `done` / `cancelled`。
- `has_open_tasks`：该评测是否含开放型任务（需盲评）。
- `awaiting_scoring`：`status == 'scoring'`（盲评未完成）。
- **前端分流**：`running` 与 `scoring` 均对用户显示为「评测中」；只有 `done` 提供【查看】详情入口；`scoring && has_open_tasks` 时提供【继续盲评】入口。评测中不可进详情页（防提前解盲）。

### GET /api/evaluations/{id} — 详情

返回 `tasks`（含 score_weight）、`models`、`results`。

> **解盲门控（重要）**：评测 `status != 'done'` 前，**开放型任务的 result 不返回 `model_id` / `model_name`（均为 null）**，防止在盲评完成前泄露开放型输出的模型归属（即使直接调 API 也防护）。封闭型不受影响。`done` 后开放型才返回真实模型名。前端流程也不让「评测中」的评测进详情页，双重防护。

每条 result：
```json
{
  "result_id": "uuid", "task_id": "uuid", "task_name": "...",
  "model_id": "uuid", "model_type": "chat", "model_name": "...",
  "output_text": "C", "ttft_ms": 1561.8, "total_duration_ms": 1937.1,
  "output_char_count": 1, "char_per_sec": 0.51,
  "score": 5, "auto_scored": true, "status": "success", "error": null
}
```

### POST /api/evaluations/{id}/run — 启动运行（异步，仅一次）

- 后台 asyncio 任务执行所有 task × model 组合，`status='running'`。
- **仅 `status='pending'` 且无结果的评测可启动**；已运行过（非 pending 或已有结果）返回 409 `该评测已运行过，请新建评测重新组卷`；运行中重复调用返回 409。**不再清空旧结果重跑。**
- chat 模型走 `/v1/chat/completions` SSE streaming 采集 TTFT / 总耗时 / 字符数 / 字符每秒。
- **图片模型**按 `provider_mode` 分派，`ttft_ms == total_duration_ms`（出图总耗时），字符类指标为 null，`score=null` 留待盲评：
  - `poe_chat`：`POST {base}/v1/chat/completions`，`stream=false`，user prompt 放 messages（无 system），合并 default_params；从 `choices[0].message.content` 用正则 `!\[[^\]]*\]\((https?://[^\s)]+)\)` 提取图片 URL 存 `output_text`；提取不到 → `status='failed'`，`error` 为响应片段。
  - `aicodewith_async`：`POST {base}/v1/images/generations`（body `{model, prompt, n:1}` + default_params）拿 task id；轮询 `GET {base}/v1/tasks/{id}`（~3s 间隔）直到 `status` 为 completed/failed；完成取 `result_data[].url`（或 `results[]`）存 `output_text`。轮询上限 300s，可被取消中断。
  - 图片请求 httpx read timeout ≥180s。
- 封闭型任务自动判分（见下）；开放型 `score=null` 留待盲评。
- 全部完成后：有开放型（含图片）→ `status='scoring'`，否则 `status='done'`。
- 响应 `{"data": {"status": "running"}}`。

### POST /api/evaluations/{id}/cancel — 取消运行

- 校验评测处于 `running` 且在内存注册表中；否则 409 `评测不在运行中，无法取消`。
- 触发 `cancel_event`：chat streaming 循环、信号量入口、图片异步轮询循环均会检查并中断。
- 已完成的结果保留；进行中/未开始的组合记为 `status='cancelled'`，评测最终 `status='cancelled'`。
- 响应 `{"data": {"status": "cancelling"}}`（实际状态转移由后台任务收尾）。

### DELETE /api/evaluations/{id} — 删除评测

- 级联删除该评测的 results / eval_tasks / eval_models / scoring_sessions（ORM relationship all,delete-orphan）。
- 运行中拒绝：409 `评测运行中，请先取消再删除`。
- 响应 `{"data": {"deleted": true}}`；不存在返回 404。

**封闭型自动判分**：`re.search(scoring_regex, output_text, re.DOTALL)` 取第一个匹配；有捕获组取 `group(1)`，否则 `group(0)`；`strip()` 后 == `expected_answer.strip()` → `score=score_weight`，否则 0；`auto_scored=true`。

### GET /api/evaluations/{id}/status — 运行状态（轮询）

```json
{"data": {"status": "running", "total": 2, "completed": 1,
          "success": 1, "failed": 0, "cancelled": 0, "skipped": 0}}
```
结果逐组合独立提交，`completed` 实时增长。

## 阶段 5（已实现）：开放型盲评打分

**流程时序（重构后，盲评在进详情页之前）**：点【创建并运行】→ 后台开始运行 → 含开放型任务 → **前端直接进盲评界面**（不经详情页）；纯客观题 → 直接进历史列表页。逐任务放开盲评：某开放型任务的所有参评模型都产出结果后（`ready=true`）方可打分，无需等整场评测跑完。全部开放任务打完 → 评测 `done` → 跳历史列表。中途退出 → 列表页显示【继续盲评】接着打。

开放型（含图片开放）任务的结果 `score=null`，评测 `status='scoring'`，等待人工盲评。纯人工打分，不引入 LLM 辅助。

**打分与折算（用户已确认）**：盲评统一按 **1-5 档**；实际得分 = `round(档位 × 满分 / 5)`，满分即该任务 `score_weight`（5/10/15/20）。例：打 4 档、满分 10 → score=8。写入 `results.score`，`auto_scored` 保持 `false`（区分自动/人工）。

### GET /api/evaluations/{id}/scoring-sessions — 会话列表

返回每个开放型任务的盲评会话进度，含 `ready` 就绪标志：
```json
{"data": [{"task_id": "uuid", "task_name": "...", "ready": true,
           "total": 2, "scored": 0, "completed": false}]}
```
- `ready`：该任务所有参评模型是否都已产出结果（结果数 ≥ 模型数）。**会话（`shuffled_order` 快照）只在 `ready` 后惰性创建**，`shuffled_order` = 该任务所有 `success` 结果 result_id 的随机打乱顺序（隐藏模型归属）；未就绪时不建会话，`ready=false, total=0`。前端对未就绪任务禁用并标「生成中」，轮询直到就绪。
- 这样保证盲评集在冻结时已完整，不会漏掉晚到的输出。

### GET /api/evaluations/{eval_id}/scoring-sessions/{task_id} — 某任务盲评视图

返回该任务 prompt + rubric（选填）+ 满分 + 打乱后的盲评条目。**不含 model_id / 模型名**：
```json
{"data": {
  "task_id": "uuid", "task_name": "...", "prompt": "...", "rubric": null,
  "score_weight": 10, "current_index": 0, "total": 2, "completed": false,
  "items": [{"blind_id": "uuid(=result_id)", "model_type": "chat",
             "output_text": "...", "current_score": null}]
}}
```
`model_type` 仅用于前端选渲染器（chat 文本 / image `<img>`），不泄露具体模型。非开放型任务返回 404；**任务未就绪（模型输出未齐）返回 409** `该任务输出尚未全部生成，暂不可盲评`。

### POST /api/evaluations/{eval_id}/scoring-sessions/{task_id}/score — 提交打分

请求体 `{"blind_id": "uuid", "tier": 4}`（tier 1-5）。写入 `results.score = round(tier × score_weight / 5)`，`auto_scored=false`；重推进度（已打分条目数）；该任务全部打分 → session `completed=true`。
**状态由 `eval_runner.recompute_status` 统一推导**（DB 为单一真相源）：生成未完 → `running`；有开放任务且盲评未全完 → `scoring`；否则 → `done`。运行循环与打分提交都调它，二者对终态永不冲突。
响应 `{"data": {"scored", "total", "completed", "eval_status", "score"}}`。`blind_id` 不属于该任务返回 400。

## 后续阶段（规划中，尚未实现）

- 统计图表（本期 TBA，不做）。

## 评测生成模型设置（AI 辅助出题）

### GET /api/settings/generation-model — 读取当前生成模型
返回 `{"data": {"generation_chat_model_id": uuid|null, "model_name": str|null, "display_name": str|null}}`。未设置或所指模型已删除时三者均为 null。

### PUT /api/settings/generation-model — 设置生成模型
请求体 `{"generation_chat_model_id": uuid|null}`（null 清空）。目标 chat 模型不存在返回 400。

### POST /api/tasks/generate — AI 生成一道任务（不落库）
请求体 `{"dimension_id": uuid, "task_type": "open"|"closed", "name_hint": str|null}`。后端读维度 name/description + 全局生成模型，调 `run_chat_single` 让模型返回结构化 JSON，解析后回给前端预填表单（不写库，用户确认后再 POST /tasks）。
- **name_hint（可选）**：用户已填的任务名称。提供时 AI 须围绕该名称出题，且响应 name 强制沿用该名称（后端兜底，不依赖模型回显）；为空则按维度自由出题、AI 自拟名。
- **封闭型强制四选一**：`prompt` 含 A/B/C/D 四选项、正则固定 `[A-D]`、`expected_answer` 校验必须是单个 A/B/C/D 字母，否则 502。
- 未配置生成模型返回 400；生成模型调用失败或输出非合法 JSON 返回 502。
- 响应 `{"data": {"name", "task_type", "prompt", "scoring_regex"?, "expected_answer"?}}`。
