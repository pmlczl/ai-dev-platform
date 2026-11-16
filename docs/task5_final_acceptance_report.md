# 任务 5 最终验收报告（M2–M4）

报告日期：2026-11-11
适用版本：`develop` 分支，HEAD = `2af903b`，工作区包含 M1–M4 未提交改动
验收范围：任务 5「前端业务闭环」= M2 项目详情页 + M3 任务详情与工作流监控 + M4 人工审批 + 集成测试
运行环境：本机 Windows + 临时后端（`127.0.0.1:8123`，SQLite + LangGraph 内存检查点）+ Vite 开发服务器（`127.0.0.1:5174`）+ headless Edge 157（CDP 驱动真实页面）

> 本报告只描述已经真实执行过的命令与真实取到的页面数据。未执行的检查一律写在「未验证」或 G 节遗留问题里，并给出复现命令。
> 工作流为**本地模拟实现**：节点由固定模板产出产物，未接入任何 AI 模型；报告与页面文案均不使用「AI 生成」的表述。

---

## A. 功能完成情况

| 编号 | 功能块 | 状态 | 说明与证据 |
| --- | --- | --- | --- |
| M2 | 项目详情页 | 完成 | 基本信息、编辑项目、任务列表（含最新运行状态列）、新建/编辑任务入口、工作流概览、GitLab 仓库占位卡；14 张截图见 `docs/M2_project_detail_report.md` |
| M3 | 任务详情 | 完成 | 基本信息与编辑、需求文档上传（类型/大小前置校验、进度、同名新版本 + 旧版 `superseded`）、下载内容与本地逐字节一致、研发成果列表并标注「模拟成果」、启动工作流与重复启动 409 防护；见 `docs/M3_task_workflow_report.md` |
| M3 | 任务管理（一级导航） | 完成 | `/tasks` 跨项目任务列表可用（关键词 + 状态 + 分页 + URL 状态恢复）。已知限制 M3-2：该页隐藏「工作流」列，因为接口无法一次返回每个任务的最新运行；项目详情页仍显示该列 |
| M3 | 工作流监控 | 完成 | 列表页筛选（项目/任务/状态/分页）+ 4 秒轮询 + 刷新恢复；详情页节点路径、事件日志、轮询与终态自动停止、只读态、404/离线态。本轮补测取到真实节点与事件（见 E.6 的 x2） |
| M3 | 「继续执行」按钮 | 部分完成 | 逻辑按后端契约实现（仅 `paused` 显示、确认框、只回传后端 `thread_id`、防重复提交），恢复执行由后端自动化测试覆盖；但 `paused` 只在后端重启后由检查点产生，本轮未重启临时后端，浏览器路径未验证（见 G-1） |
| M4 | 人工审批队列 | 完成 | `/approvals` 数据来自 `GET /workflows?status=waiting_approval`，9 列（含等待时长）、项目/任务筛选、分页、5 秒自动刷新、刷新失败保留旧行并给出中文告警 |
| M4 | 审批详情与决定 | 完成 | 项目/任务/运行/产物/版本/大小/发起时间/SHA-256 全链路呈现；按类型预览（Markdown 经消毒渲染，PDF 用浏览器查看器，其他仅下载）；通过需意见、驳回强制理由；确认框 + 幂等键；历史只追加 |
| M4 | 审批人身份 | 未完成（受平台范围限制） | 平台没有登录与权限体系，审批人是自报姓名，页面已用告警明确说明「仅作为记录写入审批历史」，不冒充已认证身份（见 G-4） |
| 全局 | 布局与导航 | 完成 | 一级导航为 项目管理 / 任务管理 / 工作流监控 / 人工审批，详情页为二级；Loading / Empty / Error / Success / Forbidden(409 引导) / NotFound 均有专门呈现；网络错误为中文文案并带 `request_id`；1440×900 与 1680×1000 无横向滚动 |
| 全局 | 数据可追溯 | 完成 | 项目 → 任务 → 工作流 → 产物 → 审批记录五级链路逐条核对通过（见 E.6 的 x7 与 E.7） |
| 全局 | 刷新恢复 | 完成 | 每个详情页与列表页都做了 `Page.reload` 复验：路由与筛选状态由 URL 还原，数据全部重新来自后端，Pinia 不作为唯一数据源 |

未做（按任务 5 指令明确排除）：GitLab 真实集成、Docker 部署、真实模型 API、Agent 调度、暂停接口。

---

## B. 文件变更清单

后端在 M2–M4 期间**零改动**（`git status` 中 `backend/` 无变更），任务 5 的改动全部在前端与文档。

### B.1 新增文件

