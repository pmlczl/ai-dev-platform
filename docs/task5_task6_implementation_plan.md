# 任务 5 / 任务 6 开发实施计划

- 状态：**待确认**（本轮只做检查与文档，未修改任何业务代码）
- 前置文档：[`docs/task5_task6_api_inventory.md`](./task5_task6_api_inventory.md)（接口与工程事实清单）
- 依据：`create_app().openapi()` 导出的 21 个既有端点 + 后端/前端/容器源码逐项勘察
- 本文中所有标注「**新增**」的接口，**当前都不存在**，属于本计划的待实现项；标注「既有」的才是可对接的现状

## 0. 硬约束（来自本轮指令，逐条落到本计划）

| # | 约束 | 本计划的落实方式 |
| --- | --- | --- |
| C1 | 不重写任务 4 | 任务 4 的图、节点、`thread_id` 规则、审批双通道、幂等键全部不动；后端只做**新增端点**，不碰 `dev_workflow.py`、`services/workflows.py` 的既有逻辑 |
| C2 | 不擅自改现有数据库结构与 API 契约 | **任务 5 阶段零迁移**：所需数据全部来自既有 6 张表。任务 6 需要新增绑定字段 ⇒ 单列为决策点 D-1/D-2，等确认后再写迁移 |
| C3 | 不虚构已存在的接口 | 既有 21 个端点以 OpenAPI 导出为准；其余一律标注「新增」 |
| C4 | 不为让检查通过而删已有测试 | 现有 83 个后端用例（其中 11 个覆盖工作流与审批）必须保持全绿；新增用例只增不改 |
| C5 | 未真实执行的验证要标注 | 本机无 Docker ⇒ 整栈验证标「未执行」并给出复验命令；GitLab 真实验证需要 Token 与目标仓库，同样标注 |

---

## 1. 总览：两条线与里程碑

```
                    ┌─────────────────────────────────────────────┐
                    │  M0 共享前置（后端只增接口 + 前端地基）      │
                    │  S5-1 GET /workflows, GET /tasks/{id}/workflows │
                    │  S5-0 types / api 封装 / 错误处理 / 三态组件   │
                    └───────────────┬─────────────────────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              │                                           │
   ┌──────────▼───────────┐                    ┌──────────▼───────────┐
   │ 任务 5：前端四个页面  │                    │ 任务 6：GitLab 后端  │
   │ S5-2 P1 项目列表     │                    │ T6-1 REST 客户端      │
   │ S5-3 P2 项目详情 ★   │◄── GitLab 绑定 UI  │ T6-2 绑定建模 (待确认) │
   │ S5-4 P3 任务详情     │    入口落在 P2     │ T6-3 GitLab API      │
   │ S5-5 P4 人工审批     │                    │ T6-4 仓库同步         │
   └──────────┬───────────┘                    └──────────┬───────────┘
              │                                           │
   ┌──────────▼───────────┐                    ┌──────────▼───────────┐
   │ S5-6 前端联调验收     │                    │ T6-5 容器改造         │
   │ npm type-check/build │                    │ T6-6 Docker 整栈验证★ │
   └──────────────────────┘                    │ T6-7 最小 CI (可选)   │
                                                └──────────────────────┘
★ = 有前置依赖 / 有环境限制
```

| 里程碑 | 内容 | 交付物 | 前置 |
| --- | --- | --- | --- |
| M0 | 后端只增接口（S5-1）+ 前端地基（S5-0） | 2 个新端点 + `src/api/*`、`src/types/*`、公共组件 | — |
| M1 | 任务 5 的 P1 项目管理列表页 | `ProjectListView.vue` 等 | M0 |
| M2 | 任务 5 的 P2 项目详情页（同时是 GitLab 绑定 UI 宿主） | `ProjectDetailView.vue` 等 | M0、M1 |
| M3 | 任务 6 的 GitLab 后端接入 | `services/gitlab.py` + 新端点 | 决策点 D-1/D-2 确认 |
| M4 | 任务 5 的 P3 任务详情页（工作流 + 产物） | `TaskDetailView.vue` 等 | M0、M2 |
| M5 | 任务 5 的 P4 人工审批页 | `ApprovalQueueView.vue` 等 | M0、M4 |
| M6 | 任务 6 的容器改造与 Docker 整栈验证 | Dockerfile/compose 改动 + 验证记录 | M3；**需一台有 Docker 的机器** |

---

## 2. 任务 5：前端四个页面

### 2.1 阶段划分与顺序

顺序：**S5-1（后端补口） → S5-0（前端地基） → P1 → P2 → P3 → P4 → S5-6（联调验收）**

理由：
- P4 审批页没有 `GET /workflows` 就无法开工，必须先补后端；
- P1 是最简单的 CRUD 列表，用来验证「地基 → 页面」的模板跑得通；
- P2 需要 P1 的路由与表格模板；
- P3 依赖 P2 的任务列表与「任务→工作流」反查；
- P4 的审批对象是 P3 产出的工作流实例，最晚做。

### 2.2 S5-1 后端只增接口（**新增，不改既有端点**）

