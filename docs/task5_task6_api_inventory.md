# 任务 5 / 任务 6 接口与工程清单

- 状态：**已完成工程检查**（2026-11-10），本次未修改任何业务代码
- 检查对象：`D:\project\ai-dev-platform`（backend / frontend / 数据库模型 / Alembic 迁移 / API 路由 / LangGraph 工作流 / 人工审批 / Docker 配置）
- 方法：通读后端路由、schema、model、service 与工作流实现；导出 FastAPI 生成的 OpenAPI 文档作为接口事实来源（避免凭印象罗列）；前端与容器部分由只读勘察子代理并行完成并人工复核
- 结论摘要：后端 21 个端点已就绪，前端仍是**零业务页面的脚手架**；GitLab 接入**完全未开始**；任务 5 存在 1 个**阻塞级缺口**（没有任何工作流列表/待审批列表接口）

---

## 1. 已实现的 API（21 个）

来源：`backend/app/api/v1/endpoints/{health,projects,tasks,artifacts,workflows}.py`，
与 `create_app().openapi()` 导出的路径逐条核对一致。统一前缀 `/api/v1`，
所有响应带 `X-Request-ID`，错误统一为 `{code, message, detail, request_id, timestamp}`。

### 1.1 健康检查

| 方法 | 路径 | 请求参数 | 响应 | 实现 |
| --- | --- | --- | --- | --- |
| GET | `/health` | 无 | `HealthResponse`：`status/app/version/environment/timestamp`；**不查库** | `endpoints/health.py:28` |
| GET | `/health/ready` | 无 | `ReadinessResponse`：`status/database{status,latency_ms}/timestamp`；DB 不可用时**实际返回 503**（OpenAPI 只声明 200，前端必须自己处理 503） | `endpoints/health.py:44` |

### 1.2 项目管理

| 方法 | 路径 | 请求参数 | 响应 | 实现 |
| --- | --- | --- | --- | --- |
| POST | `/projects` | body `ProjectCreate`：`code`(1-64，`^[A-Za-z0-9][A-Za-z0-9._-]*$`)、`name`(1-200)、`description?`、`status?`(默认 planning)、`owner?` | 201 `ProjectRead` | `endpoints/projects.py:25` |
| GET | `/projects` | query：`page`(≥1)、`page_size`(1-100，默认 20)、`status?`、`keyword?`(名称或编号模糊) | `Page[ProjectListItem]`（比 `ProjectRead` 多 `task_count`） | `endpoints/projects.py:40` |
| GET | `/projects/{project_id}` | path | `ProjectRead`（**不含** `task_count`） | `endpoints/projects.py:66` |
| PUT | `/projects/{project_id}` | body `ProjectUpdate`（全部可选，只写出现的字段；`project_id` 不可迁移） | `ProjectRead` | `endpoints/projects.py:79` |
| DELETE | `/projects/{project_id}` | path | 204；软删除项目并级联软删其任务，数据与审批记录保留 | `endpoints/projects.py:94` |
| GET | `/projects/{project_id}/tasks` | query：`page`、`page_size`、`status?` | `Page[TaskRead]` | `endpoints/projects.py:108` |

### 1.3 研发任务

| 方法 | 路径 | 请求参数 | 响应 | 实现 |
| --- | --- | --- | --- | --- |
| POST | `/tasks` | body `TaskCreate`：`project_id`(必填)、`title`(1-300)、`description?`、`status?`、`priority?`(low/medium/high/urgent)、`assignee?` | 201 `TaskRead` | `endpoints/tasks.py:20` |
| GET | `/tasks` | query：`page`、`page_size`、`project_id?`、`status?`、`priority?`、`keyword?`(标题模糊) | `Page[TaskRead]` | `endpoints/tasks.py:35` |
| GET | `/tasks/{task_id}` | path | `TaskRead`（含 `project_code`/`project_name`） | `endpoints/tasks.py:71` |
| PUT | `/tasks/{task_id}` | body `TaskUpdate`（`project_id` 不可改） | `TaskRead` | `endpoints/tasks.py:84` |

### 1.4 文件（artifacts）

