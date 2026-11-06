# 任务 2：数据库设计与项目管理模块 — 设计与实施计划

> 状态：**已实施**（设计已评审确认，代码、迁移与测试均已落地并实际执行验证）
> 基线：任务 1 基础工程已完成，验收报告见 `docs/iteration1_acceptance_report.md`
> 约定来源：`AGENTS.md`（依赖方向 `api → services → models → core`）

---

## 1. 目标与边界

### 1.1 本次要做

- 用 PostgreSQL + SQLAlchemy 2.x + Alembic 建立 5 张业务表：`projects`、`development_tasks`、`workflow_instances`、`artifacts`、`approval_records`。
- 实现项目管理 REST API：项目 5 个端点、任务 4 个端点，项目与任务强关联。
- Pydantic 请求/响应模型、统一错误信封、分页查询、参数校验。
- Alembic 初始迁移（相对 `0001_baseline`）+ 数据库初始化与迁移命令。
- pytest 覆盖：项目增删改查、任务创建、项目关联、非法参数。

### 1.2 本次不做（避免越界）

- 不实现任何 AI Agent、工作流构图、PRD 解析等业务逻辑（`workflows/`、`agents/` 保持占位）。
- 不做前端页面改造（任务 2 范围是数据库 + 后端 API）。
- 不引入鉴权/多租户（当前无用户体系，`owner`/`approver` 只是审计字段）。
- 不引入文件上传与存储实现，`artifacts` 只保存元数据（相对路径 + 版本 + SHA256）。

---

## 2. 设计决策与理由

| 决策点 | 方案 | 理由 |
| --- | --- | --- |
| 主键 | `UUID`，Python 侧 `uuid4()` 生成 | 分布式安全、可跨库合并；列类型用 `sa.Uuid`（PG 上是原生 `uuid`，SQLite 上是 `CHAR(32)`） |
| 时间字段 | `DateTime(timezone=True)`，`server_default=func.now()` | 与既有 `TimestampMixin` 一致，存 UTC |
| 状态字段 | `VARCHAR(n)` + `CHECK` 约束，Python 侧 `StrEnum` 定义取值 | 不用 PG 原生 ENUM：加值要 `ALTER TYPE`，且 Alembic 在 PG 上比对 ENUM 容易产生漂移告警；`CHECK` 两边都能跑 |
| JSON 字段 | `sa.JSON().with_variant(postgresql.JSONB, "postgresql")` | PG 上得 JSONB（可建索引），SQLite 上退化为 JSON，保证可移植 |
| 任务编号 | `projects.task_sequence` 计数器 + `UPDATE ... RETURNING` 原子自增 | 避免 `max(seq)+1` 的并发竞态；`UNIQUE(project_id, seq)` 兜底 |
| 删除语义 | **软删除**（`deleted_at`），项目删除时连带软删其任务 | 审批记录追加式 + 产物版本化要求保留历史；物理删除会破坏审计链 |
| 审批记录 | 只增不改不删，无 `updated_at`，`(target_type, target_id, sequence)` 唯一 | 追加式；`sequence` 保证同一对象的审批顺序可确定 |
| 审批记录外键 | `project_id` 用 `ON DELETE RESTRICT`（其余表 `CASCADE`） | 审计数据不应随主体物理消失，物理删除有审批历史时直接拒绝 |
| 多态引用 | `approval_records.target_type + target_id`（不建 FK） | 一个审批可指向任务/产物/工作流实例多张表，PG 无多态外键；用普通索引 + 服务层校验存在性 |
| 分页 | `page`（≥1，默认 1）+ `page_size`（1–100，默认 20） | 统一信封 `{items, total, page, page_size, pages}` |

---

## 3. ER 关系

```
projects 1 ──< development_tasks 1 ──< workflow_instances
    │                    │                    │
    │                    └──── artifacts ─────┘
    │                          (project_id / task_id / workflow_instance_id)
    └──< approval_records   (target_type + target_id 多态指向 task/artifact/workflow_instance)
```

- `workflow_instances.task_id` 可空：`NULL` 表示项目级工作流，非空表示任务级。
- `artifacts` 三级外键均可空，允许「只挂项目」的文件元数据。
- `approval_records` 不含 `updated_at`，**不提供** PUT/DELETE 接口。

