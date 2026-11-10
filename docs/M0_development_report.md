# M0 交付报告：任务 5、任务 6 共享基础开发

- 阶段：**M0 —— 后端工作流查询接口补充 + 前端基础架构建设**
- 实施日期：2026-11-10
- 工作分支：`develop`（基线 `bd492dd`）
- 前置文档：`docs/task5_task6_api_inventory.md`、`docs/task5_task6_implementation_plan.md`
- 范围：只做 M0。**未**开发四个业务页面、**未**开发 GitLab 功能、**未**修改 Docker 配置

---

## 1. 本阶段实现内容

### 1.1 后端：两个只增不改的查询接口

| 端点 | 说明 |
| --- | --- |
| `GET /api/v1/workflows` | 工作流实例列表，支持 `page`、`page_size`、`status`、`project_id`、`task_id`，按 `created_at DESC, id` 排序，过滤条件可任意组合 |
| `GET /api/v1/tasks/{task_id}/workflows` | 某个任务关联的全部工作流实例（含历史终态实例），任务不存在或已软删除时返回 404 |

实现要点：

- **复用既有模型与 Schema**：返回类型仍是 `Page[WorkflowRead]`，与详情接口 `GET /workflows/{id}` 完全同构；未新增任何 Pydantic 模型。
- **复用既有数据访问逻辑**：新增 `services/workflow_store.py::list_instances()`，与该模块既有的 `list_events()` 同风格（同一条 `stmt` 派生 count 查询、`order_by(...).offset().limit()`）；视图组装复用 `services/workflows.py::to_read()`。
- **视图组装去重**：`to_read()` 原先把字段拼装和查询写在一起，本次把「拼装」抽成 `_build_view()`，`to_read()`（单条）与新增的 `_to_read_many()`（批量）共用它，字段映射只有一份。
- **批量查询避免 N+1**：列表页会被浏览器轮询，`_to_read_many()` 用 **2 条查询**取回一页内所有实例的当前产物与审批轨迹，而不是每行 2 条。
- **不暴露内部状态**：返回的 `WorkflowRead` 不含 `state`、checkpoint id 等图内部字段（测试中显式断言 `"state" not in item`）。
- **未改动任务 4 逻辑**：`dev_workflow.py`、检查点运行时、审批双通道、幂等键、启动/恢复/审批逻辑一行未动。

### 1.2 前端：统一基础架构

| 交付物 | 内容 |
| --- | --- |
| `src/types/index.ts` | 10 个要求类型 + 8 个枚举联合类型 + 请求体类型，字段与后端 Pydantic Schema 一一对应 |
| `src/api/*.ts` | 5 个业务 API 模块 + 改造后的 `client.ts` 与 `index.ts` |
| `src/api/client.ts` | 统一错误处理：按 `code` 分类提示、错误文本始终带 `request_id`、404/409/422/503 分别处理；补请求拦截器；支持 `silent` 选项让页面自行接管错误 |
| `src/components/common/PageState.vue` | loading / empty / error 三态组件，带插槽 |
| `src/components/common/StatusTag.vue` | 项目、任务、工作流、产物、审批结论、优先级的状态映射**唯一来源** |
| `src/utils/format.ts` | 日期时间、日期、文件大小、路径、文件名、相对时间格式化 |
| `src/router/index.ts` | 新增 5 条路由 + `RouteMeta` 类型扩展（`title` / `icon` / `hideInMenu` / `activeMenu`） |
| `src/components/layout/AppSidebar.vue` | 导航改为**路由表驱动**，新增页面无需再改组件 |
| `src/stores/workspace.ts` | 当前项目 / 任务 / 工作流的页面上下文（缓存，非唯一数据源） |

**文件上传 / 下载约定**：

- axios 实例**不再固定** `Content-Type: application/json`。axios 会根据请求体自动决定：对象 → `application/json`，`FormData` → `multipart/form-data` 并自行生成 boundary。原来的固定头会破坏所有上传（boundary 不匹配）。
- 下载使用 `responseType: 'blob'`，同时从响应头取 `X-Content-SHA256` 与 `Content-Disposition` 中的文件名。
- 前端不保存任何 GitLab Token（本阶段也没有 GitLab 代码）。