| 方法 | 路径 | 请求参数 | 响应 | 实现 |
| --- | --- | --- | --- | --- |
| POST | `/tasks/{task_id}/artifacts` | multipart：`file`(必填)、`relative_path?`、`stage?`(design/development/testing/delivery/other)、`created_by?` | 201 `ArtifactRead` | `endpoints/artifacts.py:37` |
| GET | `/artifacts/{artifact_id}` | path | `ArtifactRead` | `endpoints/artifacts.py:81` |
| GET | `/artifacts/{artifact_id}/download` | path | 文件流；响应头 `X-Content-SHA256` | `endpoints/artifacts.py:95` |
| GET | `/tasks/{task_id}/artifacts` | query：`page`、`page_size`、`review_status?`、`stage?`、`keyword?` | `Page[ArtifactRead]` | `endpoints/artifacts.py:115` |
| POST | `/artifacts/{artifact_id}/revisions` | multipart：`file`(必填)、`stage?`、`created_by?` | 201 `ArtifactRead`（旧版本转 `superseded`） | `endpoints/artifacts.py:148` |
| POST | `/artifacts/{artifact_id}/review` | body `ArtifactReviewRequest`：`decision`(approved/rejected)、`reviewed_by`(必填)、`comment?` | `ArtifactRead` | `endpoints/artifacts.py:183` |

### 1.5 工作流与人工审批（任务 4 交付）

| 方法 | 路径 | 请求参数 | 响应 | 实现 |
| --- | --- | --- | --- | --- |
| POST | `/tasks/{task_id}/workflow/start` | body `WorkflowStartRequest`：`workflow_key?`(默认 `dev_workflow`)、`started_by?` | 201 `WorkflowRead`；**同步跑图到第一个 interrupt**，返回时通常已是 `waiting_approval` | `endpoints/workflows.py:31` |
| GET | `/workflows/{workflow_id}` | path | `WorkflowRead` | `endpoints/workflows.py:51` |
| POST | `/workflows/{workflow_id}/resume` | body `WorkflowResumeRequest`：`thread_id`(必填)、`decision?`(approved/rejected)、`approver?`（有 decision 时必填）、`comment?`、`idempotency_key?` | 200 `WorkflowRead` | `endpoints/workflows.py:65` |
| GET | `/workflows/{workflow_id}/logs` | query：`page`、`page_size` | `Page[WorkflowEventRead]`（平台自有事件表，**不是** LangGraph 内部状态） | `endpoints/workflows.py:84` |

### 1.6 关键响应结构

**`WorkflowRead`**（任务 5 审批页的核心数据结构，`schemas/workflow.py:99`）：

```jsonc
{
  "id": "uuid", "project_id": "uuid", "task_id": "uuid|null",
  "workflow_key": "dev_workflow",
  "thread_id": "wf-<workflow_id>",            // 服务端派生，客户端只能回传做一致性断言
  "status": "pending|running|paused|waiting_approval|completed|failed|cancelled",
  "current_step": "human_approval",
  "iteration": 1,                             // 返工轮次，退回后 +1
  "current_artifact": {                       // 当前轮次产物
    "id": "uuid", "relative_path": "workflow/<wf_id>/iteration-1/demo-artifact.md",
    "version": 1, "sha256": "…", "size_bytes": 383, "review_status": "pending"
  },
  "pending_approval": {                       // 待审批面板数据，为 null 表示当前不待审
    "request_id": "<wf_id>:1", "iteration": 1, "artifact_id": "uuid",
    "artifact_version": 1, "preview": "产物前 500 字",
    "revision_comments": [], "requested_at": "…"
  },
  "approvals": [                              // 该实例的审批轨迹
    { "id": "uuid", "decision": "approved", "approver": "alice",
      "comment": "…", "sequence": 1, "created_at": "…" }
  ],
  "started_at": "…", "finished_at": null, "error_message": null,
  "created_at": "…", "updated_at": "…"
}
```

**分页信封**（`schemas/common.py:42`，所有列表端点一致）：

```jsonc
{ "items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0 }
```

**`ArtifactRead`**：`id/project_id/task_id/workflow_instance_id/relative_path/version/sha256/file_type/size_bytes/review_status/reviewed_by/reviewed_at/created_by/stage/original_filename/storage_path/created_at/updated_at`。

**`TaskRead`**：`id/project_id/seq/title/description/status/priority/assignee/project_code/project_name/created_at/updated_at`。

---

## 2. 尚未实现的 API