---

## 4. 表结构设计

### 4.1 projects

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | `uuid4()` |
| `code` | VARCHAR(64) | NOT NULL，**UNIQUE** | 人类可读项目编号，如 `PRJ-2026-001` |
| `name` | VARCHAR(200) | NOT NULL | 项目名称 |
| `description` | TEXT | NULL | 描述 |
| `status` | VARCHAR(32) | NOT NULL，默认 `planning`，CHECK | `planning/active/paused/completed/archived/cancelled` |
| `owner` | VARCHAR(120) | NULL | 负责人 |
| `task_sequence` | INTEGER | NOT NULL，默认 0，CHECK ≥ 0 | 项目内任务编号计数器 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | 继承 `TimestampMixin` |
| `deleted_at` | TIMESTAMPTZ | NULL | 软删除标记 |

索引：`ix_projects_status`、`ix_projects_created_at`、`ix_projects_deleted_at`；唯一：`uq_projects_code`。

### 4.2 development_tasks

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `project_id` | UUID | NOT NULL，FK → `projects.id` **ON DELETE CASCADE**，索引 | 任务必须属于项目 |
| `seq` | INTEGER | NOT NULL，CHECK ≥ 1 | 项目内序号，由计数器分配 |
| `title` | VARCHAR(300) | NOT NULL | 任务标题 |
| `description` | TEXT | NULL | 任务描述 |
| `status` | VARCHAR(32) | NOT NULL，默认 `pending`，CHECK | `pending/in_progress/blocked/in_review/completed/cancelled` |
| `priority` | VARCHAR(16) | NOT NULL，默认 `medium`，CHECK | `low/medium/high/urgent` |
| `assignee` | VARCHAR(120) | NULL | 执行人 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | |
| `deleted_at` | TIMESTESTAMPTZ | NULL | 软删除标记 |

唯一：`uq_development_tasks_project_seq (project_id, seq)`；索引：`ix_development_tasks_project_id`、`ix_development_tasks_status`、`ix_development_tasks_project_id_status`。

### 4.3 workflow_instances

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `project_id` | UUID | NOT NULL，FK → `projects.id` CASCADE，索引 | |
| `task_id` | UUID | NULL，FK → `development_tasks.id` **SET NULL**，索引 | NULL = 项目级工作流 |
| `workflow_key` | VARCHAR(100) | NOT NULL | 注册表里的工作流标识 |
| `status` | VARCHAR(32) | NOT NULL，默认 `pending`，CHECK | `pending/running/paused/waiting_approval/completed/failed/cancelled` |
| `current_step` | VARCHAR(100) | NULL | 暂停时所处节点 |
| `state` | JSONB | NULL | 工作流状态快照（后续接 LangGraph checkpoint） |
| `error_message` | TEXT | NULL | 失败原因 |
| `started_at` / `finished_at` | TIMESTAMPTZ | NULL | 生命周期时间 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | |

索引：`ix_workflow_instances_project_id`、`ix_workflow_instances_task_id`、`ix_workflow_instances_status`、`ix_workflow_instances_project_id_status`。

### 4.4 artifacts（文件元数据）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `project_id` | UUID | NOT NULL，FK → `projects.id` CASCADE，索引 | |
| `task_id` | UUID | NULL，FK → `development_tasks.id` SET NULL，索引 | |
| `workflow_instance_id` | UUID | NULL，FK → `workflow_instances.id` SET NULL，索引 | |
| `relative_path` | VARCHAR(500) | NOT NULL | 项目工作区内的**相对路径**（不存绝对路径） |
| `version` | INTEGER | NOT NULL，默认 1，CHECK ≥ 1 | 版本号 |
| `sha256` | CHAR(64) | NOT NULL | 内容哈希，十六进制小写 |
| `file_type` | VARCHAR(100) | NOT NULL | MIME 类型或扩展名类别，如 `text/markdown` |
| `size_bytes` | BIGINT | NULL，CHECK ≥ 0 | 文件大小 |
| `review_status` | VARCHAR(32) | NOT NULL，默认 `pending`，CHECK | `pending/approved/rejected/superseded` |
| `reviewed_by` / `reviewed_at` | VARCHAR(120) / TIMESTAMPTZ | NULL | 审核人与审核时间 |
| `created_by` | VARCHAR(120) | NULL | 上传者 |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL | |

