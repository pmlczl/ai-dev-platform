# 迭代 4：LangGraph 研发工作流与人工审批模块 —— 设计方案与实施记录

- 状态：**已实施**（2026-11-09 验证通过；PostgreSQL 检查点路径为「未执行」项，见 §10）
- 目标：在 `ai-dev-platform` 中落地基于 LangGraph 的研发工作流编排，用 `interrupt()` 实现人工审批暂停，
  用 PostgreSQL Checkpointer 持久化工作流状态，支持服务重启后恢复。
- 约束：本次**不调用任何大模型**，全部节点为确定性模拟实现。

---

## 1. 范围与边界

| 属于本次范围 | 不属于本次范围 |
| --- | --- |
| 工作流实例与 `thread_id` 的持久化 | 真实大模型调用、Prompt 编排、Agent 决策 |
| 5 个模拟节点 + 退回返工分支 | 前端审批界面（仅交付 API） |
| 人工审批暂停 / 恢复 / 审批记录落库 | 权限体系、登录鉴权、多租户 |
| PostgreSQL Checkpointer 接入 + 本地等价实现 | 分布式任务队列、横向扩容调度 |
| 幂等、重启恢复、并行隔离的自动化测试 | 制品内容质量的智能评估 |

依赖方向保持 `api → services → workflows → models → core`：

- `app/api/v1/endpoints/workflows.py` 只做 HTTP 编排，**不构图、不碰检查点**；
- `app/workflows/` 提供工作流实现与注册表（沿用现有 `BaseWorkflow` / `registry`）；
- `app/services/workflows.py` 负责业务语义（建实例、校验、跑图、记审批）；
- `app/core/` 不出现任何工作流领域概念。

---

## 2. 技术选型与依赖

本机现状（已核实）：

| 包 | 版本 | 状态 |
| --- | --- | --- |
| `langgraph` | 0.6.11 | ✅ 已安装于 `backend/.venv` |
| `langgraph-checkpoint` | 3.0.1 | ✅ 已安装（固定为 3.0.x：langgraph 0.6 要求 `< 4`） |
| `langgraph-checkpoint-postgres` | 3.0.5 | ✅ 已安装（提供 `AsyncPostgresSaver`） |
| `langgraph-checkpoint-sqlite` | 3.0.3 | ✅ 已安装（提供 `AsyncSqliteSaver`） |
| `psycopg[binary]` | 3.x | ✅ 已安装（PostgreSQL 检查点驱动） |
| `aiosqlite` | 0.22.1 | ✅ 已安装 |

关键 API 已在本机核实（`AsyncPostgresSaver.from_conn_string()` / `await saver.setup()` /
`AsyncSqliteSaver.from_conn_string()` / `interrupt(value)` / `Command(resume=...)`）。

**检查点后端可切换**（同一套抽象，两种驱动）：

| 环境 | `WORKFLOW_CHECKPOINT_BACKEND` | 用途 |
| --- | --- | --- |
| 生产 / Docker | `postgres` | 需求一指定实现；检查点表位于独立库 `ai_dev_platform_checkpoints` |
| 本地开发 / 自动化测试 | `sqlite` | 本机无 PostgreSQL，等价验证同一套图与恢复语义 |
| 单元测试 | `memory` | 纯内存，不落盘 |

> 需求一「采用 PostgreSQL Checkpointer」在生产路径上严格实现；本地因无 PG 实例，
> 自动化测试跑在 SQLite 检查点上（同一 `BaseCheckpointSaver` 抽象、同一 `thread_id` 语义）。
> PostgreSQL 路径的真实连通性属于**未执行项**，在交付说明中如实标注。