| 文件 | 阶段 | 作用 |
| --- | --- | --- |
| `frontend/src/components/common/PageHeader.vue` | M2 | 详情页统一页头：返回、标题、副标题、状态标签、操作区插槽 |
| `frontend/src/components/project/ProjectTable.vue` | M1 | 项目列表表格（名称/编号、描述、状态、Git、任务数、时间、操作） |
| `frontend/src/components/project/ProjectSearchBar.vue` | M1 | 关键词 300 ms 防抖 + 状态筛选 + 刷新 |
| `frontend/src/components/project/ProjectFormDialog.vue` | M1 | 项目新建/编辑表单与校验 |
| `frontend/src/components/task/TaskTable.vue` | M2 | 任务表格，可选显示「工作流」列（项目详情页用） |
| `frontend/src/components/task/TaskFormDialog.vue` | M2 | 任务新建/编辑表单（名称、描述、状态、优先级、负责人） |
| `frontend/src/components/artifact/ArtifactTable.vue` | M3 | 文件列表：文件名、类型、版本、大小、来源、审核状态、时间、下载 |
| `frontend/src/components/workflow/WorkflowTable.vue` | M3 | 工作流运行列表（ID、项目、任务、类型、状态、轮次、当前节点、时间、操作） |
| `frontend/src/components/workflow/WorkflowNodePath.vue` | M3 | 节点路径图：主链 + 分支节点 + 每节点状态（来自后端运行状态与事件） |
| `frontend/src/components/workflow/WorkflowEventTable.vue` | M3 | 事件日志表（序号、节点、事件、消息、可展开 payload） |
| `frontend/src/components/workflow/WorkflowStartDialog.vue` | M3 | 启动对话框：工作流类型、发起人、模拟流程提示 |
| `frontend/src/components/approval/ApprovalQueueTable.vue` | M4 | 待审批队列表格，含「等待时长」列与产物摘要 |
| `frontend/src/components/approval/ApprovalDecisionDialog.vue` | M4 | 通过/驳回对话框：审批人、意见（驳回理由必填）、二次确认框、幂等键 |
| `frontend/src/components/approval/ArtifactPreview.vue` | M4 | 按类型预览：Markdown/文本消毒渲染、PDF 浏览器查看器、其他仅下载 |
| `frontend/src/utils/markdown.ts` | M4 | Markdown → HTML 的安全渲染（转义、白名单标签、剥离 `javascript:` 与内联事件） |
| `frontend/src/utils/download.ts` | M3 | 通过后端下载接口取 blob 并交给浏览器保存 |
| `frontend/src/stores/reference.ts` | M2 | 项目/任务实体的跨页缓存，仅作为「按 id 取名字」的加速层，每次进页面都重新向后端取 |
| `frontend/src/constants/status.ts` | M1 | 状态/优先级枚举的中文文案与颜色 |
| `frontend/src/constants/artifact.ts` | M3 | 允许扩展名、50 MiB 上限、阶段文案（与后端 `artifact_types.py` 对齐） |
| `frontend/src/constants/workflow.ts` | M3 | 节点标签、事件语义、轮询间隔 4000 ms |
| `frontend/src/constants/approval.ts` | M4 | 审批字段长度、幂等键生成规则、队列轮询间隔 5000 ms |
| `frontend/src/views/tasks/TaskListView.vue` | M3 | 一级导航「任务管理」的跨项目任务列表 |
| `frontend/src/views/workflows/WorkflowDetailView.vue` | M3 | 工作流详情：基本信息、执行节点、本轮产物、审批记录、事件日志、轮询 |
| `frontend/src/views/approvals/ApprovalDetailView.vue` | M4 | 审批详情：审批对象、待审批产物、产物预览、审批历史、提交决定 |
| `docs/M2_project_detail_report.md` | M2 | M2 交付报告（14 张截图） |
| `docs/M3_task_workflow_report.md` | M3 | M3 交付报告（25 张截图） |
| `docs/M4_approval_report.md` | M4 | M4 交付报告（25 张截图） |
| `docs/task5_final_acceptance_report.md` | 任务 5 | 本报告 |
| `docs/task5_manual_acceptance_guide.md` | 任务 5 | 人工验收指南 |
| `docs/images/{M2,M3,M4,task5-integration}/*.png` | 各阶段 | 页面证据：M2 14、M3 25、M4 25、集成 30 张 |

### B.2 修改文件