| 方法 | 路径 | 参数 | 响应 | 说明 |
| --- | --- | --- | --- | --- |
| **新增** | `GET /api/v1/workflows` | `page`、`page_size`、`status?`、`project_id?`、`task_id?` | `Page[WorkflowRead]` | 审批页待办列表的数据源；同时覆盖 P2 的「项目下工作流」需求，避免 N+1 |
| **新增** | `GET /api/v1/tasks/{task_id}/workflows` | `page?`、`page_size?` | `Page[WorkflowRead]` | 任务 → 工作流反查，刷新页面后仍能找回 `workflow_id` |
| **新增**（P1，可延后） | `GET /api/v1/projects/{project_id}/approvals` | `page`、`page_size`、`target_type?` | `Page[ApprovalRecordRead]` | `approval_records` 目前**没有任何 HTTP 端点**；schema 已存在 `schemas/approval.py:ApprovalRecordRead` |

实现要点：
- 服务层新增 `list_workflow_instances(session, params, status, project_id, task_id)`，复用 `services/workflow_store.py` 现有的 `get_instance` / `find_active_instance` 风格；`WorkflowRead` 组装复用 `services/workflows.py:to_read`（已存在，**不改**）；
- `GET /workflows` 的排序固定为 `created_at DESC, id`，与 `list_projects` 的写法保持一致；
- `GET /tasks/{task_id}/workflows` 必须先校验任务存在（404），任务软删后返回空列表；
- 路由注册在既有 `app/api/v1/endpoints/workflows.py`（不新建文件也不改 `router.py` 的注册方式，避免无谓改动）；
- 新增测试文件 `backend/tests/test_workflow_listing.py`（**新增文件，不动 `test_workflow_approval.py`**），覆盖：分页与过滤、任务反查、软删任务行为、不存在任务 404。

验收：
- `python -m pytest -q` 全绿，用例数 ≥ 83 + 新增数（预期 83 + 8 左右）；
- `python -m ruff check .` 零错误；
- `python -m alembic upgrade head` 后**不产生任何新迁移**（本阶段零迁移，用 `alembic revision --autogenerate` 生成空 diff 作为证据）；
- 既有 5 个工作流端点的 OpenAPI 定义逐字未变（导出 diff 为空）。

### 2.3 S5-0 前端地基

| 类别 | 新增 / 修改 | 要点 |
| --- | --- | --- |
| 类型 | **新增** `src/types/index.ts` | 集中放 `Page<T>`、`ProjectRead`、`ProjectListItem`、`TaskRead`、`ArtifactRead`、`WorkflowRead`、`WorkflowEventRead`、`ApprovalRecordRead`、`PendingApproval`、`ApiErrorPayload`；解决 FE3（四个页面各写一份 interface） |
| API 封装 | **新增** `src/api/projects.ts` `tasks.ts` `artifacts.ts` `workflows.ts` `approvals.ts`；**修改** `src/api/index.ts` 统一 `export *` | 只做请求，不含 UI 逻辑（符合 `agents.md` 的目录职责） |
| 错误处理 | **修改** `src/api/client.ts` | ① 补请求拦截器（预留 `Authorization`，解决 FE1）；② 响应拦截器按 `code` 分类（404/409/422/503 各自文案）并弹出 `ElMessage`，把 `request_id` 一起带上，解决 FE2 |
| 公共组件 | **新增** `src/components/common/PageState.vue` | loading / empty / error 三态（FE6） |
| 公共组件 | **新增** `src/components/common/StatusTag.vue` | 项目/任务/工作流/产物四套状态 → 颜色映射，避免每页硬编码 |
| 工具 | **新增** `src/utils/format.ts` | 时间、字节、路径的显示格式化 |
| 导航 | **修改** `src/components/layout/AppSidebar.vue` | 由 `router.getRoutes()` 过滤 `meta.title` 生成菜单（FE4），新增 `/projects`、`/approvals` 路由后侧边栏自动出现 |
| 路由 | **修改** `src/router/index.ts` | 追加 `/projects`、`/projects/:project_id`、`/tasks/:task_id`、`/approvals` 四条路由，全部懒加载；保留既有 3 条路由不变 |
| 状态 | **新增** `src/stores/workspace.ts` | 记录当前项目/任务/工作流上下文，跨页跳转时携带（FE5） |

验收：
- `npm run type-check` 零错误（含 `noUnusedLocals`/`noUnusedParameters` 约束，FE8）；
- `npm run build` 成功；
- 侧边栏在未接业务数据时也能正常渲染，不出现空路由项。

### 2.4 S5-2 / P1 项目管理列表页（`/projects`）

| 动作 | 调用接口 | 状态 |
| --- | --- | --- |
| 列表 + 分页 + 搜索 + 状态过滤 | `GET /projects?page&page_size&status&keyword` | 既有 |
| 新建 / 编辑 | `POST /projects`、`PUT /projects/{id}` | 既有 |
| 删除（软删，204） | `DELETE /projects/{id}` | 既有 |
| 展示任务数 | `ProjectListItem.task_count` | 既有（仅列表接口有） |

新增文件：`src/views/projects/ProjectListView.vue`、`src/components/project/ProjectFormDialog.vue`。

关键实现要点：
- 表头：编号 / 名称 / 状态 / 负责人 / 任务数 / 更新时间 / 操作；
- `keyword` 输入防抖 300ms；`page`、`status`、`keyword` 同步到 URL query（刷新后条件不丢）；
- 删除二次确认，提示「软删除，任务一并归档」；
- 编辑对话框复用 `ProjectCreate`/`ProjectUpdate` 的字段约束（`code` 正则 `^[A-Za-z0-9][A-Za-z0-9._-]*$`、名称 1–200）。