新增环境变量（同步更新 `.env.example` / `docker-compose.yml` / README）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WORKFLOW_CHECKPOINT_BACKEND` | `sqlite`（生产由 Compose 覆盖为 `postgres`） | 检查点后端 |
| `CHECKPOINT_DATABASE_URL` | 空 | PostgreSQL 检查点 DSN；为空时由 `POSTGRES_*` 拼装并把库名换成 `<db>_checkpoints` |
| `WORKFLOW_SQLITE_CHECKPOINT_PATH` | `backend/.checkpoint/checkpoints.sqlite` | SQLite 检查点文件 |
| `WORKFLOW_DEFAULT_KEY` | `dev_workflow` | 默认工作流注册名 |
| `WORKFLOW_MAX_ITERATIONS` | `3` | 返工迭代上限，超限判定失败 |

---

## 3. 工作流图

### 3.1 节点与边

```
   START
     │
     ▼
 ┌───────────────┐   任务不存在/已删除   ┌───────────────┐
 │  load_task    │ ────────────────────▶ │ fail_workflow │
 └───────────────┘                       └───────────────┘
     │ 载入任务与项目，写入状态、置任务为 in_progress
     ▼
 ┌──────────────────────────┐
 │ generate_demo_artifact   │  生成模拟产物（幂等：相对路径含 workflow_id + iteration）
 └──────────────────────────┘
     │ 产物落库 + 落盘 + 事件日志
     ▼
 ┌────────────────────────┐        校验失败且未超迭代上限        ┌──────────────────────────┐
 │   validate_artifact    │ ─────────────────────────────────▶ │ handle_revision_comments │
 └────────────────────────┘                                    └──────────────────────────┘
     │ 校验通过                                                      │ 记录意见、iteration += 1
     ▼                                                               └───────────┬──────────────┘
 ┌──────────────────┐                                                            │
 │  human_approval  │◀───────────────────────────────────────────────────────────┘
 │  ⚡ interrupt()  │  暂停等待人工审批
 └──────────────────┘
     │                    │                        │
  通过 │               退回 │+修改意见          校验失败自动返工
     ▼                    ▼                        （回到生成节点）
 ┌────────────────────┐   ┌────────────────────┐
 │ complete_workflow  │   │ handle_revision_   │
 │ （任务置 completed）│   │ comments（意见入库）│
 └────────────────────┘   └────────────────────┘
     │                          │
     ▼                          └──▶ generate_demo_artifact（iteration + 1）
    END
```

边定义（`StateGraph`）：

| 源节点 | 条件 | 目标 |
| --- | --- | --- |
| START | — | `load_task` |
| `load_task` | 任务有效 | `generate_demo_artifact` |
| `load_task` | 任务无效 | `fail_workflow` |
| `generate_demo_artifact` | — | `validate_artifact` |
| `validate_artifact` | 通过 | `human_approval` |
| `validate_artifact` | 不通过且 `iteration < max` | `handle_revision_comments` |
| `validate_artifact` | 不通过且 `iteration >= max` | `fail_workflow` |
| `human_approval` | 决定 = 通过 | `complete_workflow` |
| `human_approval` | 决定 = 退回 | `handle_revision_comments` |
| `handle_revision_comments` | — | `generate_demo_artifact` |
| `complete_workflow` / `fail_workflow` | — | END |

> 说明：`validate_artifact` 失败默认直接自动返工（意见由校验器生成），不再占用人工审批；
> 若希望人工先看到失败产物，只需把该条件边改指 `human_approval`，属于一行改动。

### 3.2 节点职责与副作用幂等性

**LangGraph 的关键行为**：`interrupt()` 所在节点在恢复执行时会**从头重跑**，
因此「中断前」的所有副作用必须幂等。下表逐项给出幂等手段。

| 节点 | 职责 | 副作用 | 幂等手段 |
| --- | --- | --- | --- |
| `load_task` | 读任务/项目，校验可启动 | 事件日志、任务状态 | 事件带唯一 `event_key`；状态为绝对赋值 |
| `generate_demo_artifact` | 生成模拟 Markdown 产物并落盘落库 | 文件 + `artifacts` 行 + 事件 | 相对路径固定为 `workflow/{workflow_id}/iteration-{n}/demo-artifact.md`，命中 `uq_artifacts_project_path_version`；先查后写，命中即复用既有行 |
| `validate_artifact` | 校验产物（文件存在、SHA256 一致、必需章节齐全） | 事件日志 | `event_key` 唯一约束，重复插入被忽略 |
| `human_approval` | `interrupt()` 等待人工决定 | `pending_payload`、事件日志 | 状态/载荷为绝对赋值；事件 `event_key` 唯一 |
| `handle_revision_comments` | 意见入库、迭代 +1 | 事件日志、状态 | 绝对赋值 + `event_key` 唯一 |
| `complete_workflow` | 收尾：工作流 `completed`、任务 `completed` | 状态、事件 | 绝对赋值，重复执行结果一致 |
| `fail_workflow` | 终止：工作流 `failed`、记录错误 | 状态、事件 | 绝对赋值 |

**模拟产物的生成规则（确定性，无大模型）**：

- 内容由模板拼装：任务标题、迭代序号、上一轮的修改意见、固定的三个章节
  （`## 需求描述` / `## 实现方案` / `## 验收标准`）；