| 文件 | 阶段 | 改动内容 |
| --- | --- | --- |
| `frontend/src/App.vue` | M1 | 挂载统一布局与侧边导航 |
| `frontend/src/components/layout/AppHeader.vue` | M1 | 顶栏后端健康状态指示（`/health`） |
| `frontend/src/components/common/StatusTag.vue` | M2 | 支持项目/任务/优先级/工作流/审核状态多种标签语义 |
| `frontend/src/router/index.ts` | M2–M4 | 新增项目详情、任务列表/详情、工作流列表/详情、审批队列/详情路由与二级标题 |
| `frontend/src/stores/index.ts` | M2 | 导出 `reference` store |
| `frontend/src/api/client.ts` | M1–M3 | 统一错误提示（中文）、`X-Request-ID` 透出、`silent` 选项、blob 支持 |
| `frontend/src/api/projects.ts` | M1–M2 | 项目分页/详情/新建/编辑/删除、项目任务分页 |
| `frontend/src/api/tasks.ts` | M3 | 任务 CRUD 与任务运行反查 |
| `frontend/src/api/artifacts.ts` | M3 | 文件列表、上传（进度、120 s 超时）、下载、版本、审核 |
| `frontend/src/api/workflows.ts` | M3–M4 | 运行列表/详情/日志、启动、恢复（审批提交） |
| `frontend/src/api/approvals.ts` | M4 | 审批动作命名层：审批即 `POST /workflows/{id}/resume`，避免页面直接依赖传输细节 |
| `frontend/src/utils/format.ts` | M1–M4 | 时间（SQLite/PostgreSQL 统一按 UTC 解析）、大小、`shortId`、`formatElapsedSince`（等待时长） |
| `frontend/src/views/projects/ProjectListView.vue` | M1 | 项目列表页装配 |
| `frontend/src/views/projects/ProjectDetailView.vue` | M2 | 项目详情页：四个卡片 + 编辑 + 新建任务 |
| `frontend/src/views/tasks/TaskDetailView.vue` | M3 | 任务详情：基本信息、PRD 上传/下载、研发成果、工作流运行、启动工作流 |
| `frontend/src/views/workflows/WorkflowListView.vue` | M3 | 工作流监控列表 + 轮询 |
| `frontend/src/views/approvals/ApprovalQueueView.vue` | M4 | 审批队列：筛选、分页、5 秒轮询、告警 |

M4 期间对已交付文件的三处收敛（均在 `docs/M4_approval_report.md` 记录）：审批详情去掉重复的 `GET /artifacts/{id}`（实测由 2 次降为 1 次）；队列「最后更新」列改为「等待时长」；队列增加 5 秒自动刷新。

---

## C. API 清单

### C.1 使用的已有 API（任务 5 未新增任何接口）

| 方法与路径 | 使用页面 | 用途 |
| --- | --- | --- |
| `GET /api/v1/health` | 顶栏 | 后端连通状态 |
| `GET /api/v1/projects` | 项目列表、审批队列筛选 | 分页 + `keyword`/`status` |
| `POST /api/v1/projects` | 项目列表 | 新建项目 |
| `GET /api/v1/projects/{id}` | 项目详情 | 基本信息 |
| `PUT /api/v1/projects/{id}` | 项目详情 | 编辑项目 |
| `DELETE /api/v1/projects/{id}` | 项目列表 | 软删除 |
| `GET /api/v1/projects/{id}/tasks` | 项目详情 | 任务列表（含最新运行状态） |
| `GET /api/v1/tasks` | 任务管理 | 跨项目任务列表 |
| `POST /api/v1/tasks` | 项目详情 | 新建任务 |
| `GET /api/v1/tasks/{id}` | 任务详情 | 基本信息 |
| `PUT /api/v1/tasks/{id}` | 任务详情 | 编辑任务 |
| `GET /api/v1/tasks/{id}/artifacts` | 任务详情 | 文件列表（`stage=design` 取 PRD） |
| `POST /api/v1/tasks/{id}/artifacts` | 任务详情 | 上传需求文档（multipart，进度） |
| `GET /api/v1/artifacts/{id}` | 审批详情 | 产物元数据（大小、SHA-256、审核状态） |
| `GET /api/v1/artifacts/{id}/download` | 任务详情、审批预览 | 文件内容（`X-Content-Sha256`、`Content-Disposition`） |
| `GET /api/v1/workflows` | 工作流监控、审批队列 | 分页 + `project_id`/`task_id`/`status` |
| `GET /api/v1/workflows/{id}` | 工作流详情、审批详情 | 运行状态、当前产物、待审批摘要、审批历史 |
| `GET /api/v1/workflows/{id}/logs` | 工作流详情 | 事件日志 |
| `POST /api/v1/tasks/{id}/workflow/start` | 任务详情 | 启动运行（同步跑到首个审批点，201 + `waiting_approval`） |
| `POST /api/v1/workflows/{id}/resume` | 审批详情 | 提交审批决定（`thread_id`/`decision`/`approver`/`comment`/`idempotency_key`） |

已封装但页面未调用：`GET/POST /artifacts/{id}/revisions`、`POST /artifacts/{id}/review`、`fetchWorkflowApprovals`。其中 `POST /artifacts/{id}/review` 是「文件审核」，与「工作流人工审批」是两条独立流程，任务 5 刻意不混用（否则审批历史与产物审核状态会互相掩盖）。

### C.2 新增 API

任务 5（M2–M4）**没有新增接口，也没有修改任何既有接口契约**。本轮业务闭环依赖的两个接口是在任务 5 之前的准备阶段（提交 `c3acaa2`）新增的，此处一并给出请求/响应实例与对应测试，便于验收核对。

**1）`GET /api/v1/workflows` — 工作流运行分页列表**

请求：

```
GET /api/v1/workflows?status=waiting_approval&page=1&page_size=1
X-Request-ID: 由客户端可选传入，服务端始终回写响应头
```

响应（200，实测数据，`request_id` 见响应头）：

