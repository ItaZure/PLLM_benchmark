# 流程与操作指南

## 安全说明

本项目是个人本地工具，**未做任何鉴权**。请勿将 `web`(8080) / `api`(8000) / `db`(5432) 端口暴露到公网。

---

## 目录结构

```
PLLM_benchmark/
├── app/
│   ├── main.py              # FastAPI 入口，CORS，挂载 /api 路由
│   ├── core/config.py       # pydantic-settings 读环境变量
│   ├── db/
│   │   ├── base.py          # DeclarativeBase
│   │   └── session.py       # 异步 engine + session（get_db 依赖）
│   ├── models/              # SQLAlchemy 模型（全部表）
│   ├── schemas/             # Pydantic schema（model, dimension, task, evaluation）
│   ├── services/            # model_test / llm_runner（streaming+判分）/ eval_runner（编排+注册表）
│   └── api/routers/         # health, models, dimensions, tasks, evaluations
├── frontend/
│   ├── chat-models.html / image-models.html   # 模型管理页
│   ├── dimensions.html / tasks.html           # 维度管理 / 任务管理页
│   ├── evaluations.html / evaluations-new.html / evaluation-run.html  # 评测列表/新建/运行
│   ├── index.html           # 跳转到 chat-models.html
│   └── assets/              # app.js（共享）+ 各页控制器 *-page.js
├── alembic/                 # 迁移环境 + versions/
├── alembic.ini
├── docker/
│   ├── entrypoint.sh        # 先 alembic upgrade head 再起 uvicorn
│   └── nginx.conf           # 静态托管前端 + 反代 /api
├── docker-compose.yml       # db + api + web 三服务
├── Dockerfile               # backend 镜像
├── requirements.txt         # 锁版本依赖
└── .env.example
```

---

## 启动项目（Docker Compose）

```bash
# 1. （可选）准备本地 .env，默认值已适配 compose，一般无需改
cp .env.example .env

# 2. 一键启动：db + api + web
docker compose up -d --build

# 3. 验证
curl http://localhost:8080/api/health   # 经 Nginx 反代
curl http://localhost:8000/api/health   # 直连后端
# 期望：{"data":{"status":"ok","database":"ok"},"message":"ok"}

# 前端占位页：http://localhost:8080/
```

服务端口：
- `web`(Nginx) → `http://localhost:8080`
- `api`(FastAPI) → `http://localhost:8000`
- `db`(PostgreSQL) → `localhost:5432`（用户/密码/库均为 pllm / pllm / pllm_benchmark）

`api` 容器启动时 `entrypoint.sh` 会自动执行 `alembic upgrade head` 建表，再以**单 worker** 启动 uvicorn（取消机制依赖单 worker，见概要设计 5.6）。

停止：
```bash
docker compose down          # 停服务，保留数据卷
docker compose down -v       # 连数据卷一起删（清库）
```

---

## 模型管理（阶段 2）

浏览器打开 `http://localhost:8080/` 会跳转到 Chat 模型管理页，左侧导航切换 Chat / 图片生成模型。

页面操作与验证：
1. 右上「新增模型」→ 右侧抽屉填写名称、Base URL、API Key、模型名、默认参数 JSON → 保存
2. 列表行「测试可用性」：状态标签切「测试中」spinner → 回来变「可用」(绿) / 「不可用」(红，hover 看失败原因)
3. 「编辑」：抽屉回填，API Key 留空则不修改（占位提示已设置 + 脱敏值）
4. 「删除」：确认后移除
5. 顶部搜索框按名称/URL/模型名过滤

前端改动无需重建镜像（Nginx 只读挂载 `./frontend`），刷新浏览器即可。

可用性测试失败分类见 `docs/api.md`（连接失败 / 超时 / 401 鉴权 / 429 限流 / 5xx 等）。

可用性测试逻辑 chat 与 image 不同：
- Chat：`GET /v1/models`，404 fallback 到最小 chat 请求。
- 图片：只 `GET /v1/models` 判连通（图片生成走 `/v1/chat/completions`，慢且花钱，不做生成探测）。

> 图片模型（POE 模式）：生成实际走 `/v1/chat/completions`，图片以 markdown 链接在 content 返回，后端正则提取 URL（阶段 3 评测运行实现）。**base URL 配置为不带 `/v1` 后缀**（如 `https://api.poe.com`），否则会 `/v1/v1/models` 404 误判。

> 注：前端不接触明文 API Key，列表只返回脱敏值。

---

## 维度管理 + 任务管理（阶段 3）

左侧导航「Benchmark」组下的「维度管理」「任务管理」。

**维度管理页（dimensions.html）**：
1. 右上「新增维度」→ 抽屉填 name / description / system_prompt（多行）→ 保存
2. 维度为可展开卡片，收起显示 名称 / 描述 / 任务数 / 白名单模型数
3. 展开卡片 → 勾选 chat + image 模型配置白名单 → 点「保存白名单」（全量替换，走 `PUT /dimensions/{id}/whitelist`）
4. 「编辑」改维度信息；「删除」——维度下有任务时后端拒绝（提示先删任务）