验收：
- 新建项目后列表首行可见且 `task_count = 0`；
- 搜索「不存在的关键词」返回空列表并显示空态，不报错；
- 分页第 2 页与第 1 页数据不重复；
- 删除后列表不再出现该项目，直接访问 `/projects/{id}` 详情返回 404；
- `npm run type-check` 通过。

### 2.5 S5-3 / P2 项目详情页（`/projects/:project_id`）

| 动作 | 调用接口 | 状态 |
| --- | --- | --- |
| 项目信息 | `GET /projects/{id}` | 既有 |
| 项目下任务列表 | `GET /projects/{id}/tasks?page&page_size&status` | 既有 |
| 新建 / 编辑任务 | `POST /tasks`、`PUT /tasks/{id}` | 既有 |
| 任务数量 | 任务列表响应的 `total` | 既有（`GET /projects/{id}` 不含 `task_count`，F4） |
| 项目下工作流 | `GET /workflows?project_id=` **新增** | 新增（S5-1） |
| GitLab 仓库绑定 | **新增**（任务 6，T6-3） | 依赖 M3，见 §4 依赖关系 |

新增文件：`src/views/projects/ProjectDetailView.vue`、`src/components/task/TaskTable.vue`、`src/components/task/TaskFormDialog.vue`。

关键实现要点：
- 左「项目信息」卡 + 右「任务列表」表；
- 任务表新增「工作流」列：一次性拉 `GET /workflows?project_id=`，前端按 `task_id` 分组，**不做 N+1 逐任务查询**；
- 任务无删除接口（F5）：只提供「编辑 + 改状态」，UI 不出现删除按钮；
- 项目软删后跳转回 `/projects`。

验收：
- 打开详情页，任务数与任务列表 `total` 一致；
- 某任务启动过工作流后，详情页该行显示「进行中 / 待审批 / 已完成」及轮次；
- 刷新页面工作流状态不丢失（依赖 S5-1 的反查）；
- `npm run type-check` 通过。

### 2.6 S5-4 / P3 任务详情页（`/tasks/:task_id`）

| 动作 | 调用接口 | 状态 |
| --- | --- | --- |
| 任务信息 | `GET /tasks/{id}` | 既有 |
| 文件列表 | `GET /tasks/{id}/artifacts?page&page_size&review_status&stage&keyword` | 既有 |
| 上传文件 | `POST /tasks/{id}/artifacts`（multipart） | 既有 |
| 下载文件 | `GET /artifacts/{id}/download`（响应头 `X-Content-SHA256`） | 既有 |
| 新建版本 | `POST /artifacts/{id}/revisions` | 既有 |
| 文件审核 | `POST /artifacts/{id}/review` | 既有 |
| 启动工作流 | `POST /tasks/{id}/workflow/start` | 既有 |
| 工作流状态 / 日志 / 推进 | `GET /workflows/{id}`、`GET /workflows/{id}/logs`、`POST /workflows/{id}/resume` | 既有 |
| 找回 `workflow_id` | `GET /tasks/{task_id}/workflows` **新增** | 新增（S5-1） |

新增文件：
- `src/views/tasks/TaskDetailView.vue`
- `src/components/artifact/ArtifactTable.vue`、`ArtifactUploadDialog.vue`、`ArtifactPreviewDrawer.vue`、`ArtifactReviewDialog.vue`
- `src/components/workflow/WorkflowStatusCard.vue`、`WorkflowTimeline.vue`、`WorkflowActionBar.vue`

关键实现要点：
- 启动工作流：调用成功返回 `WorkflowRead`（通常已是 `waiting_approval`），直接渲染；返回 **409**（该任务已有活动实例）时读取 `detail.existing_workflow_id` 跳到对应实例，**不弹「失败」**；
- 状态轮询：页面可见时每 4s 拉一次 `GET /workflows/{id}`，`document.hidden` 时暂停；进入 `waiting_approval` 后停止轮询并提示「去审批」；
- **「文件审核」与「工作流审批」是两套独立语义**（F3）：UI 分区呈现，「文件审核」按钮只调 `POST /artifacts/{id}/review`，不驱动图；「通过/驳回」只出现在工作流卡片里；
- 下载用 `blob` 响应，文件名取 `original_filename`；
- 上传时由浏览器自动设置 `Content-Type`（不要在 `headers` 里写死 multipart boundary）。

验收：
- 上传文件后列表出现新行，版本号为 1；提交新版本后旧版本变 `superseded`；
- 下载得到的文件内容与上传一致，页面展示的 SHA256 与响应头 `X-Content-SHA256` 一致；
- 启动工作流后卡片显示轮次 `iteration=1`、当前节点 `human_approval`，产物预览可见；
- 日志时间线按 `sequence` 升序展示 `node_started → artifact_generated → validation_passed → approval_requested`；
- 重复点击「启动工作流」不产生第二个实例（后端 409，前端正确引导）；
- `npm run type-check` 通过。

### 2.7 S5-5 / P4 人工审批页（`/approvals`）