### 2.1 任务 5（前端 + 人工审批界面）缺口

| 优先级 | 缺失接口 | 为什么必须有 | 建议补充方式（不改现有契约，只新增） |
| --- | --- | --- | --- |
| **P0 阻塞** | **工作流实例列表** `GET /workflows`（建议支持 `status`、`project_id`、`task_id` 过滤） | 审批页的「待审批列表」**目前没有任何数据来源**：后端只能按 `workflow_id` 查单个实例，前端既不知道有哪些实例，也不知道谁在等审批 | 新增 `GET /api/v1/workflows`，返回 `Page[WorkflowRead]`；复用 `workflow_store.list_instances()`（目前没有，需要新增）与 `pagination_params` |
| **P0 阻塞** | **按任务反查工作流** `GET /tasks/{task_id}/workflow` | 任务详情页要展示「该任务的工作流状态/轮次/日志入口」，但 `workflow_id` 只在 start 的响应里出现过，刷新页面就丢了 | 新增 `GET /api/v1/tasks/{task_id}/workflows`（返回该任务的实例列表，含历史终态实例）或单实例版本；服务层已有 `find_active_instance(session, task_id)` 可直接复用 |
| P1 | **审批记录查询** `GET /projects/{project_id}/approvals`（可按 `target_type` 过滤） | `approval_records` 只有服务层 `list_approvals()`，**没有任何 HTTP 端点**；artifact / task 的审批轨迹前端完全取不到 | 新增只读端点 + `ApprovalRecordRead` schema（`schemas/approval.py` 已有 `ApprovalRecordRead`，需确认字段覆盖 `idempotency_key`） |
| P1 | 独立的人工审批「通过 / 驳回」端点 | 目前通过/驳回**只能**经 `POST /workflows/{id}/resume`（必须带 `thread_id`）或 `POST /artifacts/{id}/review`（只改文件审核态，不驱动图） | **建议不新增**：直接复用 `resume`，前端保存 `workflow_id` + `thread_id` 即可。确需简化可加 `POST /workflows/{id}/approvals` 薄封装，但会增加第二套语义 |
| P2 | 项目级产物列表 `GET /projects/{project_id}/artifacts` | 项目详情页想汇总展示全部文件时，只能逐任务拉取 | 可由前端聚合 N 个 `GET /tasks/{id}/artifacts`，数据量小的话不必新增 |
| P2 | 工作流实例的取消 `POST /workflows/{id}/cancel` | 状态机定义了 `cancelled`，但**没有任何代码能进入该状态**（枚举里有、服务里没人写） | 需要时再加，属于新语义而非补漏 |
| P2 | 实时状态推送（SSE / WebSocket） | 审批页若要自动刷新，得靠前端轮询 | 现阶段轮询足够，SSE 留到真实 LLM 节点上线后再做 |

### 2.2 任务 6（GitLab 接入）缺口

GitLab 相关能力**完全没有**：全仓库检索 `gitlab` 仅命中 `docs/总任务.txt:6` 的路线图条目。

| 缺失项 | 现状 | 说明 |
| --- | --- | --- |
| Python 依赖 | 无 `python-gitlab`、无 `GitPython` | 需新增依赖；`git` CLI 本机可用（2.52.0） |
| 配置项 | `config.py` 无任何 gitlab 字段 | 需 `GITLAB_BASE_URL` / `GITLAB_TOKEN` / `GITLAB_DEFAULT_NAMESPACE` / `GITLAB_TIMEOUT` 等 |
| 数据库 | `projects` 表**没有仓库地址字段** | 需要一处绑定关系，见 §4.3 的两个方案 |
| 服务层 | 无 `app/services/gitlab.py` | 需要：仓库地址校验、仓库信息查询、克隆/拉取 |
| API | 无任何 GitLab 端点 | 需要设计（见任务 6 计划文档） |
| CI | 无 `.github/workflows/`、无 `.gitlab-ci.yml` | 部署验证目前只能靠手工 compose |

### 2.3 明确**不存在**的东西（避免误用）

- 没有登录、用户、JWT、Session、角色与权限表——`approver`、`reviewed_by`、`created_by` 全部由请求方自报。
- 没有项目级上传（只有任务级 `POST /tasks/{task_id}/artifacts`）。
- 没有 `workflow_instances` 的删除/取消接口。
- 没有 `artifacts` 的删除接口（只有 superseded 语义）。
- 没有 Webhook、通知（飞书在路线图第四迭代）。