```json
{
  "items": [
    {
      "id": "798e9e90-db16-4856-a95f-5824a94bc176",
      "project_id": "13aa36f1-a9b4-4bae-8270-f7b913147bae",
      "task_id": "aa6ece90-f7bf-4f3f-a257-8fcbb38828b2",
      "workflow_key": "dev_workflow",
      "thread_id": "wf-798e9e90-db16-4856-a95f-5824a94bc176",
      "status": "waiting_approval",
      "current_step": "human_approval",
      "iteration": 1,
      "current_artifact": {
        "id": "e0871552-bc58-49e8-af90-805b81fe2d1d",
        "relative_path": "workflow/798e9e90-…/iteration-1/demo-artifact.md",
        "version": 1,
        "sha256": "1b768c78ca98146395a40d58b9ab7a4f198eb2366a6e4f45873f38a91010ba70",
        "size_bytes": 389,
        "review_status": "pending"
      },
      "pending_approval": {
        "request_id": "798e9e90-db16-4856-a95f-5824a94bc176:1",
        "iteration": 1,
        "artifact_id": "e0871552-bc58-49e8-af90-805b81fe2d1d",
        "artifact_version": 1,
        "preview": "# 模拟研发产物 - 搭建项目骨架\n…",
        "revision_comments": [],
        "requested_at": "2026-11-10T14:55:20.801916Z"
      },
      "approvals": [],
      "started_at": "2026-11-10T14:55:20.020609",
      "finished_at": null,
      "error_message": null,
      "created_at": "2026-11-10T14:55:20",
      "updated_at": "2026-11-10T14:55:21"
    }
  ],
  "total": 1, "page": 1, "page_size": 1, "pages": 1
}
```

错误示例（非法状态值，422）：`{"code":"VALIDATION_ERROR","message":"…","detail":…,"request_id":"…","timestamp":"…"}`。

**2）`GET /api/v1/tasks/{task_id}/workflows` — 按任务反查运行**

请求：

```
GET /api/v1/tasks/9e6c6c6f-dbab-45ca-97c1-e16540f13bfe/workflows?page=1&page_size=1
```

响应（200，实测；`x-request-id: 05dd721695194100aca470cd472a750c`）：`items[0]` 为
`{"id":"8e86e538-2bfb-4e64-aa0c-8dc5c9dcbf49","task_id":"9e6c6c6f-…","status":"completed","current_step":"complete_workflow","iteration":1,…}`，`total=1`、`pages=1`。任务详情页用它判断「是否已有进行中的运行」，从而禁用启动按钮并给出跳转链接。

**对应测试**：`backend/tests/test_workflow_listing.py`（10 个用例）——列表返回、按时间倒序、分页、按状态/项目/任务筛选、组合筛选、非法状态被拒、任务反查、任务反查分页等。

---

## D. 数据库变更

| 项目 | 结论 |
| --- | --- |
| 是否新增迁移 | 否。M2–M4 未新增 `backend/alembic/versions/` 脚本，`alembic_version` 仍为任务 4 的 `0004` |
| 是否新增字段或表 | 否。`projects` / `development_tasks` / `workflow_instances` / `workflow_events` / `artifacts` / `approval_records` 结构未变 |
| 是否影响现有数据 | 代码层面没有破坏性变更。验收在**本机临时 SQLite 库**（`%TEMP%\m1run\app.db`）累积了演示数据：两轮集成通过后的最终数量为 20 个项目、17 个任务、13 次运行、27 个产物文件、16 条审批记录、96 条事件；其中任务 5 集成验收新建 1 个项目（`INT493415`）+ 3 个任务 + 3 次运行（`8e86e538` / `01e74b9e` / `61f427a1`，均 `completed`）+ 8 个产物 + 4 条审批记录，全部为脚本新建，未修改 M1–M4 既有验收数据 |
| 特意保留的数据 | 运行 `798e9e90-db16-4856-a95f-5824a94bc176` 保持 `waiting_approval`、第 1 轮、0 条审批记录，作为人工验收靶子；集成测试全程按项目筛选审批队列，未误提交它的决定（实测见 E.6 的 f2 / x7） |
| 如何回滚 | 前端改动直接丢弃工作区即可（`git checkout -- frontend` + 删除未跟踪文件），无数据库副作用。数据库回滚：`cd backend; python -m alembic downgrade -1`（逐级回退 `0004 → 0003 → 0002 → 0001`），每个迁移脚本都实现了 `upgrade()` 与 `downgrade()` |
| 时间戳口径 | SQLite 返回不带偏移的 naive 串、PostgreSQL 返回 `+00:00`；前端 `parseDateTime()` 统一按 UTC 解析，两种数据库显示同一个本地时间（`utils/format.ts`） |

---

## E. 自动化测试结果

以下命令全部在最终代码上真实执行（2026-11-11）。

### E.1 后端 Lint

```
$ cd backend
$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
（ruff 0.17.3，退出码 0）
```

### E.2 后端测试