| 动作 | 调用接口 | 状态 |
| --- | --- | --- |
| 待审批列表 | `GET /workflows?status=waiting_approval` **新增** | 新增（S5-1）★ 阻塞项 |
| 审批详情（产物、预览、意见历史） | `GET /workflows/{id}` 的 `pending_approval` + `current_artifact` + `approvals` | 既有 |
| 产物全文 | `GET /artifacts/{current_artifact.id}/download` | 既有 |
| 通过 | `POST /workflows/{id}/resume`（`decision=approved` + `approver`） | 既有 |
| 驳回 | `POST /workflows/{id}/resume`（`decision=rejected` + `approver` + `comment`） | 既有 |
| 幂等提交 | 请求体 `idempotency_key` | 既有 |
| 跨实例审批轨迹 | `GET /projects/{id}/approvals` **新增**（P1） | 新增（可选） |

新增文件：
- `src/views/approvals/ApprovalQueueView.vue`
- `src/components/approval/ApprovalDetailDrawer.vue`、`ApprovalDecisionForm.vue`
- `src/components/artifact/ArtifactMarkdownViewer.vue`（产物预览，Markdown 纯文本渲染，不引第三方渲染库）

关键实现要点：
- **`thread_id` 必须取自 `GET /workflows/{id}` 的响应**，前端绝不自己拼 `wf-...`；不一致会 409；
- `idempotency_key` 每次「打开审批单」时生成一次 UUID 并固定在该单上，重试提交复用同一个 key，避免双写审批记录；
- `approver` 无用户体系（F6）：做成「选择器（最近使用）+ 可选手填」，为后续接真实身份留位；
- 驳回必须填 `comment`，否则按钮禁用（后端虽不强制，但返工语义依赖意见）；
- 通过后该实例离开 `waiting_approval`，从待办列表移除（前端本地移除 + 列表重新拉取）；
- 待办列表轮询 5s；提交成功后立即刷新。

验收：
- 列表只显示 `status=waiting_approval` 的实例，显示项目名、任务名、轮次、等待时长；
- 点击某条能拉到完整详情并下载产物全文；
- 点「通过」后实例变 `completed`，列表中消失；
- 点「驳回」后实例变 `waiting_approval` 且 `iteration` 递增，`approvals` 数组出现一条 `rejected` 记录并带上意见；
- 同一审批单连点两次「通过」，第二次返回 200 且**审批记录不重复**（幂等键生效）；
- 断网/后端 5xx 时错误提示里能看到 `request_id`，便于排查；
- `npm run type-check` 通过。

### 2.8 S5-6 联调与前端验收

- 后端：`python -m pytest -q` 全绿（既有 83 + 新增）；`python -m ruff check .` 零错误；
- 前端：`npm run type-check`、`npm run build` 均通过；
- 端到端手工脚本（写在 `docs/task5_task6_api_inventory.md` 的接口基础上）：
  1. 建项目 → 建任务 → 上传 PRD → 启动工作流 → 待审批 → 通过 → 完成；
  2. 同任务再启动 → 409 引导到既有实例；
  3. 驳回 → 轮次 +1 → 再通过；
  4. 重启后端 → 实例仍可查、仍可审批（任务 4 已保证，本轮只做回归验证）。

---

## 3. 任务 6：GitLab 后端接入

### 3.1 阶段划分与顺序

顺序：**T6-0（配置与凭据） → T6-1（REST 客户端） → T6-2（绑定建模，需确认） → T6-3（API） → T6-4（仓库同步） → T6-5（容器改造） → T6-6（Docker 整栈验证） → T6-7（最小 CI，可选）**

理由：客户端是所有上层能力的地基；绑定建模涉及表结构变更，必须在写任何端点前定案；容器改造必须早于部署验证。

### 3.2 T6-0 配置与凭据

新增环境变量（同步 `.env.example`、`docker-compose.yml`、README 环境变量表）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GITLAB_BASE_URL` | `https://gitlab.com` | GitLab 实例根地址；**唯一允许的出站主机**，用户输入不得覆盖它（防 SSRF） |
| `GITLAB_TOKEN` | 空 | 私有仓库访问令牌，**只进环境变量 / `.env`，不进仓库、不进日志、不进 `.git/config`** |
| `GITLAB_DEFAULT_NAMESPACE` | 空 | 绑定时的默认命名空间（group） |
| `GITLAB_TIMEOUT` | `15` | HTTP 超时（秒） |
| `GITLAB_CLONE_ROOT` | `{STORAGE_ROOT}/repos` | 本地克隆目录根 |
| `GITLAB_CLONE_TIMEOUT` | `300` | clone/pull 超时（秒） |
| `GITLAB_ENABLED` | `false` | 总开关；关闭时 GitLab 端点返回 503，前端隐藏入口 |

实现要点：
- `app/core/config.py` 增加对应字段（走 Pydantic Settings，`extra="ignore"` 保持不变）；
- 新增脱敏属性 `masked_gitlab_token`（只显示前 4 位），日志只打脱敏值；
- 令牌缺失时，GitLab 端点返回 `ServiceUnavailableException`，**不静默成功**。

验收：
- `python -m pytest -q` 全绿；`test_config.py` 增加脱敏断言；
- `.env.example` 中只有占位符，无真实令牌；`git grep -i "glpat-\|private_token"` 无命中。

### 3.3 T6-1 GitLab REST 客户端