---

## 2. 新增和修改的文件

### 2.1 后端

| 文件 | 动作 | 说明 |
| --- | --- | --- |
| `backend/app/api/v1/endpoints/workflows.py` | 修改 | 新增两个端点；既有 4 个端点未改 |
| `backend/app/services/workflow_store.py` | 修改 | 新增 `list_instances()`；既有函数未改 |
| `backend/app/services/workflows.py` | 修改 | 新增 `list_workflows()`、`list_task_workflows()`、`_to_read_many()`、`_build_view()`；`to_read()` 改为调用 `_build_view()`，行为不变 |
| `backend/tests/test_workflow_listing.py` | **新增** | 12 个用例，既有测试文件一个字节未改 |

### 2.2 前端

| 文件 | 动作 |
| --- | --- |
| `frontend/src/types/index.ts` | 新增 |
| `frontend/src/api/projects.ts` | 新增 |
| `frontend/src/api/tasks.ts` | 新增 |
| `frontend/src/api/artifacts.ts` | 新增 |
| `frontend/src/api/workflows.ts` | 新增 |
| `frontend/src/api/approvals.ts` | 新增 |
| `frontend/src/api/client.ts` | 修改 |
| `frontend/src/api/index.ts` | 修改 |
| `frontend/src/components/common/PageState.vue` | 新增 |
| `frontend/src/components/common/StatusTag.vue` | 新增 |
| `frontend/src/utils/format.ts` | 新增 |
| `frontend/src/stores/workspace.ts` | 新增 |
| `frontend/src/stores/index.ts` | 修改（导出新 store） |
| `frontend/src/router/index.ts` | 修改 |
| `frontend/src/components/layout/AppSidebar.vue` | 修改 |
| `frontend/src/views/projects/ProjectListView.vue` | 新增（占位） |
| `frontend/src/views/projects/ProjectDetailView.vue` | 新增（占位） |
| `frontend/src/views/tasks/TaskDetailView.vue` | 新增（占位） |
| `frontend/src/views/workflows/WorkflowListView.vue` | 新增（占位） |
| `frontend/src/views/approvals/ApprovalQueueView.vue` | 新增（占位） |

> **关于占位页面**：M0 要求路由与导航可用且构建通过，但又不允许提前开发业务页面。5 个新路由各配了一个 10 行左右的占位视图（沿用仓库既有 `WorkbenchView.vue` 的占位风格），只显示路由参数与「将在 Mx 实现」的说明。M1–M5 逐个替换为真实页面。

### 2.3 文档

| 文件 | 动作 |
| --- | --- |
| `docs/M0_development_report.md` | 新增（本文件） |

---

## 3. 新增 API 的完整请求响应示例

以下响应均为**真实启动后端服务**（uvicorn + 临时 SQLite 库 + 真实 Alembic 迁移）后抓取，非构造数据。

### 3.1 `GET /api/v1/workflows`

**请求**