```
$ cd backend
$ .venv/Scripts/python.exe -m pytest -q
95 passed, 1 warning in 25.21s
（退出码 0；唯一的 warning 是 langgraph.checkpoint 的既有 DeprecationWarning）
```

原有测试全部保留，任务 5 未删除或跳过任何用例。

### E.3 前端类型检查

```
$ cd frontend
$ npm run type-check
> vue-tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json
（无输出，退出码 0）
```

### E.4 前端构建

```
$ cd frontend
$ npm run build
✓ built in 9.60s
dist/assets/index-BBI4j8cg.js  1,280.96 kB │ gzip: 414.96 kB
（仅 Vite 既有的主包 >500 kB 提示，非错误；退出码 0）
```

项目未配置 ESLint/Prettier 脚本（`package.json` 的 scripts 只有 dev/build/preview/type-check），因此没有额外的 Lint 命令可执行；静态检查由 `type-check`（`strict: true` + `noUnusedLocals`）承担。未关闭任何 TypeScript 规则，也未删除既有规则。

### E.5 纯函数检查（Node 直接 import 前端源码，无浏览器、无 Mock）

```
$ node --experimental-strip-types C:/Users/wansh/AppData/Local/Temp/m1run/m4markdown.mjs
PASS escapeHtml / PASS headings / PASS list / PASS table / PASS link-whitelist /
PASS strip-javascript-uri / PASS plain-text / PASS escape
8/8 通过（退出码 0）

$ node --experimental-strip-types C:/Users/wansh/AppData/Local/Temp/m1run/m4format.mjs
{"summary": "12/12 通过", …}（退出码 0）
```

两个脚本分别 `import` `frontend/src/utils/markdown.ts` 与 `frontend/src/utils/format.ts`：Markdown 用例覆盖转义、`<script>`、`javascript:` 链接、内联 `onclick`、标题/列表/表格渲染；格式用例覆盖 `formatElapsedSince` 的全部分支（不足 1 分钟 / N 分钟 / N 小时 / N 小时 M 分 / N 天 / 整点不显示「0 分」），并用一条真实队列数据做对照。

> 这两个脚本目前只在临时目录，未纳入仓库。任务 6 若要把它们变成常驻回归，建议放到 `frontend/tools/` 并在 `package.json` 里加 `node --experimental-strip-types` 脚本入口。

### E.6 浏览器端功能验收（CDP 驱动真实页面）