---

## 3. 数据库模型与字段

迁移链：`0001_baseline` → `0002_project_management` → `0003_artifact_storage` → `0004_workflow_engine`（head）。
枚举统一用 `StrEnum` + `VARCHAR` + `CHECK` 约束，不用原生 PG enum。

### 3.1 `projects`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID PK | |
| `code` | VARCHAR(64) unique | 项目编号，正则 `^[A-Za-z0-9][A-Za-z0-9._-]*$` |
| `name` | VARCHAR(200) | |
| `description` | TEXT null | |
| `status` | VARCHAR(32) | planning / active / paused / completed / archived / cancelled |
| `owner` | VARCHAR(120) null | |
| `task_sequence` | INTEGER | 任务序号原子计数器 |
| `deleted_at` | TIMESTAMPTZ null | 软删除标记 |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

索引：`status`、`created_at`、`deleted_at`。

### 3.2 `development_tasks`

`id` / `project_id`(FK CASCADE) / `seq`(项目内递增，`uq_development_tasks_project_seq`) / `title`(300) / `description` / `status`(pending、in_progress、blocked、in_review、completed、cancelled) / `priority`(low、medium、high、urgent) / `assignee` / `deleted_at` / `created_at` / `updated_at`。
索引：`project_id`、`status`、`(project_id,status)`。

### 3.3 `workflow_instances`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID PK | |
| `thread_id` | VARCHAR(120) NOT NULL | **唯一索引 `uq_workflow_instances_thread_id`**；服务端派生 `wf-{id}`，历史行按此回填 |
| `project_id` | UUID FK CASCADE | |
| `task_id` | UUID FK SET NULL null | |
| `workflow_key` | VARCHAR(100) | 注册表 key，如 `dev_workflow` |
| `status` | VARCHAR(32) | pending / running / paused / waiting_approval / completed / failed / cancelled |
| `current_step` | VARCHAR(100) null | 当前节点名 |
| `state` | JSON/JSONB null | 图状态快照（**不对外暴露**） |
| `error_message` | TEXT null | |
| `started_at` / `finished_at` | TIMESTAMPTZ null | |
| `iteration` | INTEGER default 1 | 当前返工轮次 |
| `pending_payload` | JSON/JSONB null | 审批面板摘要（产物、预览、意见） |
| `pending_since` | TIMESTAMPTZ null | 进入待审的时间 |
| `pending_decision` | JSON/JSONB null | 已入库、图尚未消费的决定（兜底通道） |
| `last_decision` | VARCHAR(32) null | 最近一次决定 |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

索引：`project_id`、`task_id`、`status`、`(project_id,status)`。

### 3.4 `workflow_events`（只追加事件日志）

`id` / `workflow_instance_id`(FK CASCADE) / `sequence`(实例内递增) / `event_key`(幂等键，160) / `step`(节点名) / `event`(事件名) / `message` / `payload`(JSON) / `created_at`。
唯一约束：`(workflow_instance_id, event_key)`、`(workflow_instance_id, sequence)`。
事件名取值：`node_started`、`artifact_generated`、`validation_passed`、`validation_failed`、`approval_requested`、`approval_received`、`revision_handled`、`workflow_completed`、`workflow_failed`、`workflow_recovered`。

### 3.5 `artifacts`

`id` / `project_id`(FK CASCADE) / `task_id`(FK SET NULL) / `workflow_instance_id`(FK SET NULL) / `relative_path`(500) / `version` / `sha256`(64) / `file_type` / `size_bytes` / `review_status`(pending、approved、rejected、superseded) / `reviewed_by` / `reviewed_at` / `created_by` / `stage`(design、development、testing、delivery、other) / `original_filename` / `storage_path`(相对存储根的路径) / `created_at` / `updated_at`。
唯一：`uq_artifacts_project_path_version(project_id, relative_path, version)`、`uq_artifacts_storage_path`。

### 3.6 `approval_records`（只追加）