**任务管理页（tasks.html）**：
1. 顶部维度筛选下拉（`?dimension_id=` 过滤）
2. 表格：任务名 / 所属维度 / 类型标签 / 提示词前 50 字 / 创建时间 / 编辑删除
3. 「新增任务」→ 抽屉选维度、类型（封闭/开放）、填 prompt；**类型联动**：封闭型显示正则+标准答案，开放型显示评分 rubric
4. 后端按类型校验必填字段（封闭需 regex+answer，开放需 rubric），不满足返回 422

验证要点：新增维度→配白名单→在任务页按该维度筛选→新增封闭/开放任务→回到维度页看任务数+1→尝试删除有任务的维度会被拒绝。

---

## 评测运行（阶段 4，含图片 / 取消 / 删除）

左侧导航「评测」组：**运行评测**（evaluations-new.html，组卷 + 运行）/ **历史评测结果**（evaluations.html，历史报告列表）。

**核心概念（方式 A）**：一个 evaluation = 一次组卷 = 一次运行 = 一份独立历史报告。「运行评测」页每次组卷（选维度→任务+赋分→白名单模型）并创建一个**新评测**后运行一次。运行只发生一次，已运行过的评测不可重跑；要重新评测就再新建。

**运行评测 / 新建（evaluations-new.html）**：
1. 填评测名称 → 选维度（任务和模型都限定在该维度内）
2. 勾选任务并赋分（1-20）；勾选参与模型（维度白名单，chat 与图片均可）
3. 「创建并运行」→ 创建评测后自动 `POST /run` 一次 → 跳到运行页

**运行/进度页（evaluation-run.html?id=）**：
- 顶部状态标签 + 总进度条（completed/total）+ 成功/失败/跳过/取消计数
- 结果表：任务、模型、状态、得分、TTFT、字/秒、字符数、输出预览
- **图片结果**：`output_text` 是图片 URL，成功时用 `<img>` 缩略图渲染（点击原图新窗口打开）
- `status=running` 时每 2s 轮询 `/status` 并刷新；结束自动停止
- 仅 `pending` 且无结果时显示「运行评测」按钮（运行一次即隐藏，不再有「重新运行」）
- `running` 时显示「取消运行」按钮（二次确认）→ `POST /cancel`

**历史评测结果（evaluations.html）**：名称、状态、任务数、模型数、创建时间；每行「查看」进运行页 + 「删除」（二次确认，级联删除 → `DELETE /api/evaluations/{id}`）。

**图片模型执行**（按 `provider_mode`，见 api.md `/run`）：`poe_chat` 走 `/v1/chat/completions` stream=false 正则提取 markdown 图片 URL；`aicodewith_async` 提交 `/v1/images/generations` 后轮询 `/v1/tasks/{id}`。两者 `ttft_ms==total_duration_ms`，字符类指标 null，`score=null` 待盲评；httpx read timeout ≥180s。

**取消**：`POST /cancel` 触发内存 `cancel_event`；chat streaming 循环、信号量入口、图片异步轮询循环均检查中断。已完成结果保留，进行中/未开始记 `cancelled`，评测最终 `status='cancelled'`。

**异步与单 worker**：运行是进程内 asyncio 后台任务，内存注册表 `running_tasks`（`app/services/eval_runner.py`）跟踪，单 worker 前提（取消机制依赖）。每个 task×model 组合用独立 DB session 提交，保证 `/status` 实时进度。

实测：
- chat：「中文写作」封闭选择题（正则 `^C$`）+ POE claude / deepseek 跑通，SSE streaming、TTFT/字符每秒有值、封闭型自动判分正确。
- 图片双模式：FLUX 2 Pro（poe_chat，~15s）+ GPT-Image-2（aicodewith_async，~44s）均成功出图，URL 入库、`<img>` 可渲染。
- 取消：运行中 `POST /cancel`，进行中组合记 `cancelled`，评测转 `cancelled`。
- 删除：`DELETE` 级联移除结果，列表实时刷新。

---

## 评测闭环流程（重构后：盲评在进详情页之前）

**核心：从时序上根除解盲泄露。** 盲评发生在进结果详情页之前——评测中永远进不了详情页。

**创建后分流**（`eval-new-page.js`）：点【创建并运行】→ 创建 + 启动后台运行 →
- 含开放型任务 → 直接跳 `blind-scoring.html?id=`（**不经详情页**）。
- 纯客观题 → 直接跳 `evaluations.html`（历史列表）。