新增 `backend/app/services/gitlab.py`（薄客户端 + 领域映射），依赖选择：

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| `httpx` 直调 REST API | 已在测试栈中；`httpx.MockTransport` 可离线单测；无额外传递依赖 | 需自己处理分页与字段映射 | **采用** |
| `python-gitlab` | 现成的项目/分支/文件 API | 引入新依赖与较重对象模型，错误映射不可控 | 备选 |

需把 `httpx>=0.27.0` 从 `dev` extras 提升到主依赖（`pyproject.toml` 的 `dependencies`）。

客户端能力：
- `get_project(repo_path)` → 基础信息（`path_with_namespace`、`default_branch`、`visibility`、`web_url`、`last_activity_at`）；
- `list_projects(namespace, page, per_page, search)` → 分页遍历（跟随 `X-Next-Page`）；
- `list_branches(repo_path)`；
- `get_file(repo_path, file_path, ref)` → 仓库文件内容（用于校验仓库确实可读且非空）。

安全要点（重要）：
- `repo_path` 必须过严格白名单正则 `^[A-Za-z0-9._-]{1,64}(/[A-Za-z0-9._-]{1,64}){1,10}$`，拒绝 `..`、拒绝绝对路径、拒绝 URL；
- 主机固定为配置里的 `GITLAB_BASE_URL`，请求路径由 `repo_path` 拼装，**不接受用户传入的完整 URL**；
- 令牌只放在 `PRIVATE-TOKEN` 请求头，**不出现在 URL、异常消息与日志**；
- 错误映射：404 → `NotFoundException`、401/403 → `ForbiddenException`（新增，语义明确）或 `ServiceUnavailableException`、5xx / 超时 → `ServiceUnavailableException`，统一走 `app/core/exceptions.py` 的信封。

验收：
- 新增 `backend/tests/test_gitlab_client.py`，用 `httpx.MockTransport` 覆盖：正常返回、分页、404、401、超时、令牌脱敏（异常与日志文本中不含令牌字面量）；
- 恶意 `repo_path`（`../../etc`、`http://evil.com/x`、`a..b/c`）全部被拒。

### 3.4 T6-2 项目 ↔ GitLab 仓库绑定建模（**需先确认，见决策点 D-1/D-2**）

| 方案 | 变更 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **A（推荐）** | `projects` 新增 3 列：`gitlab_repo_path VARCHAR(255) NULL`、`gitlab_default_branch VARCHAR(120) NULL`、`gitlab_last_synced_at TIMESTAMPTZ NULL` | 一对一关系够用；`op.add_column` 对 SQLite 安全（不重建表，符合既有迁移风格）；改动面最小 | 一个项目只能绑一个仓库 |
| B | 新建 `gitlab_repositories` 表（`project_id` FK、`repo_path`、`default_branch`、`last_synced_at`、`sync_status`…） | 支持多仓库与同步状态机；扩展性好 | 多一张表 + 迁移更重；当前需求用不上 |

本计划默认按 **方案 A** 规划，迁移脚本 `0005_gitlab_binding.py` 必须同时实现 `upgrade()` 与 `downgrade()`（`drop_column`）。

若确认方案 A：
- `models/project.py` 增加字段 + `models/schemas/project.py` 增加 `GitLabRepoUpdate`；
- 迁移文件按既有 `0004_workflow_engine.py` 风格编写（SQLite 安全、无表重建）；
- **既有项目的 `gitlab_repo_path` 为 NULL**，不影响任何既有接口。

若确认方案 B，则改为新建表，接口契约不变。

### 3.5 T6-3 GitLab API（**新增**）

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| **新增** | `GET /api/v1/gitlab/repositories` | `namespace?`、`search?`、`page`、`page_size` | `Page[GitLabRepositoryRead]`（可绑定的仓库列表，供选择器使用） |
| **新增** | `GET /api/v1/projects/{project_id}/gitlab/repository` | — | `GitLabBindingRead`（绑定状态 + 仓库信息；未绑定时 `bound=false`，不报 404） |
| **新增** | `PUT /api/v1/projects/{project_id}/gitlab/repository` | body `GitLabRepoUpdate`：`repo_path`（必填）、`default_branch?` | `GitLabBindingRead` |
| **新增** | `DELETE /api/v1/projects/{project_id}/gitlab/repository` | — | 204（解绑，不删本地克隆） |
| **新增** | `POST /api/v1/projects/{project_id}/gitlab/repository/validate` | body：`repo_path` | `GitLabValidateRead`：`exists`、`default_branch`、`visibility`、`web_url`、`last_activity_at`、`warnings[]` |
| **新增** | `POST /api/v1/projects/{project_id}/gitlab/repository/sync` | body：`branch?`、`force?` | `GitLabSyncRead`：`synced`、`branch`、`commit`、`files_count`、`duration_ms`、`local_path` |
| **新增**（可选） | `GET /api/v1/projects/{project_id}/gitlab/repository/branches` | — | `list[GitLabBranchRead]` |

实现要点：
- 统一挂 `/api/v1`，在 `app/api/v1/router.py` 新增 `gitlab` 路由注册（新增文件，不改既有注册行）；
- 「校验」不落库（先校验再绑定），「绑定」时再调一次 GitLab 确认存在；
- 绑定后项目详情页 P2 出现「GitLab 仓库」区块（Tab）；
- `sync` 复用 T6-4 的同步服务。

### 3.6 T6-4 仓库同步服务（clone / pull）