唯一：`uq_artifacts_project_path_version (project_id, relative_path, version)`；索引：`ix_artifacts_project_id`、`ix_artifacts_sha256`、`ix_artifacts_review_status`、`ix_artifacts_task_id`、`ix_artifacts_workflow_instance_id`。

### 4.5 approval_records（追加式）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | PK | |
| `project_id` | UUID | NOT NULL，FK → `projects.id` **RESTRICT**，索引 | |
| `target_type` | VARCHAR(32) | NOT NULL，CHECK | `task/artifact/workflow_instance` |
| `target_id` | UUID | NOT NULL | 多态目标 ID（不建 FK，服务层校验存在性） |
| `decision` | VARCHAR(32) | NOT NULL，CHECK | `approved/rejected/changes_requested` |
| `comment` | TEXT | NULL | 审批意见 |
| `approver` | VARCHAR(120) | NOT NULL | 审批人 |
| `sequence` | INTEGER | NOT NULL，CHECK ≥ 1 | 同一 target 的审批顺序 |
| `created_at` | TIMESTAMPTZ | NOT NULL | **没有 `updated_at`**（追加式） |

唯一：`uq_approval_records_target_sequence (target_type, target_id, sequence)`；索引：`ix_approval_records_project_id`、`ix_approval_records_target_type_target_id`、`ix_approval_records_created_at`。

---

## 5. API 设计

统一前缀 `/api/v1`；错误全部走 `app/core/exceptions.py` 的信封 `{code, message, detail, request_id, timestamp}`。

### 5.1 项目

| 方法 | 路径 | 行为 | 成功码 |
| --- | --- | --- | --- |
| POST | `/api/v1/projects` | 创建；`code` 重复 → 409 | 201 |
| GET | `/api/v1/projects` | 分页列表；过滤 `status`、`keyword`（匹配 name/code）；默认按 `created_at DESC` | 200 |
| GET | `/api/v1/projects/{project_id}` | 详情；不存在 → 404 | 200 |
| PUT | `/api/v1/projects/{project_id}` | 部分更新（字段全可选）；改 `code` 重复 → 409 | 200 |
| DELETE | `/api/v1/projects/{project_id}` | 软删除项目并级联软删其任务 | 204 |
| GET | `/api/v1/projects/{project_id}/tasks` | 项目下的任务分页列表（附加，体现关联） | 200 |

### 5.2 任务

| 方法 | 路径 | 行为 | 成功码 |
| --- | --- | --- | --- |
| POST | `/api/v1/tasks` | 创建；`project_id` 必填，项目不存在 → 404；自动分配 `seq` | 201 |
| GET | `/api/v1/tasks` | 分页列表；过滤 `project_id`、`status`、`priority`、`keyword` | 200 |
| GET | `/api/v1/tasks/{task_id}` | 详情；不存在 → 404 | 200 |
| PUT | `/api/v1/tasks/{task_id}` | 部分更新；不允许改 `project_id`（换项目=换归属，另行处理） | 200 |

按需求，任务**不提供** DELETE（用 `status=cancelled` 表达终止）。

### 5.3 分页与校验

- 请求：`page`（默认 1，≥1）、`page_size`（默认 20，1–100），越界 → 422 信封。
- 响应：`{"items": [...], "total": 88, "page": 1, "page_size": 20, "pages": 5}`。
- 字段长度/格式约束在 Pydantic 层声明（`max_length`、`pattern`、枚举），非法值一律 422。

---

## 6. 代码结构（遵循 `AGENTS.md` 依赖方向）