`id` / `project_id`(FK **RESTRICT**，审计轨迹不随项目消失) / `target_type`(task、artifact、workflow_instance) / `target_id`(多态引用，服务层校验存在性) / `decision`(approved、rejected、changes_requested) / `comment` / `approver` / `sequence`(每目标内递增) / `idempotency_key`(120 null，唯一索引 `uq_approval_records_target_idempotency`) / `created_at`（**无 `updated_at`，只追加**）。

---

## 4. 任务 4 的 LangGraph 与人工审批：实际实现方式

### 4.1 图结构（`backend/app/workflows/dev_workflow.py:500`）

```
START → load_task ─┬─(任务无效)→ fail_workflow → END
                    └→ generate_demo_artifact → validate_artifact
                                                    ├─(通过)→ human_approval ⚡interrupt
                                                    ├─(不通过, iteration < max)→ handle_revision_comments → generate_demo_artifact
                                                    └─(不通过, iteration >= max)→ fail_workflow
human_approval ─┬─(approved)→ complete_workflow → END
                 └─(rejected)→ handle_revision_comments → …
```

- 7 个节点，全部**本地模拟**，不调用任何大模型；产物由固定模板拼装（`## 需求描述` / `## 实现方案` / `## 验收标准`，返工轮追加 `## 修改意见`）。
- 校验规则：文件存在、SHA256 与库中一致、字节数 > 0、三个必需章节齐全、返工产物必须包含上一轮意见。

### 4.2 `thread_id` 的生成、保存与恢复

| 环节 | 实现 | 位置 |
| --- | --- | --- |
| 生成 | 服务层建实例时服务端派生 `f"wf-{instance_id}"`，**客户端无法指定** | `services/workflows.py:254` |
| 保存 | `workflow_instances.thread_id`，唯一索引；`0004` 迁移把历史行按 `wf-{id}` 回填 | `models/workflow.py:61`、`alembic/versions/0004_workflow_engine.py` |
| 寻址 | 配置恒为 `{"configurable": {"thread_id": instance.thread_id}}`；请求里的 `thread_id` 仅做一致性断言，不一致 → 409 | `services/workflows.py:176`、`services/workflows.py:295` |
| 持久化 | Checkpointer（生产 PostgreSQL / 本地与测试 SQLite / 内存），由 `WorkflowRuntime` 持有 | `services/workflow_runtime.py` |
| 恢复 | 运行时**归属应用实例**（lifespan 建、关时释放，存在 `app.state.workflow_runtime`）；「重启」= 新建应用实例重新打开同一份检查点 | `main.py:46`、`api/deps.py` |

> 关键设计：检查点持有连接与 `asyncio.Lock`，必须与打开它的应用同处一个事件循环，因此运行时**不是进程级单例**。

### 4.3 人工审批的实际链路

```
前端 POST /workflows/{id}/resume {thread_id, decision, approver, comment, idempotency_key?}
  └─ services/workflows.py: resume_workflow
       ├─ 1. 载入实例（404）→ 2. thread_id 比对（409）→ 3. 幂等键命中 → 直接回放当前状态（200）
       ├─ 4. 终态/pending/running → 409
       ├─ 5. waiting_approval 但无 decision → 409
       ├─ 6. 本轮已有审批记录 → 已应用则 409；未应用则复用该记录推进（崩溃恢复路径）
       └─ 7. 记录决定 → _apply_decision
             ├─ 写 approval_records（idempotency_key = client:<key> 或 req:<wf_id>:<iteration>）
             ├─ 写 workflow_instances.pending_decision = {decision, approver, comment, request_id}
             ├─ graph.ainvoke(Command(resume=decision), config)
             │    └─ human_approval 节点重跑 → _take_decision()
             │         ├─ 快通道：instance.pending_decision 且 request_id 匹配 → 直接用
             │         ├─ 兜底通道：读 workflow_events 中 event_key = "approval_received:<iteration>" 的 payload
             │         └─ 都没有 → interrupt(request) 真正暂停等待
             ├─ 落 approval_received 事件 + 清 pending_decision
             ├─ 标记产物 review_status = approved/rejected
             └─ 回写 state 快照
```

**决定为什么不会丢**：`interrupt()` 所在节点在恢复时会**从头重跑**，所以决定必须先落库再驱动图。
「决定已入库、进程崩溃在检查点落盘之前」这个窗口，由 `pending_decision` + `approval_received` 事件双通道兜住。

**幂等手段**（中断前的副作用全部幂等）：