实现要点：
- 用 `git` CLI（`asyncio.create_subprocess_exec`，**argv 列表、绝不 `shell=True`**）；
- 克隆参数：`git clone --depth 1 --single-branch --branch <branch> -- <url> <dir>`；
- 认证：**不把令牌写进 remote URL**（避免落进 `.git/config`），改用 `GIT_ASKPASS` + 环境变量 `GIT_TERMINAL_PROMPT=0`，或 `git -c http.extraHeader="PRIVATE-TOKEN: ..."` 的**内存级** header（`-c` 不会写盘）；
- 目录固定为 `{GITLAB_CLONE_ROOT}/{project_id}/{repo_name}`，路径全部用 `resolve_within_root` 校验，杜绝路径穿越；
- 幂等：目标目录已存在且是合法 git 仓库 → 走 `fetch --depth 1` + `reset --hard origin/<branch>`；`force=true` 时先清空重建；
- 失败清理：超时或报错时删除半成品目录，返回结构化错误；
- 体积保护：同步后统计目录大小，超限则报错（防打满磁盘）。

容器影响：后端镜像当前**没有 git**（`python:3.11-slim` 只装了 curl，G4）⇒ T6-5 必须加装。

验收：
- 新增 `backend/tests/test_gitlab_sync.py`：`git` 不存在时报错清晰；路径穿越被拒；用**本地 git 仓库作为远端**（`git init --bare` + `file://` 协议）验证 clone/fetch 幂等，全程不访问外网；
- 连续两次 sync 不产生重复目录、第二次为增量更新；
- 仓库 URL 与 `.git/config` 中**不含令牌**（测试断言文件内容）。

### 3.7 T6-5 容器与部署配置改造

| 文件 | 改动 | 依据 |
| --- | --- | --- |
| `backend/Dockerfile` | `apt-get install -y --no-install-recommends git` + 清理 apt 缓存 | G4：容器内要能 clone |
| `backend/Dockerfile` | 可选：改为多阶段或 `pip install .[dev]` | D2：容器内无 pytest，无法在容器里跑测试 |
| `frontend/Dockerfile` | `npm install` → `npm ci` | D3：构建可复现 |
| `frontend/Dockerfile` | 可选：非 root 运行 | D4：安全基线 |
| `docker-compose.yml` | `backend` 服务注入 `GITLAB_*` 环境变量（`GITLAB_TOKEN` 用 `${GITLAB_TOKEN:-}` 透传，不写死） | 打通配置 |
| `docker-compose.yml` | 可选：挂载 `gitlab_repos` 卷 | 克隆内容需持久化 |
| `.env.example` / `README.md` | 新增环境变量表条目 | 规范要求 |

验收：
- `docker compose config` 无告警、变量可正确注入；
- Dockerfile 的改动在**有 Docker 的机器**上构建成功（见 T6-6）。

### 3.8 T6-6 Docker 整栈部署验证（本机**无法执行**，标「未执行」）

本机没有 `docker` / `docker compose`（D1），因此下列验证**必须在一台有 Docker 的机器或 CI Runner 上执行**，本轮仅提供清单与脚本：

1. `cp .env.example .env`，填 `POSTGRES_PASSWORD` 与 `GITLAB_TOKEN`；
2. `docker compose up --build -d`；
3. `docker compose ps`：`db` healthy、`migrate` 退出码 0、`backend` healthy、`frontend` 正常；
4. `curl http://localhost:8000/api/v1/health` → `status=ok`；`/health/ready` → 数据库 `ok`；
5. `curl http://localhost/health`（前端 nginx）返回页面；`curl http://localhost/api/v1/health` 反代通；
6. 走一遍完整业务：建项目 → 建任务 → 上传 → 启动工作流 → 审批 → 完成；
7. 验证 PG 检查点：`docker compose exec db psql -c "\dt" ai_dev_platform_checkpoints` 能看到检查点表；
8. 重启后端容器（`docker compose restart backend`），实例仍在 `waiting_approval` 且可继续审批（任务 4 的重启恢复在 PG 路径下的复验）；
9. `docker compose logs backend | grep -i token` 无令牌泄漏。

交付：一份 `docs/task6_deployment_verification.md`，记录**实际执行环境、执行时间、每步输出**；未执行就写「未执行」并附复现命令。

### 3.9 T6-7 最小 CI（可选）

- 新增 `.github/workflows/ci.yml`（或 `.gitlab-ci.yml`，二选一）：`ruff check` → `pytest -q` → 前端 `npm ci && npm run type-check`；
- 若 Docker 验证环境可用，再加一个 job 跑 `docker compose up` 冒烟。

---

## 4. 需要新增或修改的 API 汇总

### 4.1 任务 5（后端只增 2～3 个，全部新增）

| 方法 | 路径 | 归属阶段 | 阻塞页面 |
| --- | --- | --- | --- |
| GET | `/api/v1/workflows` | S5-1 | P4（阻塞）、P2 |
| GET | `/api/v1/tasks/{task_id}/workflows` | S5-1 | P3、P2 |
| GET | `/api/v1/projects/{project_id}/approvals` | S5-1（P1，可延后） | P4 的跨实例轨迹 |

**既有端点零改动**：21 个既有端点的路径、请求体、响应体一律不动。

### 4.2 任务 6（全部新增）