- 写入临时文件后用既有的 `move_into()` 原子落位（已存在即冲突，不覆盖历史版本）；
- 计算 SHA256 与字节数，写入 `artifacts`（`task_id` + `workflow_instance_id` 关联，
  `review_status = pending`，`stage = development`）。

**模拟校验规则**：

1. 文件存在于存储根目录内；
2. 磁盘文件 SHA256 与 `artifacts.sha256` 一致；
3. 字节数 > 0；
4. 内容包含三个必需章节；
5. 若存在上一轮修改意见，内容必须包含「修改意见」章节（保证返工真的改进了东西）。

### 3.3 工作流状态机（`workflow_instances.status`）

| 状态 | 含义 | 允许的操作 |
| --- | --- | --- |
| `pending` | 实例已创建，尚未跑图 | — |
| `running` | 正在执行节点 | — |
| `waiting_approval` | 停在 `human_approval`，等待人工决定 | `resume`（必须带 decision） |
| `paused` | 因服务重启/异常停在检查点，可继续 | `resume`（不带 decision） |
| `completed` | 正常完成（终态） | 只读 |
| `failed` | 任务无效或迭代超限（终态） | 只读 |
| `cancelled` | 人工取消（终态，预留） | 只读 |

---

## 4. `thread_id` 与检查点

- 每个工作流实例一个独立 `thread_id`：**`wf-{workflow_instance_id}`**，创建实例时生成并落库，
  加唯一约束；同一实例的多次调用（启动、恢复、重启后恢复）始终使用同一条 `thread_id`。
- `thread_id` **由服务端派生**。客户端在 `resume` 请求里带的 `thread_id` 只作为**一致性断言**：
  与库中记录不一致 → `409 CONFLICT`；服务端永远不会用客户端传来的值去寻址检查点。
- 检查点配置统一为 `{"configurable": {"thread_id": thread_id}}`，由 `app/services/workflow_runtime.py` 构造，
  API 层拿不到也不需要这个对象。
- 检查点由**应用实例**的生命周期管理：lifespan 启动时创建并 `setup()`（PG 建表 / SQLite 建文件），
  关闭时释放连接；服务层通过 FastAPI 依赖 `get_workflow_runtime()` 拿到运行时，
  该依赖从 `app.state.workflow_runtime` 读取。
  运行时**不是进程级单例**：检查点持有连接（SQLite 下还持有 `asyncio.Lock`），
  必须与打开它的应用实例在同一个事件循环里，因此「重启」＝新建一个应用实例并重新打开检查点，
  两个实例读同一份检查点文件 / 同一个检查点库。

**审批决定的存放（双通道，数据库为准）**：

1. `resume` 接口先把决定写入 `approval_records`（追加式、不可改）+ `workflow_instances.pending_decision`；
2. 再用 `Command(resume=decision)` 驱动图继续；
3. `human_approval` 节点醒来时，优先取 interrupt 的 resume 值；
   若节点因崩溃重启被重跑（此时没有 interrupt 值），则从库中取**本轮未消费的决定**兜底，
   保证「决定已入库但检查点尚未落盘」的崩溃窗口不会让决定丢失或被重复消费。

---

## 5. 数据库变更（迁移 `0004_workflow_engine`）

### 5.1 `workflow_instances` 增列

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `thread_id` | `VARCHAR(120)` NOT NULL，**唯一** | 与检查点一一对应；历史行按 `wf-{id}` 回填 |
| `iteration` | `INTEGER` NOT NULL default `1` | 当前返工迭代序号 |
| `pending_payload` | `JSON` NULL | 人工审批面板所需的摘要（产物、预览、意见） |
| `pending_since` | `TIMESTAMPTZ` NULL | 进入 `waiting_approval` 的时间 |
| `pending_decision` | `JSON` NULL | 已入库、尚未被图消费的决定（兜底通道） |
| `last_decision` | `VARCHAR(32)` NULL | 最近一次决定，便于列表展示 |