| 副作用 | 幂等键 |
| --- | --- |
| 生成产物 | 相对路径 `workflow/{wf_id}/iteration-{n}/demo-artifact.md` + `uq_artifacts_project_path_version`；先查后写，命中即复用 |
| 写事件 | `(workflow_instance_id, event_key)` 唯一约束 |
| 写审批记录 | 唯一索引 `(target_type, target_id, idempotency_key)` |
| 状态推进 | 全部是绝对赋值，绝不增量 |

### 4.4 状态机

| 状态 | 含义 | 可执行操作 |
| --- | --- | --- |
| `pending` | 实例已建、图未跑 | —（resume → 409） |
| `running` | 正在执行节点 | —（resume → 409） |
| `waiting_approval` | 停在 `human_approval` | `resume` **必须**带 decision |
| `paused` | 重启后停在检查点 | `resume` 不带 decision，从检查点继续 |
| `completed` / `failed` / `cancelled` | 终态 | 只读（resume → 409） |

> `cancelled` 是**死枚举**：没有任何代码路径会写入它。

---

## 5. 前端四个页面与 API 依赖

前端现状：`src/views/` 只有 `HomeView.vue`(116 行)、`WorkbenchView.vue`(16 行占位)、`NotFoundView.vue`(13 行)；
`src/api/` 只有 `client.ts` + `health.ts`；**没有任何业务 API 封装、类型定义、业务 store 或表格/表单页面**。
导航菜单在 `AppSidebar.vue:9` 写死两项。

四个页面按后端现有能力与路线图「创建项目 → 上传 PRD → 启动工作流 → 暂停等待人工审核」推导（可调整）：

### P1 项目管理列表页（`/projects`）

| 动作 | 调用接口 | 现状 |
| --- | --- | --- |
| 列表 + 分页 + 搜索 + 状态过滤 | `GET /projects?page&page_size&status&keyword` | ✅ |
| 新建项目 | `POST /projects` | ✅ |
| 编辑项目 | `PUT /projects/{id}` | ✅ |
| 删除项目 | `DELETE /projects/{id}`（软删除，204） | ✅ |
| 展示任务数 | `ProjectListItem.task_count`（仅列表接口有） | ✅ |
| 跳转项目详情 | 前端路由 | 需新增 |

### P2 项目详情页（`/projects/:project_id`）

| 动作 | 调用接口 | 现状 |
| --- | --- | --- |
| 项目信息 | `GET /projects/{id}` | ✅ |
| 项目下的任务列表 | `GET /projects/{id}/tasks?page&page_size&status` | ✅ |
| 新建任务 | `POST /tasks` | ✅ |
| 任务数量 | `GET /projects/{id}/tasks` 的 `total` | ✅（详情接口不含 task_count） |
| 编辑/删除任务 | `PUT /tasks/{id}` / **无删除接口** | ⚠️ 任务只能改不能删（项目软删会级联软删任务） |
| 项目下的工作流 | **无接口** | ❌ 需新增 `GET /tasks/{task_id}/workflows` 或 `GET /projects/{id}/workflows` |

### P3 任务详情页（`/tasks/:task_id`）

| 动作 | 调用接口 | 现状 |
| --- | --- | --- |
| 任务信息 | `GET /tasks/{id}` | ✅ |
| 任务下的文件列表 | `GET /tasks/{id}/artifacts?page&page_size&review_status&stage&keyword` | ✅ |
| 上传文件 | `POST /tasks/{id}/artifacts`（multipart） | ✅ |
| 下载文件 | `GET /artifacts/{id}/download`（带 `X-Content-SHA256`） | ✅ |
| 新建版本 | `POST /artifacts/{id}/revisions` | ✅ |
| 文件审核 | `POST /artifacts/{id}/review` | ✅ |
| 启动工作流 | `POST /tasks/{id}/workflow/start` | ✅（该任务已有活动实例 → 409，`detail.existing_workflow_id` 可直接跳转） |
| 查看工作流状态 | `GET /workflows/{id}`（需要先有 `workflow_id`） | ⚠️ 刷新后丢失 `workflow_id`，需新增反查接口 |
| 查看执行日志 | `GET /workflows/{id}/logs` | ✅ |
| 推进/审批 | `POST /workflows/{id}/resume` | ✅ |