```
backend/app/
├── models/
│   ├── enums.py              # 新增：领域枚举（项目/任务/工作流/产物/审批状态）
│   ├── project.py             # 新增：Project
│   ├── task.py                # 新增：DevelopmentTask
│   ├── workflow.py            # 新增：WorkflowInstance
│   ├── artifact.py            # 新增：Artifact
│   ├── approval.py            # 新增：ApprovalRecord
│   └── __init__.py            # 修改：导入各模型，注册到 Base.metadata
├── schemas/
│   ├── common.py              # 新增：分页请求参数与分页响应泛型
│   ├── project.py             # 新增：ProjectCreate / ProjectUpdate / ProjectRead
│   ├── task.py                # 新增：TaskCreate / TaskUpdate / TaskRead
│   ├── workflow.py            # 新增：WorkflowInstanceRead
│   ├── artifact.py            # 新增：ArtifactRead / ArtifactRegister
│   └── approval.py            # 新增：ApprovalAppend / ApprovalRecordRead
├── services/
│   ├── projects.py            # 新增：项目 CRUD + 分页查询 + 软删除
│   ├── tasks.py               # 新增：任务 CRUD + 分页查询 + seq 分配
│   ├── artifacts.py           # 新增：产物元数据登记与版本递增
│   └── approvals.py           # 新增：审批追加（仅 append）
└── api/v1/endpoints/
    ├── projects.py            # 新增
    ├── tasks.py               # 新增
    └── router.py              # 修改：注册两个子路由
```

枚举放在 `app/models/enums.py`：`models` 与 `schemas` 都从这里取状态取值，避免在 `core`（禁止领域概念）与两处重复定义之间二选一。

---

## 7. 迁移方案

- 基线 `0001_baseline` 保留不动，新增 `0002_*` 修订（`down_revision = "0001_baseline"`）。
- 生成方式：先改 `app/models/`，再 `python -m alembic revision --autogenerate -m "..."`，**人工逐行检查**生成的脚本（不手写绕过模型定义）。
- `upgrade()` / `downgrade()` 都要实现；`downgrade()` 按外键逆序删除。

数据库初始化与迁移命令（写入 `README.md`）：

```bash
# 初始化：在空库上执行全部迁移
python -m alembic upgrade head

# 回滚到空库
python -m alembic downgrade base

# 修改模型后生成新迁移（随后必须人工检查）
python -m alembic revision --autogenerate -m "描述"

# 检查模型与迁移是否漂移（应输出 "No new upgrade operations detected"）
python -m alembic check
```

另提供 `backend/scripts/init_db.sh` 与 `backend/scripts/init_db.ps1`（跨平台各一份，符合 `AGENTS.md` 跨平台约定）。

---

## 8. 测试方案

### 8.1 测试数据库策略

`backend/tests/conftest.py` 在**导入应用之前**注入 `DATABASE_URL`：

- 默认用 `sqlite+aiosqlite` 指向临时文件（`tempfile` 生成，退出即删），保证测试**不碰开发者真实库**；
- 支持 `TEST_DATABASE_URL` 覆盖 → 可直接指向 PostgreSQL 跑同一套测试；
- session 级 fixture 通过**子进程执行 `python -m alembic upgrade head`** 建库，即测试跑的是真实迁移脚本，而非 `create_all`；
- 收尾执行 `alembic downgrade base` + 删除临时文件。

### 8.2 用例清单（`backend/tests/`）

| 文件 | 覆盖点 |
| --- | --- |
| `test_projects.py` | 创建项目；`code` 重复 → 409；列表分页与过滤；详情 404；更新名称/状态；软删除后再查 → 404、列表不再出现；非法参数（空 code、超长 name）→ 422 |
| `test_tasks.py` | 创建任务并校验归属项目；`project_id` 不存在 → 404；`seq` 递增且项目内唯一；列表按 `project_id` 过滤；更新状态；删除项目后其任务不可见；非法参数（空标题、超长、非法状态枚举）→ 422 |
| `test_artifacts_approvals.py` | 产物登记（相对路径/版本/SHA256/文件类型/审核状态）；同路径同版本重复 → 409；版本递增；审批记录仅追加、顺序号连续、不可更新 |

> 若选择「其他三张表不开放 HTTP 接口」，产物与审批用**服务层**测试覆盖，同样落到真实数据库。

### 8.3 验证命令

```bash
cd backend
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m alembic downgrade base
./.venv/Scripts/python.exe -m alembic check
```

---

## 9. 环境限制与验证策略（PostgreSQL）