```
GET /api/v1/workflows?page=1&page_size=20&status=waiting_approval&project_id=<uuid>&task_id=<uuid>
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `page` | integer ≥ 1 | 否，默认 1 | 页码 |
| `page_size` | integer 1–100 | 否，默认 20 | 每页条数 |
| `status` | enum | 否 | `pending` / `running` / `paused` / `waiting_approval` / `completed` / `failed` / `cancelled` |
| `project_id` | uuid | 否 | 只返回该项目的实例 |
| `task_id` | uuid | 否 | 只返回该任务的实例 |

**响应 200**

```json
{
  "items": [
    {
      "id": "f74138af-3833-49c6-8715-2230d80d2baa",
      "project_id": "73a539d2-d37b-4065-831b-0bfff184ca54",
      "task_id": "2f054353-9ca3-441e-9300-fabc354bfaf3",
      "workflow_key": "dev_workflow",
      "thread_id": "wf-f74138af-3833-49c6-8715-2230d80d2baa",
      "status": "waiting_approval",
      "current_step": "human_approval",
      "iteration": 1,
      "current_artifact": {
        "id": "f5cddb35-acbb-41df-82f4-c0eec4a69c2a",
        "relative_path": "workflow/f74138af-3833-49c6-8715-2230d80d2baa/iteration-1/demo-artifact.md",
        "version": 1,
        "sha256": "3638db939a1ff108c4fa0fe631063317f26ffebde6b557640f16db8a70010a7b",
        "size_bytes": 386,
        "review_status": "pending"
      },
      "pending_approval": {
        "request_id": "f74138af-3833-49c6-8715-2230d80d2baa:1",
        "iteration": 1,
        "artifact_id": "f5cddb35-acbb-41df-82f4-c0eec4a69c2a",
        "artifact_version": 1,
        "preview": "# 模拟研发产物 - M0 冒烟任务\n\n- 工作流实例: f74138af-3833-49c6-8715-2230d80d2baa\n- 迭代轮次: 1\n- 任务: 2f054353-9ca3-441e-9300-fabc354bfaf3\n\n## 需求描述\n本节由模拟节点生成，未调用任何大模型。\n\n## 实现方案\n本节描述实现方案，同样由模拟节点生成。\n\n## 验收标准\n本节描述验收标准，同样由模拟节点生成。\n",
        "revision_comments": [],
        "requested_at": "2026-11-10T07:05:51.239357Z"
      },
      "approvals": [],
      "started_at": "2026-11-10T07:05:50.931416",
      "finished_at": null,
      "error_message": null,
      "created_at": "2026-11-10T07:05:50",
      "updated_at": "2026-11-10T07:05:51"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

### 3.2 `GET /api/v1/tasks/{task_id}/workflows`

**请求**

```
GET /api/v1/tasks/2f054353-9ca3-441e-9300-fabc354bfaf3/workflows?page=1&page_size=20
```

**响应 200**

```json
{
  "items": [
    {
      "id": "f74138af-3833-49c6-8715-2230d80d2baa",
      "project_id": "73a539d2-d37b-4065-831b-0bfff184ca54",
      "task_id": "2f054353-9ca3-441e-9300-fabc354bfaf3",
      "workflow_key": "dev_workflow",
      "thread_id": "wf-f74138af-3833-49c6-8715-2230d80d2baa",
      "status": "waiting_approval",
      "current_step": "human_approval",
      "iteration": 1,
      "current_artifact": { "...": "与上一响应一致" },
      "pending_approval": { "...": "与上一响应一致" },
      "approvals": [],
      "started_at": "2026-11-10T07:05:50.931416",
      "finished_at": null,
      "error_message": null,
      "created_at": "2026-11-10T07:05:50",
      "updated_at": "2026-11-10T07:05:51"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

### 3.3 错误响应

| 场景 | 状态码 | 响应体 |
| --- | --- | --- |
| 任务不存在 | 404 | `{"code":"NOT_FOUND","message":"任务 00000000-0000-0000-0000-000000000000 不存在","detail":null,"request_id":"d8fe34400c91416ba23db403ec76f336","timestamp":"..."}` |
| 状态值非法 | 422 | `{"code":"VALIDATION_ERROR","message":"Request validation failed","detail":[{"type":"enum","loc":["query","status"],"msg":"Input should be 'pending', 'running', 'paused', 'waiting_approval', 'completed', 'failed' or 'cancelled'","input":"does_not_exist"}],"request_id":"...","timestamp":"..."}` |
| 分页参数越界 | 422 | `{"code":"VALIDATION_ERROR","message":"Request validation failed","detail":[...],"request_id":"...","timestamp":"..."}` |

---

## 4. 后端测试结果

命令：`cd backend && python -m pytest -q`

```
95 passed, 1 warning in 29.22s
```

| 项 | 结果 |
| --- | --- |
| 既有测试（开发前基线） | 83 passed |
| 既有测试（开发后） | 83 passed —— **一个都没被修改或删除** |
| 新增测试 `tests/test_workflow_listing.py` | 12 passed |
| 合计 | **95 passed** |

新增用例覆盖（对应指令的 9 项要求）：

| # | 用例 | 覆盖点 |
| --- | --- | --- |
| 1 | `test_the_workflow_list_returns_the_runs` | 列表查询；断言不含 `state` / `checkpoint_id` |
| 2 | `test_the_workflow_list_is_ordered_newest_first` | 排序（`created_at` 倒序） |
| 3 | `test_the_workflow_list_is_paginated` | 分页：total / pages / 两页不重叠 / 三条齐全 |
| 4 | `test_the_workflow_list_can_be_filtered_by_status` | status 过滤 |
| 5 | `test_the_workflow_list_can_be_filtered_by_project` | project_id 过滤 |
| 6 | `test_the_workflow_list_can_be_filtered_by_task` | task_id 过滤 |
| 7 | `test_the_workflow_list_combines_the_filters` | 多条件组合 |
| 8 | `test_the_workflow_list_rejects_an_unknown_status` | 非法状态 422 |
| 9 | `test_the_runs_of_a_task_are_listed` | 任务反查（含直接写入数据库的历史终态实例） |
| 10 | `test_the_runs_of_a_task_are_paginated` | 反查分页 |
| 11 | `test_an_unknown_task_has_no_runs` | 任务不存在 404 |
| 12 | `test_a_deleted_task_has_no_runs` | 软删除任务 404；工作流历史本身仍然保留 |

其它后端检查：

| 命令 | 结果 |
| --- | --- |
| `python -m ruff check .` | `All checks passed!` |
| `python -m alembic upgrade head` | 4 个迁移依次执行成功，current = `0004_workflow_engine (head)` |
| `python -m alembic check` | `No new upgrade operations detected.` |

> **本阶段零新增迁移**：`alembic/versions/` 仍是 0001–0004 四个文件，模型、迁移与数据库结构三者一致。

---

## 5. 前端类型检查和构建结果

命令：`cd frontend && npm run type-check` / `npm run build`（Node v24.20.0，npm 11.19.0）

| 命令 | 结果 |
| --- | --- |
| `npm run type-check` | **通过**，无输出（`vue-tsc --noEmit` + `tsc --noEmit`） |
| `npm run build` | **通过**，`✓ 1710 modules transformed`，`✓ built in 22.33s` |

构建产物包含 5 个新的懒加载 chunk（`ProjectListView` / `ProjectDetailView` / `TaskDetailView` / `WorkflowListView` / `ApprovalQueueView`），证明新路由与组件引用链完整。

> 既有告警（非本阶段引入）：主 chunk 1,277 kB 超过 Vite 的 500 kB 提示阈值，来源是 Element Plus 全量引入。M1 引入更多页面后可一并处理（按需引入或 manualChunks）。

---

## 6. OpenAPI 契约对比结果

方法：用 `git archive HEAD backend` 导出**基线代码**到临时目录，分别导出基线与当前的 `create_app().openapi()`，逐路径、逐 schema 做深度对比（导出前确认 `app.__file__` 指向各自的代码目录，排除 editable 安装串包）。

| 对比项 | 基线（HEAD） | 当前 | 结论 |
| --- | --- | --- | --- |
| 端点总数 | 16 | 18 | +2 |
| 新增路径 | — | `/api/v1/workflows`、`/api/v1/tasks/{task_id}/workflows` | 符合预期 |
| 删除路径 | — | — | 无 |
| 既有路径定义发生变化的 | — | **0 个** | 无非预期变化 |
| 新增 schema | — | `Page_WorkflowRead_` | 分页信封，本就存在同族 schema |
| 删除 schema | — | — | 无 |
| 既有 schema 定义发生变化的 | — | **0 个** | 无非预期变化 |

四个既有工作流接口逐一比对结果：**全部「一致」**

- `POST /api/v1/tasks/{task_id}/workflow/start`
- `GET /api/v1/workflows/{workflow_id}`
- `POST /api/v1/workflows/{workflow_id}/resume`
- `GET /api/v1/workflows/{workflow_id}/logs`

---

## 7. 遗留问题

| # | 问题 | 影响 | 处置 |
| --- | --- | --- | --- |
| 1 | 5 个新路由目前是占位视图 | 页面不可用 | 按计划在 M1–M5 逐个替换；占位视图不包含任何 Mock 数据 |
| 2 | 任务没有删除接口 | 误建任务只能改状态 | 沿用既有约定（项目软删会级联软删任务），前端不显示删除按钮 |
| 3 | `approval_records` 无 HTTP 端点 | 跨实例审批轨迹前端取不到 | `src/api/approvals.ts` 只封装了**真实存在**的审批动作（workflow resume）与轨迹读取（取自 workflow 视图），**没有虚构** `GET /projects/{id}/approvals`；待后续确认后补 |
| 4 | 无鉴权 | 任何人可审批、可传任意 `approver` | 本阶段维持现状；前端预留「审批人选择器 + 可填」入口（M5） |
| 5 | `cancelled` 仍是死枚举 | 状态机与实现不一致 | 未改动枚举（改枚举要动 CHECK 约束 → 需要迁移） |
| 6 | `created_at` 在 SQLite 下只有秒级精度 | 同一秒创建的多条实例其 `created_at` 相同 | 排序追加 `id` 作为稳定的次序键；测试断言「非递增」而非严格递减 |
| 7 | 前端主 chunk 偏大 | 首屏加载 | 既有现象，M1 后一并优化 |

---

## 8. 下一阶段建议

### 8.1 立即可做（无需等待确认）

**M1：P1 项目管理列表页** —— 依赖本阶段的 `src/api/projects.ts`、`PageState.vue`、`StatusTag.vue`、`format.ts`。
建议要点：表格列用 `StatusTag` 渲染状态、`keyword` 输入防抖 300 ms、`page`/`status`/`keyword` 同步到 URL query、新建/编辑用同一个对话框组件。

### 8.2 M1 之后

**M2：P2 项目详情页** —— 用 `GET /workflows?project_id=` 一次性取回项目下全部实例再按 `task_id` 分组，**不要**逐任务调 `GET /tasks/{id}/workflows`（N+1）。同时它是后续 GitLab 绑定面板的宿主页面。

### 8.3 需要决策后再做

| 决策点 | 阻塞内容 | 建议 |
| --- | --- | --- |
| D-1 / D-2：GitLab 绑定建模（`projects` 加列 vs 独立表）、是否允许迁移 0005 | 任务 6 的 T6-2 及其后全部工作 | 推荐方案 A（加列），迁移只做 `add_column`，SQLite 安全、零影响既有接口 |
| D-6：本迭代是否实现 clone/pull | T6-4 | 建议实现，但用**本地 bare 仓库**做自动化测试，不依赖外网 |
| D-5：Docker 整栈验证在哪台机器执行 | T6-6 | 本机无 Docker，需一台开发机或 CI Runner；建议顺带加一条最小 CI（ruff + pytest + type-check） |
| 是否引入最小鉴权 | 全平台的可信度 | 建议单列一个迭代，不与任务 5/6 混做 |

### 8.4 交接注意

- 本阶段**未提交**：工作区保留全部改动，等待验收后再决定提交方式。
- 新增端点是**纯增量**：若后续想回退 M0，只需移除 `workflows.py` 端点文件里的两个路由与 `workflow_store.list_instances()`，既有契约不受影响。
- `src/api/client.ts` 去掉了实例级 `Content-Type: application/json`。这是**上传功能的前提**（否则 multipart boundary 缺失），后续任何上传相关改动都不要把它加回来。

---

## 9. 与前置检查报告的差异说明

开发前逐项核对了前置检查报告，**未发现实际代码与报告不一致**：

| 报告中的结论 | 实际核对结果 |
| --- | --- |
| 既有 21 个端点 | 一致（OpenAPI 逐条比对） |
| 无工作流列表接口 | 一致（本次新增） |
| `approval_records` 无 HTTP 端点 | 一致（前端未虚构该接口） |
| `cancelled` 为死枚举 | 一致（未改动） |
| `GET /projects/{id}` 不含 `task_count` | 一致 |
| 任务无删除接口 | 一致 |
| `services/workflow_store.py` 无实例列表方法 | 一致（本次新增 `list_instances`） |
| 任务 4 代码无未提交修改 | 一致（开发前 `git status` 仅两个未跟踪的 docs 文件） |