驱动脚本放在临时目录（`%TEMP%\m1run\`），结果 JSON 同目录，截图入库到 `docs/images/`。

| 轮次 | 脚本 | 步骤数 | 结果 | 截图 |
| --- | --- | --- | --- | --- |
| M1 项目列表 | `m1shots.mjs` / `m1nav.mjs` / `m1debounce.mjs` | 18 项 | 全通过 | 18 |
| M2 项目详情 | `m2shots.mjs` | 22 项 | 全通过 | 14 |
| M3 任务 + 监控 | `m3shots.mjs`（+`m3download.mjs`、`m3check.mjs`） | 39 项 | 全通过 | 25 |
| M4 审批（主轮） | `m4shots.mjs` | 25 项 | 全通过 | 25 |
| M4 审批（队列补充） | `m4queue.mjs` | 8 项 | 全通过 | — |
| M4 审批（连点） | `m4double.mjs` | 5 项 | 全通过 | — |
| 任务 5 集成主轮 | `t5integration.mjs` | 38 项 | 全通过 | 30 |
| 任务 5 集成补充轮 | `t5extra.mjs` | 14 项 | 全通过 | （同上目录） |

两轮集成测试的 `Runtime.consoleAPICalled` 中 `error` 0 条、`warning` 0 条，`Runtime.exceptionThrown` 0 条。

集成主轮关键实测数据：

| 步骤 | 实测结果 |
| --- | --- |
| a1 项目创建 | 仅 `POST /projects` 1 次；提示「项目已创建」；后端回读 `code=INT493415`、`owner=集成验收-张三` |
| a2/a3 详情与刷新 | 四张卡片（基本信息/任务列表/工作流概览/GitLab 仓库）；刷新后 URL 不变、数据全部由 3 个 GET 重新取回 |
| a4–a6 任务 | 两个任务 `seq=1/2`；编辑后标题与负责人在页面与后端一致，刷新后仍在 |
| b1/b2 PRD | v1 259 B → 再传同名 → v2，v1 变 `superseded`；`file_type=text/markdown`、`stage=design` |
| b3 下载 | 页面只发 `GET /artifacts/{id}/download`；`X-Content-Sha256` = 后端 sha = 本地 sha，`bytesMatch=true` |
| b4 启动（连点两次） | `POST …/workflow/start` 仅 1 次，跳转到新运行 `8e86e538` |
| b5 轮询 | 9 秒内详情 2 次 + 日志 2 次（4 秒间隔），状态「待审批」 |
| b6 刷新恢复 | URL id == 后端 id；`status=waiting_approval`、`iteration=1`、`thread_id=wf-8e86e538-…` |
| e3 重复启动 | 接口 409「该任务已有进行中的工作流」+ `existing_workflow_id`；页面按钮禁用并给出「查看该运行」 |
| c1 队列 | 9 列表头正确；本项目 1 行；`共 1 项等待决定`；`每 5 秒自动刷新 · 更新于 …` |
| c2 详情 | 审批对象/待审批产物/产物预览/审批历史/提交决定五卡；预览标题树 H1+3×H2；不安全节点 0 |
| c3/c4 通过（连点确认提交） | `POST /resume` 仅 1 次，幂等键 `web-8e86e538-…:1:approved`；后端 `completed` / `complete_workflow`；历史 1 行；卡片消失并显示「已完成 · 本页只读」 |
| d1–d5 驳回 | 无理由驳回：表单报错「驳回必须填写理由，下一轮生成依赖这段说明。」且 0 次 POST；带理由驳回后 `iteration=2`、新 `request_id …:2`、`revision_comments` 含该理由、产物路径切到 `iteration-2/`；二轮通过后历史 2 行（`1 rejected`、`2 approved`），任务状态 `completed` |
| e4 四个 404 | 项目/任务/工作流/审批详情均显示后端 message + `request_id` + 返回入口 |
| e5/e6 断网 | 「网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」+ 重试；重试后恢复 |
| e7/e8 后端 500 | 「请求失败：服务器内部错误，请联系管理员（验收脚本构造）（request_id: simulated-500-by-script）」；重试后正常加载 |
| e9 过期页面重复审批 | 接口 409「工作流已结束，无法继续」+ `request_id`；页面为只读并提示「该运行当前为「已完成」，不在待审批状态，不能提交审批决定。」 |
| f1/f2 一致性 | 2 次运行的任务/项目归属、`thread_id=wf-{运行 id}`、产物 sha 全部一致；队列 `total=1` 且不含集成项目运行；保留靶子仍 `waiting_approval`、0 条审批 |
| f3/f4/f5 布局 | 1440×900 与 1680×1000 下 `docScrollWidth == clientWidth`、主区 `scrollWidth == clientWidth`，无横向滚动；面包屑与一级菜单高亮正确 |

补充轮（`t5extra.mjs`）关键实测数据：

| 步骤 | 实测结果 |
| --- | --- |
| x1 任务列表 | 表头含「工作流」列，三行分别显示 待审批 / 已完成 / 已完成；工作流概览 3 行 |
| x2 节点与事件 | 5 个节点（加载任务/生成模拟产物/校验产物/人工审批/完成）全部「已完成」；6 条事件；页面状态「已完成」== 后端 `completed`；本轮产物带「模拟成果」标记 |
| x3a–x3d | 任务三先传 PRD（sha 与本地一致）再启动；成果列表同时出现 `design` 上传件与 `development` 运行件（`workflow_instance_id` 非空），页面有「模拟成果」说明告警 |
| x4a/x4b 下载失败 | 下载接口 500 时提示「请求失败：服务返回了异常状态 500」，页面不崩、按钮回到可用；解除后重试成功，内容与本地 sha 一致 |
| x5 上传失败 | 上传接口 500 时提示后端 message + `request_id`；库里没有产生多余版本（仍 2 个 design 版本），上传按钮恢复可用 |
| x6a–x6c 队列更新 | 审批前队列 2 项（含任务三与保留靶子）→ 通过后队列自动刷新为 1 项，任务三的运行已消失、保留靶子仍在 |
| x7 五级链路核对 | 4 次运行的 `taskOfProject` / `projectExists` / `threadIsWfPrefix` / `artifactsBelongToTaskAndProject` / `approvalSequencesContiguous` 全为 true；驳回轮产物保持 `rejected`、通过轮为 `approved`，历史记录未被覆盖 |

### E.7 数据一致性专项结论

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 任务必须关联正确项目 | 通过 | `x7.taskOfProject`、`f1` 的任务归属；项目详情任务列表只含本项目 3 个任务 |
| 工作流必须关联正确任务 | 通过 | `f1.runs[].taskBelongs`、`x7`；详情页「所属任务」与后端 `task_id` 一致 |
| 成果文件必须关联正确任务或工作流 | 通过 | 上传件 `workflow_instance_id=null` + `task_id`；运行件带 `workflow_instance_id` 且 `task_id`/`project_id` 同源（`x3d`、`x7`） |
| 审批记录必须关联正确工作流和成果 | 通过（口径说明见下） | `approval_records` 以 `target_type='workflow_instance'` + `target_id=运行 id` 关联运行，并带 `project_id`；本轮成果由运行的 `pending_approval.artifact_id` / `current_artifact` 指明，审批记录的 `idempotency_key` 形如 `client:web-{运行 id}:{轮次}:{决定}`，逐条与页面一致 |
| 审批后待审批列表正确更新 | 通过 | `x6a→x6c`：2 项 → 1 项；`f1.queueHasNoIntegrationRun=true` |
| 历史审批记录不能被覆盖 | 通过 | 驳回 + 二轮通过的历史为 `1 rejected` + `2 approved` 两行；`sequence` 连续且唯一（DB 层 `uq_approval_records_target_sequence`）；同幂等键重放返回 200 且不新增记录（M4 主轮步骤 15/16） |
| 页面状态与后端一致 | 通过 | `x2.pageStatus/backendStatus`、`b6`、`c4`、`d5`、`e9` 均逐项比对 |

---

## F. 人工验收说明

见 [docs/task5_manual_acceptance_guide.md](./task5_manual_acceptance_guide.md)。指南共 15 章：

| 章 | 内容 |
| --- | --- |
| 0–1 | 使用方式、统一判定口径（通过 / 缺陷 / 已知项三态）、验收目标与范围边界 |
| 2 | 环境准备：依赖自检、`python -m alembic upgrade head` + `python -m uvicorn`、前端 `npm run dev`、SQLite 免装 PostgreSQL 的跑法、关键环境变量表、四项冒烟检查 |
| 3 | 测试数据准备：方案 A 全新库手工造数（含项目/任务字段建议值与 `prd.md`/`bad.exe`/`big.md` 三份异常样本的生成命令）；方案 B 直接复用验收环境靶子数据（保留运行 `798e9e90`、待审产物 `e0871552`、队列当前 1 项等实测值） |
| 4–11 | 八个场景逐步操作表：M2 项目（流程 A）、M3 任务与 PRD（流程 B 前半）、M3 启动与监控（流程 B 后半）、M4 一轮通过（流程 C）、M4 驳回二轮（流程 D）、异常与防护（流程 E，14 条）、布局与刷新（1440×900 / 1680×1000）、数据一致性抽查（7 项接口检查 + 5 条 SQL 及本指南编写时的实测结果） |
| 12 | 人工步骤 ↔ 自动化步骤编号 ↔ 30 张截图的对照表 |
| 13 | 「不要按缺陷上报」的 9 个已知项，逐条映射到本报告 G 章 |
| 14–15 | 验收记录表（含四条回归命令与预期输出）、缺陷提交模板 |

每一步都写明了预期结果与失败判定标准，人工验收无需读代码即可执行；异常场景（500、断网）给出了浏览器 DevTools 层面的可复现手法。

---

## G. 遗留问题

| 编号 | 说明 | 类别 | 影响 | 建议 |
| --- | --- | --- | --- | --- |
| G-1 | `paused` → 「继续执行」按钮的浏览器路径未验证 | 未验证功能 | 逻辑与后端契约已实现，恢复执行有后端测试覆盖，但页面按钮未真实点击过 | 重启后端使存在 `paused` 运行后打开 `/workflows/{id}`；或 `python -m pytest backend/tests -q -k resume` |
| G-2 | 工作流仍为本地模拟实现 | 模拟实现 | 产物由固定模板生成，节点不调用任何模型 | 任务 6 接真实模型时保留「模拟/真实」标识口径，避免文案误导 |
| G-3 | 后端没有「暂停」接口 | 未完成功能 | 页面不提供暂停按钮，只能等终态或重启后恢复 | 任务 6 评估新增 `POST /workflows/{id}/pause`（新接口 + 测试，不改既有契约） |
| G-4 | 平台没有登录与权限校验 | 需要真实身份认证 | 审批人是自报姓名，任何打开页面的人都能提交决定；页面已用告警说明，但无法阻止误操作 | 任务 6 引入认证后：审批人取自会话、按钮按权限禁用、审批记录写入真实用户 id |
| G-5 | 下载接口返回非 2xx 时提示为「服务返回了异常状态 500」 | 技术债 | 下载走 `responseType: 'blob'`，拦截器拿不到后端 JSON 错误体，因此不显示后端 message 与 `request_id`（普通请求能显示） | 在 `api/client.ts` 中对 blob 错误体先 `text()` 再 `JSON.parse`，复用统一错误文案；改动需补一条前端用例 |
| G-6 | 队列加载失败时标题仍显示「共 0 项等待决定」 | 技术债 | 与错误态并存略显突兀（数据确实没取到，非错误数字） | 错误态下隐藏计数或改为「—」；一行模板改动 |
| G-7 | 跨项目任务列表没有「工作流」列 | 技术债（M3-2） | 该页无法一眼看到每个任务的最新运行状态 | 任务 6 评估为 `TaskRead` 增加可选 `latest_workflow_status`（向后兼容 + 测试） |
| G-8 | 事件日志先取尽再前端分页 | 技术债（M3-5） | 当前每轮 6 条事件，无压力；多轮驳回后仍偏小 | 事件量增大时改后端分页 + 增量拉取 |
| G-9 | 时间戳时区口径依赖前端统一解析 | 需要真实 PostgreSQL 验证 | SQLite naive 串按 UTC 解析；若后端改为本地时区写入会再次偏差 | 在 PostgreSQL 环境复验；或后端统一返回带 `+00:00` 的 ISO 串 |
| G-10 | 仅在 SQLite 上验证 | 需要真实 PostgreSQL 验证 | 未验证 PostgreSQL 的约束行为（如 `RESTRICT` 外键、`uuid` 类型、并发审批）与分页排序稳定性 | 任务 6 用 `docker compose up` + PostgreSQL 跑一遍 `pytest` 与集成流程 B/C/D |
| G-11 | 未在 Docker 环境验证 | 需要 Docker 环境验证 | 本轮全部为本机进程（uvicorn + Vite）；容器网络、环境变量注入、健康检查编排未走通 | 任务 6 验证 `docker-compose.yml`：后端 `/api/v1/health`、前端反代、迁移自动执行 |
| G-12 | GitLab 仓库卡片为占位实现 | 未完成功能 | 只显示项目是否配置仓库地址，不做真实拉取 | 任务 6 按需求实现，凭据 `GITLAB_TOKEN` 只从环境变量/`.env` 读取，日志脱敏 |
| G-13 | PDF/其他类型预览分支未在浏览器验证 | 未验证功能 | Markdown 分支已逐字节与消毒验证；PDF 查看器与「其他仅下载」分支只有代码路径 | 上传一个真实 PDF 与一个 `.zip`，打开审批详情观察预览 |
| G-14 | 队列超过一页的场景未验证 | 未验证功能 | 队列分页组件存在，但本轮最多 2 项待审批 | 构造 >20 条 `waiting_approval` 运行后翻页（可脚本批量启动） |
| G-15 | 审批详情页不做轮询 | 设计取舍 | 他人已在别处提交决定时，本页要到下一次操作才反映；已用 409 + 状态提示兜住（M4 主轮步骤 15/16） | 若需要实时，可加与队列一致的 5 秒轮询，并在状态变化时提示「本页已过期」 |
| G-16 | 验收数据留在本机临时库 | 技术债 | `%TEMP%\m1run\app.db` 累积 20 项目 / 12 运行等演示数据，仅影响本机 | 无需处理；人工验收指南第 2 节给出干净环境的初始化命令 |
| G-17 | 构建产物主包 >500 kB | 技术债 | Vite 提示未拆分（Element Plus 全量引入） | 任务 6 评估按需引入组件或 `manualChunks` |
| G-18 | M1–M4 改动尚未提交 | 流程 | HEAD 仍是 M0 的 `2af903b`。工作区未提交内容：前端 16 个修改文件 + 24 个新增文件（组件 14：审批 3、产物 1、PageHeader 1、项目 3、任务 2、工作流 4；`constants/` 4；`stores/reference.ts`；`utils/download.ts`、`utils/markdown.ts`；页面 3：`ApprovalDetailView`、`TaskListView`、`WorkflowDetailView`），另有 6 份文档（M1/M2/M3/M4 报告、本报告、人工验收指南）与 `docs/images/` 下全部截图 | 人工验收通过后按阶段拆分提交（M1 / M2 / M3 / M4 / 集成与文档），提交前跑 E.1–E.4 |

---

## 结论

1. **任务 5 是否全部完成**：是。M2、M3、M4 三个阶段的页面与业务闭环全部落地，5 份交付文档齐备（M2/M3/M4 报告 + 本报告 + 人工验收指南）。
2. **是否满足全部验收标准**：功能与数据口径满足；「审批人身份」一项受平台尚无认证体系的限制，按指令以自报姓名 + 明确告警实现，已列入 G-4。
3. **主要页面与业务闭环是否正常**：正常。项目 → 任务 → PRD → 启动 → 监控 → 审批（通过/驳回二轮）→ 终态的五级链路在真实页面上跑通两轮（主轮 38 步 + 补充轮 14 步），刷新恢复、轮询、异常态与重复提交防护均按预期。
4. **自动化测试是否通过**：通过。`ruff` All checks passed!、`pytest` 95 passed、`type-check` 退出码 0、`build` 成功（9.60 s），浏览器端两轮集成 0 控制台错误。
5. **仍需人工验证的项目**：见 F 节指南与 G 节中标注「未验证」的条目（G-1、G-13、G-14），以及需要 PostgreSQL（G-9、G-10）与 Docker（G-11）环境的检查。
6. **遗留问题**：G 节 18 条 —— 3 条本轮未验证（G-1、G-13、G-14）、4 条需要真实环境（G-4 认证、G-9/G-10 PostgreSQL、G-11 Docker）、6 条技术债（G-5、G-6、G-7、G-8、G-16、G-17）、2 条未完成功能（G-3 暂停接口、G-12 GitLab 占位）、G-2 模拟实现、G-15 设计取舍、G-18 改动未提交。
7. **对任务 6 的建议**：优先补认证与审批人来源（G-4）→ 暂停接口与队列实时性（G-3、G-15）→ PostgreSQL/Docker 环境回归（G-10、G-11）→ 列表最新运行状态与事件分页（G-7、G-8）→ 前端错误体与包体优化（G-5、G-17）。

按指令，任务 5 到此停止：不进入任务 6，不做 GitLab、Docker、模型 API 与 Agent 调度，等待人工验收与下一步指令。