本机**没有 PostgreSQL，也没有 Docker**（`psql`/`postgres`/`pg_ctl` 均不存在，`C:\Program Files\PostgreSQL` 不存在）；安装 Docker Desktop 会被 Qoder 安全分类器拦截，需要你在自己终端里手动执行。

因此本次的数据库验证分两层，**如实标注、不含糊**：

| 层 | 内容 | 状态 |
| --- | --- | --- |
| A. 真实执行 | 在 SQLite 上跑完整 `upgrade → downgrade → upgrade` 往返、`alembic check` 漂移检查、全量 pytest | **已执行，全部通过**（见第 12 节） |
| B. PostgreSQL 语义 | 用 `alembic upgrade head --sql` 在 **PostgreSQL 方言**下离线渲染真实 DDL，核对 `uuid` / `JSONB` / `CHECK` / `FK` / 索引是否符合预期（不需要 PG 服务） | **已执行，全部符合预期**（见第 12 节） |
| C. PostgreSQL 实跑 | 真实 PG 服务上 `upgrade`/`downgrade`/`pytest` 全链路 | **未执行**，需你提供连接串或在本机/容器里跑 PG |

如果能提供 PostgreSQL 连接串（`postgresql+asyncpg://user:pass@host:5432/db`），我会追加 C 层实测并把结果写进交付说明；否则在文档中明确标注为「未执行」并附上复验命令。

---

## 10. 实施步骤

1. `app/models/enums.py` + 5 个模型文件，更新 `app/models/__init__.py`
2. `app/schemas/`：`common.py`（分页）、`project.py`、`task.py` 及另三表 schema
3. `app/services/`：`projects.py`、`tasks.py`、`artifacts.py`、`approvals.py`
4. `app/api/v1/endpoints/`：`projects.py`、`tasks.py`，注册进 `router.py`
5. 生成 `0002_*` 迁移并人工检查 `upgrade()/downgrade()`
6. 改造 `tests/conftest.py`（测试库 fixture）+ 编写三组测试
7. `README.md` 补迁移命令与环境变量说明；`backend/scripts/` 初始化脚本
8. 全量验证：ruff / pytest / 迁移往返 / `alembic check` / PG 方言 DDL 渲染 / HTTP 冒烟
9. 提交并推送到远端（推送链路已验证可用，无需手工配置）

以上 9 步**已全部完成**，执行记录见第 12 节。

---

## 11. 已确认决策点

评审时确认的三个决策，实现与本文档保持一致：

1. **删除语义**：采用**软删除**。`projects` 与 `development_tasks` 都带 `deleted_at`，删除项目时级联软删除其任务；数据库层的 `ON DELETE CASCADE` 保留，用于物理清理场景。查询默认过滤 `deleted_at IS NULL`。
2. **另三张表的接口范围**：**只做表 + 服务层**。`workflow_instances` / `artifacts` / `approval_records` 建表并实现服务层与 schema，但不开放 HTTP 端点——需求条目三只要求项目与任务的 REST 接口。
3. **PostgreSQL 实测**：按前两层验证（A 层真实执行 + B 层 PG 方言离线 DDL）。本机没有 PostgreSQL 也没有 Docker，**验证层 C（真实 PG 服务全链路）标注为「未执行」**，并在第 12 节给出复验命令。

---

## 12. 实施结果与验证记录

### 12.1 落地文件

| 类别 | 文件 |
| --- | --- |
| 模型 | `app/models/enums.py`、`project.py`、`task.py`、`workflow.py`、`artifact.py`、`approval.py`、更新 `__init__.py` |
| Schema | `app/schemas/common.py`（`Page` / `PageParams` / `build_page`）、`project.py`、`task.py`、`workflow.py`、`artifact.py`、`approval.py` |
| 服务 | `app/services/projects.py`、`tasks.py`、`artifacts.py`、`approvals.py` |
| API | `app/api/v1/endpoints/projects.py`、`tasks.py`；更新 `app/api/v1/router.py`、`app/api/deps.py`（分页依赖） |
| 异常 | `app/core/exceptions.py` 新增 `ValidationException`（422 语义错误） |
| 迁移 | `alembic/versions/0002_project_management.py` |
| 测试 | `tests/conftest.py`（重写）、`tests/test_projects.py`、`tests/test_tasks.py`、`tests/test_artifacts_approvals.py` |
| 脚本 | `scripts/init_db.py`、`scripts/init_db.sh`、`scripts/init_db.ps1`、`scripts/smoke_http.py` |
| 文档 | `README.md`、`docs/iteration2_db_design.md` |