### P4 人工审批页（`/approvals`）

| 动作 | 调用接口 | 现状 |
| --- | --- | --- |
| 待审批列表 | **无接口** | ❌ **阻塞项**，需新增 `GET /workflows?status=waiting_approval` |
| 审批详情（产物预览、意见历史） | `GET /workflows/{id}` 的 `pending_approval` + `current_artifact` + `approvals` | ✅ |
| 产物全文 | `GET /artifacts/{current_artifact.id]/download` | ✅ |
| 通过 | `POST /workflows/{id}/resume`（`decision=approved` + `approver`） | ✅ |
| 驳回 | `POST /workflows/{id}/resume`（`decision=rejected` + `approver` + `comment`） | ✅ |
| 幂等提交 | 请求体带 `idempotency_key` | ✅ |
| 审批轨迹（跨实例/文件级） | **无接口** | ❌ 需新增 `GET /projects/{id}/approvals`（P1） |

**结论**：P1、P2、P3 用现有接口基本能做完（各缺 1 个反查类接口）；**P4 的待审批列表完全没有数据源**，必须先补后端列表接口。

---

## 6. 发现的问题与风险

### 6.1 阻塞级

| # | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| B1 | **没有工作流实例列表接口**，前端拿不到「谁在等我审批」 | P4 审批页无法实现 | 新增 `GET /workflows`（只新增，不改现有契约） |
| B2 | **没有 task → workflow 的反查接口** | P3 刷新后不知道 `workflow_id` | 新增 `GET /tasks/{task_id}/workflows` |
| B3 | **没有任何鉴权** | 任何人可审批、删除项目、传任意 `approver` | 本迭代可继续「无鉴权裸 API」，但必须在交付说明中写明；建议后续迭代引入最小鉴权 |

### 6.2 功能与契约缺口

| # | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| F1 | `approval_records` 无 HTTP 端点 | 文件级/任务级审批轨迹前端不可见 | 新增只读端点 |
| F2 | `cancelled` 是死枚举 | 状态机文档与实现不符 | 要么实现取消接口，要么从枚举移除（会改 CHECK 约束 → 需迁移） |
| F3 | `POST /artifacts/{id}/review` 与工作流审批**是两套独立语义** | 前端若让用户在两个地方批同一份产物，会出现状态不一致 | UI 上明确区分：「文件审核」≠「工作流审批」 |
| F4 | `GET /projects/{id}` 不返回 `task_count`（只有列表接口有） | 详情页要多发一次请求 | 前端用任务列表的 `total` 代替 |
| F5 | 任务无删除接口 | 误建任务只能改状态 | 需要时新增 `DELETE /tasks/{id}`（软删） |
| F6 | 审批人只能手填字符串 | 没有用户体系，审计价值有限 | 前端至少做成「选择器 + 可选手填」，为将来接真实身份留位 |

### 6.3 前端工程

| # | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| FE1 | `api/client.ts` 只有响应拦截器，**没有请求拦截器** | 将来接 token 要改客户端；现在也无法统一加请求头 | 预留请求拦截器（可先空实现） |
| FE2 | 错误只把 `message` 塞进 `Error.message`，**没有统一 `ElMessage` 提示**，也不暴露 `request_id` | 用户看不到可排查的关联号 | 统一错误处理：按 `code` 分类（404/409/422 提示不同文案），把 `request_id` 放到通知里 |
| FE3 | 没有共享 TS 类型（`src/types/` 不存在），类型全部内联在 api 文件 | 四个页面容易各写一份 interface | 建 `src/types/` 或 `src/api/types.ts` 统一放 DTO |
| FE4 | 导航菜单写死在 `AppSidebar.vue:9` | 加页面要改组件内部 | 改成路由表驱动（从 `router.getRoutes()` 过滤 meta） |
| FE5 | 没有业务 store | 刷新即丢状态（如 `workflow_id`） | 用 Pinia 存「当前项目/任务/工作流」上下文 |
| FE6 | 没有 loading / empty / error 三态组件 | 列表页体验会差 | 抽 `components/common/PageState.vue` |
| FE7 | `vite.config.ts` 代理 `/api` → `http://localhost:8000`，前端 `baseURL` 默认 `/api/v1` | 生产走 nginx 代理 `/api/` → `backend:8000`，路径一致 ✅ | 无需改，但要注意 nginx 里 `proxy_pass` 不带尾斜杠的写法已正确 |
| FE8 | `tsconfig` 开了 `noUnusedLocals/Parameters` | 提交前必须过 `npm run type-check` | 每个页面完成即跑一次 |

