# 数据库表结构

数据库：PostgreSQL 15
ORM：SQLAlchemy 2.0（异步）
迁移：Alembic（当前 head `af271ec55320`；`ed47d9151b3a` initial → `1587d9d78fd5` 模型测试状态字段 → `af271ec55320` image_models.provider_mode）

主键统一为 UUID（`uuid4` 默认），时间戳为 `TIMESTAMP WITH TIME ZONE`，`server_default now()`。
模型定义位于 `app/models/`。

---

## chat_models（Chat 模型）

`app/models/model.py` → `ChatModel`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| name | VARCHAR(100) | NOT NULL | 显示名称 |
| api_base_url | VARCHAR(500) | NOT NULL | API base URL |
| api_key | VARCHAR(500) | NOT NULL | API 密钥 |
| model_name | VARCHAR(200) | NOT NULL | 传给 API 的模型名 |
| default_params | JSONB | NOT NULL | 默认参数（temperature、max_tokens 等） |
| test_status | VARCHAR(20) | NULL | 可用性测试结果：null 未测试 / 'ok' / 'error' |
| test_error | TEXT | NULL | 测试失败原因（test_status='error' 时） |
| last_tested_at | TIMESTAMPTZ | NULL | 最后一次测试时间 |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

> `test_status` / `test_error` / `last_tested_at` 由 `TestStatusMixin` 提供，阶段 2 迁移 `1587d9d78fd5` 新增。

## image_models（图片生成模型）

`app/models/model.py` → `ImageModel`

结构同 `chat_models`（含 test_status/test_error/last_tested_at），`default_params` 内容为 size、quality、style 等，并**多一个必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| provider_mode | VARCHAR(30) | NOT NULL, default 'poe_chat' | 平台调用模式：`poe_chat`（POE 同步）/ `aicodewith_async`（aicodewith 异步）。chat_models 无此字段 |

> `provider_mode` 由迁移 `af271ec55320` 新增。同一模型在 POE 与 aicodewith 两平台调用方式不同，需显式配置，只支持这两种模式。
> 迁移对现有数据做了 data migration：`api_base_url` 含 `aicodewith` 的置为 `aicodewith_async`，其余置为 `poe_chat`。

## dimensions（评测维度）

`app/models/dimension.py` → `Dimension`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| name | VARCHAR(100) | NOT NULL | 维度名称 |
| description | TEXT | NULL | 可选描述 |
| system_prompt | TEXT | NULL | 维度固定 system 提示词，评测时作为 system role |
| sort_order | INTEGER | NOT NULL, DEFAULT 0 | 手动显示顺序（升序），所有下拉与列表统一按此排序；拖拽重排写入 |
| created_at | TIMESTAMPTZ | NOT NULL | |

## dimension_model_whitelist（维度模型白名单）

`app/models/dimension.py` → `DimensionModelWhitelist`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| dimension_id | UUID | FK → dimensions.id, ON DELETE CASCADE | |
| model_id | UUID | NOT NULL | 指向 chat_models 或 image_models |
| model_type | VARCHAR(20) | NOT NULL | 'chat' / 'image' |

## tasks（评测任务）

`app/models/task.py` → `Task`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| dimension_id | UUID | FK → dimensions.id, ON DELETE RESTRICT | |
| name | VARCHAR(200) | NOT NULL | 任务名称 |
| task_type | VARCHAR(20) | NOT NULL | 'open' / 'closed' |
| prompt | TEXT | NOT NULL | 任务提示词 |
| scoring_regex | VARCHAR(500) | NULL | 封闭型：答案提取正则 |
| expected_answer | VARCHAR(500) | NULL | 封闭型：标准答案 |
| scoring_rubric | TEXT | NULL | 开放型：评分说明 |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

## evaluations（评测场次）

`app/models/evaluation.py` → `Evaluation`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| name | VARCHAR(200) | NOT NULL | 评测名称 |
| status | VARCHAR(20) | NOT NULL, default 'pending' | 'pending'/'running'/'scoring'/'done'/'cancelled' |
| created_at | TIMESTAMPTZ | NOT NULL | |
| finished_at | TIMESTAMPTZ | NULL | 结束/取消时刻 |

## evaluation_tasks（评测场次-任务关联）

`app/models/evaluation.py` → `EvaluationTask`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| evaluation_id | UUID | FK → evaluations.id, ON DELETE CASCADE | |
| task_id | UUID | FK → tasks.id, ON DELETE RESTRICT | |
| score_weight | INTEGER | NOT NULL, default 1 | 赋分 1-20 |

## evaluation_models（评测场次-模型关联）

`app/models/evaluation.py` → `EvaluationModel`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| evaluation_id | UUID | FK → evaluations.id, ON DELETE CASCADE | |
| model_id | UUID | NOT NULL | |
| model_type | VARCHAR(20) | NOT NULL | 'chat' / 'image' |

## results（评测结果）

`app/models/evaluation.py` → `Result`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| evaluation_id | UUID | FK → evaluations.id, ON DELETE CASCADE | |
| task_id | UUID | FK → tasks.id, ON DELETE RESTRICT | |
| model_id | UUID | NOT NULL | |
| model_type | VARCHAR(20) | NOT NULL | |
| output_text | TEXT | NULL | 模型输出 |
| ttft_ms | FLOAT | NULL | 首字响应时间（ms） |
| total_duration_ms | FLOAT | NULL | 总生成耗时（ms） |
| output_char_count | INTEGER | NULL | 输出字符数 |
| char_per_sec | FLOAT | NULL | 生成速度（字符/秒） |
| score | FLOAT | NULL | 封闭型自动 / 开放型人工 |
| auto_scored | BOOLEAN | NOT NULL, default false | 是否已自动判分 |
| status | VARCHAR(20) | NOT NULL, default 'success' | 'success'/'failed'/'cancelled' |
| error | TEXT | NULL | 失败/取消原因 |
| created_at | TIMESTAMPTZ | NOT NULL | |

## open_scoring_sessions（开放型盲评会话）

`app/models/evaluation.py` → `OpenScoringSession`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | UUID | PK | |
| evaluation_id | UUID | FK → evaluations.id, ON DELETE CASCADE | |
| task_id | UUID | FK → tasks.id, ON DELETE RESTRICT | |
| shuffled_order | JSONB | NOT NULL | result_id 列表，打乱顺序 |
| current_index | INTEGER | NOT NULL, default 0 | 已打分条目数（进度） |
| completed | BOOLEAN | NOT NULL, default false | 该任务盲评是否完成 |
| created_at | TIMESTAMPTZ | NOT NULL | |

> 阶段 5 盲评（已实现）：进入盲评时按 (evaluation_id, task_id) 惰性创建会话，`shuffled_order` = 该任务所有 `success` 结果 result_id 随机打乱（隐藏模型归属）。打分写入 `results.score = round(档位 × score_weight / 5)`（档位 1-5），`results.auto_scored` 保持 false 以区分自动/人工。`current_index` 记已打分数，全部打分 → `completed=true`；所有开放任务会话完成 → `evaluations.status` 由 `scoring` 转 `done`。**本阶段无表结构变更。**

## app_settings（全局设置，key-value 单例）

`app/models/setting.py` → `AppSetting`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| key | VARCHAR(100) | PK | 设置项键名 |
| value | TEXT | NULL | 设置项值（字符串存储） |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

> 已知键：`generation_chat_model_id`（AI 辅助出题使用的 Chat 模型 id，指向 chat_models.id；未设置时无此行或 value 为空）。迁移 `b8f2c1a4d9e0`。