> **设计调整（实施时）**：原设计中的 `current_artifact_id` 列被去掉。
> 实例与当前产物的关联已经由 `artifacts.workflow_instance_id` 反向表达，
> 存两处只会带来双写不一致的风险；「当前产物」改为按
> `artifacts.workflow_instance_id = 实例 id` 且 `relative_path = workflow/{id}/iteration-{n}/demo-artifact.md`
> 推导，`n` 取实例的 `iteration`。

### 5.2 新表 `workflow_events`（工作流事件日志，只追加）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `UUID` PK | |
| `workflow_instance_id` | `UUID` NOT NULL，FK → `workflow_instances.id` ON DELETE CASCADE | |
| `sequence` | `INTEGER` NOT NULL | 实例内递增序号 |
| `event_key` | `VARCHAR(160)` NOT NULL | **幂等键**，如 `node_started:load_task:1`；与实例组成唯一约束 |
| `step` | `VARCHAR(64)` NOT NULL | 节点名 |
| `event` | `VARCHAR(64)` NOT NULL | `node_started` / `node_finished` / `artifact_generated` / `validation_passed` / `validation_failed` / `approval_requested` / `approval_received` / `revision_handled` / `workflow_completed` / `workflow_failed` |
| `message` | `TEXT` NULL | 人类可读摘要 |
| `payload` | `JSON` NULL | 结构化补充信息 |
| `created_at` | `TIMESTAMPTZ` NOT NULL | |

唯一约束：`(workflow_instance_id, event_key)` 与 `(workflow_instance_id, sequence)`。

### 5.3 `approval_records` 增列

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `idempotency_key` | `VARCHAR(120)` NULL | 与 `target_type` / `target_id` 组成唯一约束；NULL 不参与去重 |

> 审批记录保持**只追加**语义不变：不加 `updated_at`，不提供更新接口。

### 5.4 复用

`artifacts.workflow_instance_id`、`artifacts.task_id` 已存在（迭代 3 已建），本模块直接复用，不再改动。

迁移纪律不变：先改模型 → `python -m alembic revision --autogenerate` → **人工检查脚本** → 补 `downgrade()`；
唯一约束与 `NOT NULL` 在 SQLite 上需 batch 模式重建表，沿用迭代 3 的 `op.f()` 命名约定写法。

---

## 6. API 设计

统一前缀 `/api/v1`；所有响应带 `X-Request-ID`；错误统一为
`{code, message, detail, request_id, timestamp}`。

### 6.1 `POST /api/v1/tasks/{task_id}/workflow/start`

启动一次研发工作流。

请求体（可选）：

```json
{ "workflow_key": "dev_workflow", "started_by": "alice" }
```

`workflow_key` 缺省取 `WORKFLOW_DEFAULT_KEY`；`started_by` 可空（写入 `created_by`）。

成功 `201`：

```json
{
  "id": "9f1c...-...",
  "project_id": "1a2b...",
  "task_id": "3c4d...",
  "workflow_key": "dev_workflow",
  "thread_id": "wf-9f1c...-...",
  "status": "waiting_approval",
  "current_step": "human_approval",
  "iteration": 1,
  "current_artifact": {
    "id": "…", "relative_path": "workflow/9f1c.../iteration-1/demo-artifact.md",
    "version": 1, "sha256": "…", "review_status": "pending"
  },
  "pending_approval": {
    "artifact_id": "…", "artifact_version": 1, "iteration": 1,
    "preview": "# 模拟产物 …（前 500 字）",
    "revision_comments": [],
    "requested_at": "2026-11-09T10:00:00Z"
  },
  "approvals": [],
  "started_at": "…", "finished_at": null, "error_message": null,
  "created_at": "…", "updated_at": "…"
}
```

> 启动接口会**同步跑完图**直到第一个 `interrupt()`（节点均为本地模拟，毫秒级），
> 因此返回时状态通常已是 `waiting_approval`。