### 6.4 容器与部署

| # | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| D1 | **本机没有 Docker**（`docker` / `docker compose` 均不存在） | 「Docker 部署验证」在本机**无法执行**，只能标「未执行」 | 需要一台有 Docker 的机器或 CI runner；本机只能验证 compose 文件语法与配置一致性 |
| D2 | `backend/Dockerfile` 只 `pip install .`，**不装 `.[dev]`** | 容器内没有 pytest，compose 里无法跑测试 | 若要容器内测试，改为多阶段或加 `pip install .[dev]` |
| D3 | `frontend/Dockerfile` 用 `npm install` 而非 `npm ci` | 构建不可复现（锁文件可能不被严格遵守） | 改 `npm ci`（需要 `package-lock.json` 存在） |
| D4 | frontend 容器以 root 运行（nginx 官方镜像默认） | 安全基线偏低 | 可加 `USER nginx` 或改用非 root 镜像 |
| D5 | `migrate` 服务执行 `python scripts/init_db.py`（建业务库 + 建 checkpoint 库 + alembic upgrade） | 已能自动建库，✅；但 checkpoint 库与业务库在**同一个 PG 实例**的两个 database | 保持现状即可，注意 `CHECKPOINT_POSTGRES_DB` 可配 |
| D6 | compose 未注入 `DB_POOL_*`、`CORS_ALLOW_*`、`WORKFLOW_SQLITE_CHECKPOINT_PATH` | 走代码默认值（当前可接受） | 如需调参再加 |
| D7 | 无 CI（无 `.github/workflows/`、无 `.gitlab-ci.yml`） | 每次验证靠手工 | 任务 6 可顺带加一条最小 CI：ruff + pytest + type-check |
| D8 | `frontend/nginx.conf` 代理 `/api/` → `http://backend:8000`，但**没有把 `/api/v1` 截断** | 前端 `baseURL=/api/v1` → nginx 转发 `/api/v1/xxx` → 后端路由 `/api/v1/xxx` ✅ 正确 | 无需改动 |
| D9 | CORS 默认只允许 `localhost:5173 / localhost` | 部署到其它域名需改 `CORS_ORIGINS` | 部署文档中注明 |

### 6.5 GitLab 接入（任务 6）

| # | 问题 | 影响 |
| --- | --- | --- |
| G1 | 无 `python-gitlab` 依赖 | 需新增（可只用 `httpx` 手写 REST 调用，依赖更少） |
| G2 | `projects` 表**没有仓库地址字段** | 需要一处绑定关系，两个方案见任务 6 计划文档 |
| G3 | 没有任何 git 操作能力（clone/pull/校验） | `app/services/gitlab.py` 从零实现 |
| G4 | 容器镜像里**没有 git**（`python:3.11-slim` 只装了 curl） | 若在容器内 clone，Dockerfile 必须加 `apt-get install git` |
| G5 | 网络到 gitlab.com 可达（已实测：`GET https://gitlab.com/api/v4/version` 返回 GitLab 自身的 401 与 `ratelimit-*` 头，说明出口网络通） | 真实接入可在本机部分验证；需要一个可用 Token 与目标项目 |
| G6 | 凭据管理 | `GITLAB_TOKEN` 必须只进环境变量 / `.env`，**不得进仓库**；日志只打脱敏值 |

---

## 7. 与任务 4 的关系（不改写已完成工作）

本次检查确认任务 4 的实现是**自洽且可用的**，无需重写。以下三点属于「任务 4 留下的接口缺口」，建议以**新增**方式补齐，不改动现有路径、请求体或响应体：

1. `GET /api/v1/workflows`（实例列表 / 待审批列表）——新增。
2. `GET /api/v1/tasks/{task_id}/workflows`（任务 → 工作流反查）——新增。
3. `GET /api/v1/projects/{project_id}/approvals`（审批轨迹查询）——新增（P1，可延后）。

其余全部按现有契约直接对接即可；现有的 83 个后端用例（其中 11 个覆盖工作流与审批）必须保持全绿。