**盲评页（blind-scoring.html?id=）**——两个入口（创建后直接进、列表页【继续盲评】）进的是同一界面：
1. 顶部任务切换条：多个开放型任务逐个盲评。tag：`✓`（已完成）/ `已评/总数`（就绪可评）/ **「生成中」（未就绪，禁用）**。默认定位到第一个「未完成且就绪」的任务。
2. **就绪判断**：某任务所有参评模型都产出结果（`ready`）后方可打分；未就绪时禁用并每 3s 轮询，就绪后自动放开。无需等整场评测跑完，逐任务放开。
3. 任务说明卡：prompt + rubric（选填）+ 满分与折算说明。
4. 该任务所有 `success` 输出打乱、隐名展示为「输出 A/B/C…」卡片（图片输出渲染 `<img>`，点原图）；每卡 1-5 档控件。
5. 全部打分后「提交本任务打分」逐条 `POST .../score`，转到下一个未评任务。
6. 所有开放任务打完 → 评测 `done` → **自动跳 `evaluations.html`**。中途退出（「稍后再评」）→ 列表页显示【继续盲评】。

**折算（用户已确认）**：实际得分 = `round(档位 × 满分 / 5)`，满分即 `score_weight`（5/10/15/20）。例：4 档 × 满分 10 → 8 分。`auto_scored=false`。盲评视图不返回模型名（`blind_id`=result_id，仅附 `model_type` 供选渲染器）。

**状态语义**：`done` = 客观题全跑完 **且** 所有主观题盲评完成。「评测中」（用户可见）= `running`（后台还在跑）**或** `scoring`（盲评未打完，含中途退出）。由 `eval_runner.recompute_status(db, eval_id)` 从 DB 统一推导，运行循环与打分提交共用，终态永不冲突。取消不在盲评中出口——不想要就在列表页删除。

## 历史评测结果列表 / 详情（按状态分流）

- 列表（evaluations.html）操作列按状态：
  - `done` → 【查看】进详情（`evaluation-run.html?id=`）。
  - `running` / `scoring` 归「评测中」徽章；`scoring && has_open_tasks` → 【继续盲评】，否则「运行中」占位（**无查看入口，评测中进不了详情**）。
  - 每行【删除】（级联，二次确认）。
  - **自动刷新**：列表中存在「评测中」（running/scoring）项时每 4s 轮询刷新一次（`setTimeout` 链，非 `setInterval`），跑完自动更新徽章与操作列（评测中→已完成时出现【查看】）；无任何「评测中」项时停止轮询，不空转。
- 详情页（`evaluation-run.html?id=`，仅 `done` 可进，**纯只读**）：无运行/取消/盲评按钮、无进度条、无 status 轮询——进入时必然已 done。结果表含 模型 / 任务 / 状态 / 得分 / TTFT / 字符每秒 / 字符数 / 输出（文本或图片 `<img>`）。得分列标注「自动」（客观）/「盲评」（主观）；顶部「模型汇总（按满分加权）」= `Σscore / Σscore_weight`，按得分降序。
- **后端解盲门控**：`GET /evaluations/{id}` 在 `status != 'done'` 前，开放型 result 的 `model_id`/`model_name` 返回 null（防直接调 API 泄露）；`done` 后才解盲。前端不让评测中的评测进详情，双重防护。
- 统计图表本期 TBA，不做。

**盲评后端**（`app/api/routers/evaluations.py`）：`GET /scoring-sessions`（列表，含 `ready`，就绪才惰性建会话）/ `GET /scoring-sessions/{task_id}`（盲评视图隐名，未就绪 409）/ `POST /scoring-sessions/{task_id}/score`（提交并 `recompute_status`）。

**重构后端到端实测（真实 key）**：
- 混合（开放写作满分 10 + 客观选择满分 5）× deepseek/claude → 创建并运行 → 进盲评 → `scoring` 期间 `GET /evaluations/{id}` 开放型 model_name=null（客观题正常解盲）→ 打 5/2 档 → 折算 10/4 → 评测 `done` → 详情页开放型解盲显示模型名。
- 就绪门控：开放任务 × chat(快)+image(慢~40s)，生成中 `ready=false`、任务视图 409；image 完成后 `ready=true, total=2`。
- 纯客观题：创建并运行直接跳列表，`scoring` 从不出现，直达 `done`，无盲评会话。

---

## 数据库迁移（Alembic）

迁移在容器内自动执行；手动操作时：

```bash
# 生成新迁移（修改模型后）
docker compose run --rm api alembic revision --autogenerate -m "描述"

# 应用到最新
docker compose run --rm api alembic upgrade head

# 回退一步
docker compose run --rm api alembic downgrade -1
```

Alembic 读取 `app/models` 的 `Base.metadata`；`env.py` 会把异步 `DATABASE_URL`（asyncpg）自动换成 psycopg2 同步驱动执行迁移。

---

## 本地开发（不走 Docker，可选）

需要 Python 3.11 与一个可连的 PostgreSQL。

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 把 DATABASE_URL 的 host 从 db 改成 localhost
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