| 失败场景 | HTTP | `code` |
| --- | --- | --- |
| 任务不存在 / 已软删除 | 404 | `NOT_FOUND` |
| 任务处于 `completed` / `cancelled` | 409 | `CONFLICT` |
| 该任务已有未结束的工作流 | 409 | `CONFLICT`（`detail.existing_workflow_id`） |
| `workflow_key` 未注册 | 404 | `NOT_FOUND` |

### 6.2 `GET /api/v1/workflows/{workflow_id}`

返回**服务端整理后的视图**，不暴露 LangGraph 原始 state / checkpoint id：

```json
{
  "id": "…", "project_id": "…", "task_id": "…", "workflow_key": "dev_workflow",
  "thread_id": "wf-…", "status": "waiting_approval", "current_step": "human_approval",
  "iteration": 1,
  "current_artifact": { "id": "…", "relative_path": "…", "version": 1,
                        "sha256": "…", "review_status": "pending" },
  "pending_approval": { "artifact_id": "…", "preview": "…", "revision_comments": [],
                         "requested_at": "…" },
  "approvals": [
    { "id": "…", "decision": "rejected", "approver": "alice",
      "comment": "补充异常处理", "sequence": 1, "created_at": "…" }
  ],
  "started_at": "…", "finished_at": null, "error_message": null,
  "created_at": "…", "updated_at": "…"
}
```

不存在 → 404 `NOT_FOUND`。

### 6.3 `POST /api/v1/workflows/{workflow_id}/resume`

推进工作流：提交人工审批决定，或在无审批时从检查点继续。

请求体：