### 12.2 已执行的验证（全部实际运行）

| # | 验证项 | 命令 / 方式 | 结果 |
| --- | --- | --- | --- |
| 1 | 代码风格 | `python -m ruff check .` | **All checks passed!** |
| 2 | 单元/接口测试 | `python -m pytest -q` | **51 passed**（18 条基础工程用例 + 33 条新增用例） |
| 3 | 迁移正向往返 | `alembic upgrade head` → `downgrade base` → `upgrade head`（SQLite） | 三个步骤全部成功，无报错 |
| 4 | 迁移后表结构 | 查询 `sqlite_master` | 5 张业务表 + `alembic_version` 全部存在；18 个显式索引（`ix_*`）+ 唯一约束自动索引齐全 |
| 5 | 模型/迁移漂移 | `alembic check` | **No new upgrade operations detected.** |
| 6 | PostgreSQL 方言 DDL | `alembic upgrade head --sql`（PG 方言离线渲染） | 类型为原生 `UUID` / `JSONB` / `BIGINT` / `TIMESTAMP WITH TIME ZONE`；`CHECK` 约束 12 条齐全；外键动作 `CASCADE` / `SET NULL` / `RESTRICT` 正确；唯一约束 4 条；显式索引 18 条 |
| 7 | 初始化脚本 | `python scripts/init_db.py`、`init_db.sh`、`init_db.ps1`（含 `--reset`） | 三种入口均成功执行建库跳过判断 + 迁移；`--reset` 完成 downgrade→upgrade |
| 8 | 真实 HTTP 冒烟 | uvicorn 起服务 + `scripts/smoke_http.py` | **30 项检查全部通过**：健康检查、`X-Request-ID`、创建/查询/更新/删除项目、409 冲突、422 参数校验、分页信封、任务创建与项目归属、非法状态、软删除后项目与其任务不可见 |

### 12.3 未执行的验证（如实标注）

| # | 验证项 | 原因 | 复验命令 |
| --- | --- | --- | --- |
| C | 真实 PostgreSQL 服务上的 `upgrade` / `downgrade` / `pytest` 全链路 | 本机没有 PostgreSQL，也没有 Docker（安装 Docker Desktop 被安全策略拦截，需手动操作） | 启动 PG 后执行：<br>`cd backend`<br>`$env:DATABASE_URL="postgresql+asyncpg://postgres:***@localhost:5432/ai_dev_platform"`<br>`python -m alembic upgrade head`<br>`python -m alembic downgrade base`<br>`python -m alembic upgrade head`<br>`python -m pytest -q`<br>`python scripts/smoke_http.py http://127.0.0.1:8000/api/v1` |
| C2 | 同一套 pytest 跑在 PostgreSQL 上 | 同上 | `TEST_DATABASE_URL=postgresql+asyncpg://postgres:***@localhost:5432/ai_dev_platform_test python -m pytest -q` |

> 说明：模型与迁移同时面向 PostgreSQL 与 SQLite 编写（`sa.Uuid` / `JSONB` 变体 / `VARCHAR + CHECK` 而非原生 enum），因此 SQLite 上的执行结果能覆盖绝大多数语义；**但 PostgreSQL 特有的行为（如 `JSONB` 写入、并发下的 `UPDATE ... RETURNING` 计数）仍需在真实 PG 上复验**。

### 12.4 迁移脚本的人工修订说明

`0002_project_management.py` 由 `alembic revision --autogenerate` 生成后人工逐行检查并做了两处修正：

1. 生成结果中的 `postgresql.JSONB(astext_type=Text())` 引用了未导入的 `Text`，运行时会 `NameError` → 改为 `postgresql.JSONB(astext_type=sa.Text())`；
2. 生成结果使用了单引号与超长行 → 统一为双引号并按 Ruff 行宽（100）折行。

表结构本身未做任何偏离模型的改动。