| 方法 | 路径 | 阶段 |
| --- | --- | --- |
| GET | `/api/v1/gitlab/repositories` | T6-3 |
| GET | `/api/v1/projects/{project_id}/gitlab/repository` | T6-3 |
| PUT | `/api/v1/projects/{project_id}/gitlab/repository` | T6-3 |
| DELETE | `/api/v1/projects/{project_id}/gitlab/repository` | T6-3 |
| POST | `/api/v1/projects/{project_id}/gitlab/repository/validate` | T6-3 |
| POST | `/api/v1/projects/{project_id}/gitlab/repository/sync` | T6-3 |
| GET | `/api/v1/projects/{project_id}/gitlab/repository/branches` | T6-3（可选） |

---

## 5. 需要新增或修改的数据库模型与迁移

| 迁移 | 内容 | 阶段 | 是否已确认 |
| --- | --- | --- | --- |
| —（无） | 任务 5 全部靠既有 6 张表 | S5-1 | ✅ 无需确认 |
| `0005_gitlab_binding.py` | 方案 A：`projects` 加 `gitlab_repo_path` / `gitlab_default_branch` / `gitlab_last_synced_at`（`op.add_column`，SQLite 安全，含 `downgrade()`） | T6-2 | ❌ **待确认（D-1/D-2）** |
| `0005_gitlab_repositories.py` | 方案 B：新建 `gitlab_repositories` 表 | T6-2 | ❌ 备选 |

约束：
- 迁移必须同时实现 `upgrade()` 与 `downgrade()`；
- 不重建表、不改既有列、不动既有索引；
- 迁移后必须跑一次「全新库 `alembic upgrade head` + 模型 autogenerate 空 diff」的验证。

---

## 6. 需要新增或修改的前端文件汇总

### 6.1 地基

| 文件 | 动作 | 阶段 |
| --- | --- | --- |
| `src/types/index.ts` | 新增 | S5-0 |
| `src/api/projects.ts` `tasks.ts` `artifacts.ts` `workflows.ts` `approvals.ts` `gitlab.ts` | 新增 | S5-0 / T6-3 |
| `src/api/client.ts` | 修改（请求拦截器 + 统一错误提示 + 暴露 request_id） | S5-0 |
| `src/api/index.ts` | 修改（统一导出） | S5-0 |
| `src/utils/format.ts` | 新增 | S5-0 |
| `src/components/common/PageState.vue`、`StatusTag.vue` | 新增 | S5-0 |
| `src/components/layout/AppSidebar.vue` | 修改（路由表驱动） | S5-0 |
| `src/router/index.ts` | 修改（追加 4 条路由） | S5-0 |
| `src/stores/workspace.ts` | 新增 | S5-0 |

### 6.2 业务页面

| 文件 | 动作 | 阶段 |
| --- | --- | --- |
| `src/views/projects/ProjectListView.vue` | 新增 | S5-2 |
| `src/components/project/ProjectFormDialog.vue` | 新增 | S5-2 |
| `src/views/projects/ProjectDetailView.vue` | 新增 | S5-3 |
| `src/components/task/TaskTable.vue`、`TaskFormDialog.vue` | 新增 | S5-3 |
| `src/views/tasks/TaskDetailView.vue` | 新增 | S5-4 |
| `src/components/artifact/ArtifactTable.vue`、`ArtifactUploadDialog.vue`、`ArtifactPreviewDrawer.vue`、`ArtifactReviewDialog.vue` | 新增 | S5-4 |
| `src/components/workflow/WorkflowStatusCard.vue`、`WorkflowTimeline.vue`、`WorkflowActionBar.vue` | 新增 | S5-4 |
| `src/views/approvals/ApprovalQueueView.vue` | 新增 | S5-5 |
| `src/components/approval/ApprovalDetailDrawer.vue`、`ApprovalDecisionForm.vue` | 新增 | S5-5 |
| `src/components/artifact/ArtifactMarkdownViewer.vue` | 新增 | S5-5 |
| `src/components/gitlab/GitLabRepositoryPanel.vue`、`GitLabRepoBindingDialog.vue` | 新增 | T6-3（挂载在 P2） |

---

## 7. 每项功能的验收标准汇总

### 7.1 后端

| 功能 | 验收标准 | 判定方式 |
| --- | --- | --- |
| S5-1 新增列表接口 | `pytest` 全绿；分页/过滤/反查/404 均有用例；**既有 5 个工作流端点的 OpenAPI 定义零变化** | `python -m pytest -q` + OpenAPI 导出 diff |
| GitLab 客户端 | `MockTransport` 覆盖正常/分页/404/401/超时；异常与日志不含令牌字面量 | `python -m pytest -q tests/test_gitlab_client.py` |
| 仓库同步 | 用本地 bare 仓库完成 clone→再 sync 幂等；`.git/config` 不含令牌；路径穿越被拒 | `python -m pytest -q tests/test_gitlab_sync.py` |
| 迁移（若确认） | `upgrade()`/`downgrade()` 均可执行；全新库 upgrade head 成功；autogenerate 无 diff | `python -m alembic upgrade head` + `alembic check` |
| 全部后端代码 | `ruff` 零错误 | `python -m ruff check .` |

### 7.2 前端