```json
{
  "thread_id": "wf-9f1c...",
  "decision": "approved",
  "approver": "alice",
  "comment": "可以，进入下一阶段",
  "idempotency_key": "b2c3d4e5-..."
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `thread_id` | 是 | 与库中记录比对，不一致 → 409 |
| `decision` | `waiting_approval` 时必填 | `approved` / `rejected`（其余值 → 422） |
| `approver` | `decision` 存在时必填 | 审批人，1–120 字符 |
| `comment` | 否 | 退回时为修改意见，通过时可选备注 |
| `idempotency_key` | 否 | 客户端幂等键；提供时重复提交直接返回当前状态 |

行为矩阵：

| 当前状态 | 请求 | 结果 |
| --- | --- | --- |
| `waiting_approval` | `decision=approved` | 记录审批 → 图继续 → `complete_workflow` → `completed`，任务置 `completed` |
| `waiting_approval` | `decision=rejected` | 记录审批（含意见）→ `handle_revision_comments` → 重新生成 → 校验 → 再次停在 `waiting_approval`（`iteration` +1） |
| `paused` / `running`（重启后停在检查点） | 不带 `decision` | 从检查点继续执行 |
| `waiting_approval` | 不带 `decision` | 409（等待审批时必须给出决定） |
| `pending` | 任意 | 409（尚未启动） |
| `completed` / `failed` / `cancelled` | 任意 | 409（终态） |
| 任意 | 与此前相同的 `idempotency_key` | 200，**不重复执行副作用**，直接返回当前状态 |
| 任意 | `thread_id` 不匹配 | 409 |
| 任意 | `decision` 取值非法 / 缺 `approver` | 422 |

成功 `200`：返回与 6.2 相同结构的最新视图。

### 6.4 `GET /api/v1/workflows/{workflow_id}/logs`

返回该实例的事件日志（平台自有表，**不是** LangGraph 内部状态）：

```json
{
  "items": [
    { "sequence": 1, "step": "load_task", "event": "node_started",
      "message": "载入任务 DEV-1-1", "payload": { "task_id": "…" },
      "created_at": "…" }
  ],
  "total": 12, "page": 1, "page_size": 20, "pages": 1
}
```

分页参数复用 `app/api/deps.py` 的 `pagination_params`（`page` ≥ 1、`page_size` 1–100）。

### 6.5 「浏览器不得直接操作 LangGraph 内部状态」的落实

| 约束 | 落实方式 |
| --- | --- |
| 客户端不能指定检查点 | `thread_id` 由服务端从 `workflow_id` 派生，客户端传值仅做一致性校验 |
| 客户端不能塞 state | 请求体中没有任何状态 / 图数据字段；schema 白名单校验，多余字段忽略 |
| 客户端不能读原始 state | `GET /workflows/{id}` 返回平台自有字段；无任何端点暴露 checkpoint / state blob / 节点内部变量 |
| 客户端不能直接跳过审批 | 推进图只能经 `resume`，而 `resume` 先校验状态再决定是否放行 |
| 客户端不能伪造审批记录 | 审批记录只能由服务层在 `resume` 流程内追加 |

---

## 7. 幂等性与重启恢复

### 7.1 幂等矩阵

| 副作用 | 幂等键 | 重复执行的结果 |
| --- | --- | --- |
| 生成产物文件 | 相对路径 `workflow/{wf_id}/iteration-{n}/demo-artifact.md` | 命中既有 `artifacts` 行 → 复用；落盘用 `move_into()` 原子占位，绝不覆盖 |
| 写事件日志 | `(workflow_instance_id, event_key)` | 唯一约束命中 → 跳过，不产生重复行 |
| 写审批记录 | `(target_type, target_id, idempotency_key)` | 命中 → 直接返回既有结果，不重复推进 |
| 推进工作流状态 | 状态绝对赋值 | 重复赋值结果一致 |
| 更新任务状态 | 状态绝对赋值 | 同上 |

### 7.2 重启恢复

1. 检查点由 PostgreSQL（生产）/ SQLite（本地）持久化，`thread_id` 与实例一一对应；
2. 重启＝**新建一个应用实例**：lifespan 重新创建检查点（PG 建表 / SQLite 打开同一文件），
   随后扫描 `status = running` 的实例：
   - 若实例 `pending_payload` 非空（说明已写过审批面板数据）→ 置 `waiting_approval`；
   - 否则置 `paused`，并写一条 `workflow_recovered` 事件；
3. 恢复后由调用方显式 `POST /workflows/{id}/resume`（不带 decision）继续，
   接口**不会**自动复活流程，避免重启风暴；
4. 审批决定已在 `approval_records` + `pending_decision` 中持久化，
   即使崩溃发生在「决定入库」与「检查点落盘」之间，节点也能从库中兜底取回决定（见 §4）。

---

## 8. 自动化测试矩阵

新增 `backend/tests/test_workflow_approval.py`（pytest + httpx + 真实检查点落盘）：

| # | 场景 | 断言要点 |
| --- | --- | --- |
| 1 | **审批通过** | 启动 → `waiting_approval`；`resume(approved)` → `completed`；任务 `completed`；产物文件存在且 SHA256 一致；`approval_records` 新增 1 条 `approved` |
| 2 | **审批退回** | `resume(rejected, comment)` → 仍在 `waiting_approval`，`iteration = 2`，产物相对路径含 `iteration-2`，新产物内容包含上一轮意见；事件日志出现 `revision_handled` |
| 3 | **再次审批** | 承接场景 2 再 `resume(approved)` → `completed`；审批记录 2 条、序号 1/2 |
| 4 | **服务重启恢复** | 新建第二个应用实例（等价于进程重启：重新打开同一个检查点文件）→ 实例仍为 `waiting_approval` → `resume` 成功 → `completed`；另测 `running` 实例被新实例调和为 `paused` 且可 `resume` 继续回到 `waiting_approval` |
| 5 | **重复审批** | 同一 `idempotency_key` 提交两次 → 第二次 200 且状态不变、`approval_records` 仍只有 1 条、产物未新增；无幂等键的二次提交 → 409；已入库但未落盘的「半截决定」→ 复用该记录推进，不再写第二条 |
| 6 | **两任务并行隔离** | 同一项目两个任务各启动一次 → `thread_id` 不同、产物不同、审批序号各自从 1 开始、审批 A 不影响 B 的状态 |
| 7 | **状态与参数校验** | 终态 resume → 409；`thread_id` 不匹配 → 409；非法 `decision` → 422；未知工作流 → 404；未知任务 start → 404；重复 start → 409 |
| 8 | **幂等副作用**（补充） | 模拟生成节点重放 → 不产生第二份产物文件、不产生第二条 `artifact_generated` 事件 |

测试基建：SQLite 检查点落到临时目录；每个用例独立 `thread_id`；既有 72 个用例保持全绿，
本文件新增 11 个用例（场景 1–8，其中场景 4/5 各含两个子场景）。

---

## 9. 实施步骤（已执行）

| 步骤 | 内容 | 产出 | 状态 |
| --- | --- | --- | --- |
| 1 | 依赖与配置 | `pyproject.toml`（新增 3 个依赖）、`app/core/config.py`、`.env.example`、`docker-compose.yml` | ✅ |
| 2 | 模型与迁移 | `app/models/workflow_event.py`、`workflow_instances` / `approval_records` 增列、`0004_workflow_engine` 迁移（含 `downgrade()`） | ✅ |
| 3 | 工作流实现 | `app/workflows/dev_workflow.py`（状态定义 + 5 个模拟节点 + 返工分支 + 图装配）、注册 `dev_workflow` | ✅ |
| 4 | 运行时与服务层 | `app/services/workflow_runtime.py`（检查点生命周期、图调用）、`app/services/workflow_store.py`（实例与事件日志）、`app/services/workflows.py`（启动/查询/恢复/日志） | ✅ |
| 5 | API 层 | `app/schemas/workflow.py`、`app/api/v1/endpoints/workflows.py`、路由注册 | ✅ |
| 6 | 测试 | `backend/tests/test_workflow_approval.py`（场景 1–8，共 11 个用例） | ✅ |
| 7 | 验证 | `python -m ruff check .`、`python -m pytest -q`、迁移往返 + `alembic check`、PG 方言 `--sql` 预览、HTTP 冒烟脚本 | ✅（PG 实连除外） |
| 8 | 文档与提交 | 更新 `README.md`、本设计文档状态改为「已实施」+ 验证记录；提交并推送 `develop` | ✅ |

---

## 10. 已知限制与未验证项

1. **本机无 PostgreSQL、无 Docker**：PostgreSQL Checkpointer 的真实连通性与建表流程无法在本机执行，
   自动化测试跑在 SQLite 检查点上；PG 路径标记为「**未执行**」，复验命令见 §11。
2. `interrupt()` 恢复时节点重跑 ⇒ 中断前副作用必须幂等，本设计通过
   「绝对赋值 + `event_key` 唯一键 + 产物相对路径唯一约束」三重保障，但**跨进程并发**同一
   `thread_id` 的场景未做加锁（单实例部署假设）。
3. 本迭代不含鉴权：`approver` 由请求方自报，真实身份需在接入鉴权后由服务端注入。
4. 前端审批界面不在本次范围。

---

## 11. 验证记录（2026-11-09）

| # | 检查项 | 命令 | 结果 |
| --- | --- | --- | --- |
| 1 | 静态检查 | `python -m ruff check .` | ✅ All checks passed! |
| 2 | 单元测试 | `python -m pytest -q` | ✅ **83 passed**（既有 72 + 新增 11） |
| 3 | 迁移往返 | `alembic downgrade base` → `alembic upgrade head` | ✅ 0001 → 0004 全程通过 |
| 4 | 模型漂移 | `alembic check` | ✅ No new upgrade operations detected. |
| 5 | PG 方言离线预览 | `alembic upgrade head --sql`（`postgresql+asyncpg://…`） | ✅ 生成 `workflow_instances` / `workflow_events` DDL，含 `ALTER TABLE … ADD COLUMN thread_id …`、回填语句与 `uq_workflow_instances_thread_id` 唯一索引 |
| 6 | HTTP 冒烟 | `python -m scripts.smoke_workflow` | ✅ start → `waiting_approval` → reject → `iteration=2` → approve → `completed`，事件日志 11 条，任务 `completed` |
| 7 | 路由契约 | OpenAPI 导出 | ✅ 四个接口齐全：`POST /tasks/{task_id}/workflow/start`、`GET /workflows/{workflow_id}`、`POST /workflows/{workflow_id}/resume`、`GET /workflows/{workflow_id}/logs`；`/api/v1/health` 契约未变 |
| 8 | PostgreSQL 检查点实连 | — | ⬜ **未执行**（本机无 PostgreSQL / Docker）。复验：设置 `WORKFLOW_CHECKPOINT_BACKEND=postgres` 与 `CHECKPOINT_DATABASE_URL`，执行 `python -m alembic upgrade head` 与 `python -m pytest -q`（或 `docker compose up -d postgres` 后再跑冒烟脚本） |

> 第 5 项为**离线渲染**：SQL 文本已按 PostgreSQL 方言生成并人工核对，但未在真实 PG 实例上执行过。