| 功能 | 验收标准 |
| --- | --- |
| 地基 | `npm run type-check` 与 `npm run build` 均通过；错误提示含 `request_id` |
| P1 项目列表 | 列表/分页/搜索/状态过滤/新建/编辑/删除全可用；空态与错误态可见 |
| P2 项目详情 | 项目信息 + 任务列表 + 任务增改 + 工作流状态列；刷新后状态不丢 |
| P3 任务详情 | 产物上传/下载/新版本/审核 + 启动工作流 + 状态轮询 + 日志时间线；409 重复启动有引导 |
| P4 人工审批 | 待办列表只含 `waiting_approval`；详情/预览/通过/驳回可用；重复提交不产生重复审批记录；`thread_id` 取自服务端 |
| GitLab 面板（任务 6） | 能选仓库、校验、绑定、查看信息、同步；令牌不出现在前端与网络日志中 |

### 7.3 部署

| 功能 | 验收标准 |
| --- | --- |
| Docker 整栈 | 9 步清单全绿（见 §3.8），**本机未执行**，须在有 Docker 的机器上完成并记录 |
| 配置注入 | `docker compose config` 输出含全部 `GITLAB_*` 变量且无明文硬编码 |

---

## 8. 任务 5 与任务 6 的依赖关系

1. **共享前置（M0）**：两条线都依赖后端「只增接口」与既有契约稳定；S5-1 的两个新端点既是 P4 的前提，也是任务 6 复用分页/序列化规范的模板。
2. **任务 5 内部是串行**：P1 → P2 → P3 → P4（每页都复用前一页建立的表格、表单、三态组件与路由模式）。
3. **任务 6 内部是串行**：T6-0 → T6-1 → T6-2 → T6-3 → T6-4 → T6-5 → T6-6。
4. **任务 5 ← 任务 6**：只有 **GitLab 绑定的 UI 入口**依赖任务 5 的 **P2 项目详情页**（绑定仓库属于项目属性）。因此 **P2 必须早于 GitLab 面板开发**；若要并行，则 P2 需预留一个空的「GitLab 仓库」Tab 占位。
5. **任务 6 → 任务 5 无反向依赖**：P1/P3/P4 不需要任何 GitLab 能力，任务 5 可以在任务 6 完全未开始的情况下独立完成。
6. **任务 6 的部署验证是终点**：T6-6 依赖 T6-5 的镜像改造，且依赖一台有 Docker 的机器；本机无法完成 ⇒ 该里程碑天然落在最后。
7. **可并行的部分**：M0 完成后，「任务 5 的 P1/P2 开发」与「任务 6 的 T6-0～T6-1（配置与客户端）」可同时推进，两者代码互不重叠。

推荐的落地顺序（单人或双人）：

```
S5-1 + S5-0  →  P1  →  P2  →  T6-0~T6-4  →  P3  →  P4  →  T6-5  →  T6-6
```

---

## 9. 需要确认的决策点（等指令，不擅自实施）

| # | 决策点 | 推荐 | 影响 |
| --- | --- | --- | --- |
| D-1 | GitLab 绑定建模：方案 A（`projects` 加列）还是方案 B（独立表） | **A** | 决定迁移 0005 的形态与工作量 |
| D-2 | 是否允许本迭代新增迁移 0005（指令要求不擅自改表结构） | 允许（纯新增列，零影响既有接口） | 不允许则任务 6 只能做「不落库的校验与查询」 |
| D-3 | GitLab 实例是 gitlab.com 还是自建 | 由 `GITLAB_BASE_URL` 配置决定，默认 gitlab.com | 自建需额外网络与证书配置 |
| D-4 | 是否引入最小鉴权（当前 `approver` 全靠请求方自报，B3） | 本迭代不引入，但前端做成「选择器 + 可填」 | 影响审计可信度 |
| D-5 | Docker 整栈验证在哪台机器执行（本机无 Docker） | CI Runner 或一台开发机 | 决定 T6-6 能否在本轮闭环 |
| D-6 | 本迭代是否实现 clone/pull（工作量与凭据处理最重） | 实现，但用本地 bare 仓库做自动化测试 | 不实现则任务 6 只剩「查仓库信息」 |
| D-7 | 容器加固（`npm ci`、非 root、镜像内 pytest）是否纳入 | 纳入 `npm ci` 与 git 安装；其余可选 | 影响镜像体积与可测性 |
| D-8 | 四个页面的划分是否按当前推导（项目列表 / 项目详情 / 任务详情 / 人工审批） | 是 | 若调整，API 需求随之调整 |

---

## 10. 本轮未验证事项

| 事项 | 状态 | 复验方式 |
| --- | --- | --- |
| 后端既有测试全绿 | 上一轮已执行（83 通过） | `cd backend && python -m pytest -q` |
| 前端 `npm run type-check` | 上一轮已执行通过 | `cd frontend && npm run type-check` |
| Docker 整栈部署 | **未执行**（本机无 Docker） | 在有 Docker 的机器上执行 §3.8 的 9 步清单 |
| GitLab 真实 API 调用 | **未执行**（缺 Token 与目标仓库） | 填入 `GITLAB_TOKEN` 后跑 T6-1/T6-3 的手工用例 |
| PG 检查点后端（生产路径） | **未执行**（本机无 PG） | `docker compose up` 后按 §3.8 第 7、8 步复验 |
| 容器内 clone | **未执行** | `docker compose exec backend git --version` + 一次真实 sync |
