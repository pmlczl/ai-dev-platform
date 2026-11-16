# M3 —— 任务详情页 + 工作流监控 交付报告

> 日期：2026-11-11
> 范围：任务 5 的 M3 阶段——`/tasks/:task_id` 任务详情页（基本信息与编辑、需求文档上传/版本/下载、研发成果列表、启动工作流）、`/workflows` 工作流监控列表、`/workflows/:workflow_id` 工作流详情（节点、事件、轮询、恢复执行），以及新增的一级导航「任务管理」`/tasks`。
> 前置：M0（类型 / API 封装 / 公共组件 / 路由）、M1（项目列表）、M2（项目详情）已完成；M1–M3 改动均未提交。

## 0. 开发前检查结论

- 已通读 `docs/task5_task6_api_inventory.md`、`docs/task5_task6_implementation_plan.md`、`docs/M0_development_report.md`、`docs/M1_project_management_report.md`、`docs/M2_project_detail_report.md`，并逐一核对 `backend/app/api/v1/endpoints/*.py` 的真实路由、`app/schemas/*.py` 的字段约束与 `app/services/*.py` 的行为。
- M3 所需数据全部有既有接口可用，**本阶段未新增任何后端接口，未新增数据库迁移，未改动既有 API 契约，未改动 LangGraph 核心图**。
- 核对后确认的三条后端事实，直接决定了页面设计：
  1. `thread_id` 只由后端生成并写入 `WorkflowRead.thread_id`（形如 `wf-{workflow_id}`）。前端一律使用后端返回值，恢复执行时原样回传，绝不自行拼接。
  2. 重复启动时后端返回 409，`detail.existing_workflow_id` 给出已在进行的运行 id；任务状态为 `completed` / `cancelled` 时同样返回 409，但**不带** `existing_workflow_id`（`app/services/workflows.py:237-245`）。页面据此分两种文案处理。
  3. 后端**没有暂停接口**：`paused` 只在服务重启后由检查点恢复时出现，`POST /workflows/{id}/resume` 不带 `decision` 即为「继续执行」。因此页面没有「暂停」按钮，「继续执行」仅在 `status === 'paused'` 时出现。
- 事件日志并非每个节点都写 `node_started`（一轮运行实录 4 条：`load_task/node_started`、`generate_demo_artifact/artifact_generated`、`validate_artifact/validation_passed`、`human_approval/approval_requested`）。节点完成状态因此按「`WorkflowRead.current_step` + 日志中出现过的 step + 终态」推导，不臆造未发生的节点。
- 既有工作流为 LangGraph **模拟**流程，产物由固定模板生成。页面上的类型标签写作「研发工作流（模拟）」，产物来源列写作「模拟成果」，启动对话框与研发成果卡片各有一条说明文案，明确不调用任何 AI 模型。

## 1. 功能清单

### 1.1 任务详情页 `/tasks/:task_id`

| 需求 | 实现 | 状态 |
| --- | --- | --- |
| A. 基本信息展示与编辑，字段严格对应 schema | `el-descriptions`（序号 / 名称 / 所属项目 / 状态 / 优先级 / 负责人 / 创建 / 更新 / 任务 ID / 描述）；「编辑任务」复用 M2 的 `TaskFormDialog`，提交 `PUT /tasks/{id}`，字段仅 `TaskUpdate` 中的 title / description / status / priority / assignee | 完成 |
| B. 需求文档上传（进度、类型与大小限制与后端一致） | 隐藏 `<input type=file>` + `uploadArtifact(..., onProgress)` + `el-progress`；类型白名单 `pdf docx md markdown txt json yaml yml`、上限 50 MiB 与后端 `artifact_types.py` / `MAX_UPLOAD_SIZE` 对齐，前端先校验、不合法不发请求 | 完成 |
| B. 列表展示名称 / 大小 / 上传时间 / 版本 | `ArtifactTable`（文件名 + tooltip 完整相对路径、类型、版本 `vN`、大小、审核状态、上传时间、下载）；PRD 区数据源为 `GET /tasks/{id}/artifacts?stage=design` | 完成 |
| B. 下载只走后端接口，不拼路径 | 仅 `GET /artifacts/{id}/download`，响应 Blob 交给浏览器保存，文件名取 `Content-Disposition`，缺失时回落到元数据；前端不构造任何存储路径 | 完成 |
| B. 不覆盖旧版本 | 同名上传由后端生成新版本并把旧版标记 `superseded`；页面展示全部版本（新版在前），无覆盖逻辑 | 完成 |
| C. 研发成果列表，关联当前任务 | `GET /tasks/{id}/artifacts`（阶段筛选 + 分页），列含阶段与来源；`workflow_instance_id` 非空 → 「模拟成果」，否则「人工上传」 | 完成 |
| D. 启动工作流，使用后端返回的 workflow_id / thread_id | `WorkflowStartDialog`（类型 / 发起人）→ `POST /tasks/{id}/workflow/start` → 用响应体的 `id` 跳转 `/workflows/{id}`；发起人输入上限 120 与后端 `max_length` 一致 | 完成 |
| D. 查看该任务的工作流列表 / 详情 | 「工作流运行」卡片 `GET /tasks/{id}/workflows?page_size=20`，`WorkflowTable` 的「详情」跳 `/workflows/{id}`；「前往工作流监控」带 `?task_id=` | 完成 |
| D. 运行中 / 待审批时不得重复启动 | 有存活运行时按钮禁用 + 警告条（含运行短 id 与「查看该运行」）；后端 409 时读取 `detail.existing_workflow_id` 弹确认框「前往查看 / 留在本页」；任务已结束时按钮禁用 + 说明「任务已结束（已完成或已取消），不能再启动工作流。」 | 完成 |
| 任务不存在 / 接口失败 | 404 → 「该任务不存在或已被删除。」+「返回项目列表」/「重试」；其他错误显示后端中文 message 与 `request_id` | 完成 |

### 1.2 工作流监控 `/workflows` 与详情 `/workflows/:workflow_id`

| 需求 | 实现 | 状态 |
| --- | --- | --- |
| 列表分页 + 按项目 / 任务 / 状态筛选 | `GET /workflows`，筛选与分页写入 URL；任务下拉随项目联动，URL 里的 `task_id` 即使不在候选中也会解析出名称 | 完成 |
| 列：ID / 项目 / 任务 / 类型 / 状态 / 创建 / 开始 / 结束 / 详情 | 另附轮次与当前节点；项目与任务名称经 `useReferenceStore` 解析（每个 id 只查一次） | 完成 |
| 详情：ID / 项目 / 任务 / 类型 / 状态 / 当前阶段 / 开始 / 最后更新 / 结束 / 错误 | `el-descriptions`，当前节点显示中文标签 + 后端原始值；`error_message` 非空时单独告警 | 完成 |
| 节点与真实图一致 | `START → 加载任务 → 生成模拟产物 → 校验产物 → 人工审批 → 完成`，分支节点（`handle_revision_comments` / `recover`）仅在本次运行日志出现过时单独列出 | 完成 |
| 节点样式仅由后端数据驱动 | `completed` / `current` / `waiting`（待审批）/ `pending` / `failed` 五态，输入只有 `status`、`current_step`、事件日志 | 完成 |
| 事件列表按时间先后 + 分页 | `GET /workflows/{id}/logs`（后端按 `sequence` 升序）；先取满整段日志（每页 100，翻页取尽）再前端分页 20 条/页，行可展开查看 payload JSON，错误事件标红 | 完成 |
| 运行中 / 待审批轮询 3–5 秒 | 4 秒（`WORKFLOW_POLL_INTERVAL_MS`），详情与日志并行请求；`setTimeout` 链式调度，请求未回来不排下一次，不叠加 | 完成 |
| 离开页面 / 终态停止轮询 | 路由离开与 `onUnmounted` 清理定时器；状态进入终态即停止（终态后 9 秒实测 0 个请求） | 完成 |
| 轮询失败处理 | 失败只在页头下方告警「自动刷新失败，页面可能不是最新：…」，保留已有数据与轮询；恢复后告警消失 | 完成 |
| 刷新恢复 | 列表筛选、详情页均按 URL 重新加载全部数据（Pinia 只作上下文缓存） | 完成 |
| 恢复执行 | `status === 'paused'` 时出现「继续执行」，确认框后 `POST /workflows/{id}/resume` 仅带后端 `thread_id`；按钮 loading 期间禁止二次提交 | 已实现，UI 路径未验证（见 7.4） |
| 暂停 | 后端无暂停接口，页面不提供暂停按钮 | 按后端能力 |
| 待审批不得显示成普通运行或错误 | 状态标签「待审批」（warning 色）、告警「该运行正在等待人工审批，审批通过或驳回后才会继续。」、节点「人工审批 / 等待审批」高亮、页头「前往审批」入口 | 完成 |
| 产物与审批可追溯 | 「本轮产物」卡片（文件 / 版本 / 大小 / 审核状态 / SHA-256 / 审批请求 id / 发起时间 / 历史修改意见条数）+ 下载；有审批记录时展示「审批记录」表（序号 / 结果 / 审批人 / 意见 / 时间） | 完成 |

### 1.3 布局与导航

一级导航为 项目管理 / 任务管理 / 工作流监控 / 人工审批（+ 首页、工作台）；详情页二级、`activeMenu` 与菜单高亮一致，面包屑「首页 / 一级菜单 / 当前页」。任务详情的工作流区、监控列表与项目概览共用 `WorkflowTable`；任务列表与项目详情共用 `TaskTable`。Loading / Empty / Error / Success 四态由 `PageState` 与 `ElMessage` 统一呈现；网络错误文案为中文；错误显示 `request_id`。

## 2. 新增和修改的文件

### 新增

| 文件 | 说明 |
| --- | --- |
| `frontend/src/views/tasks/TaskDetailView.vue` | 任务详情页（替换 M0 占位） |
| `frontend/src/views/tasks/TaskListView.vue` | 任务管理列表页（一级导航，后端 `GET /tasks` 已支持列表与筛选） |
| `frontend/src/views/workflows/WorkflowDetailView.vue` | 工作流详情页（替换 M0 占位） |
| `frontend/src/components/artifact/ArtifactTable.vue` | 产物表格：文件名 / 类型 / 阶段 / 版本 / 大小 / 来源 / 审核状态 / 时间 / 下载，PRD 区与研发成果区共用 |
| `frontend/src/components/workflow/WorkflowStartDialog.vue` | 启动工作流对话框（类型、发起人、模拟流程说明） |
| `frontend/src/components/workflow/WorkflowNodePath.vue` | 节点路径：主路径 + 分支节点，五态样式 |
| `frontend/src/components/workflow/WorkflowEventTable.vue` | 事件日志表格（可展开 payload） |
| `frontend/src/constants/artifact.ts` | 产物类型白名单、大小上限、阶段标签、MIME 中文名、文本/Markdown/PDF 判定 |
| `frontend/src/utils/download.ts` | `saveBlob` / `artifactDisplayName` / `saveArtifact`（只经后端下载接口） |

### 修改

| 文件 | 改动 |
| --- | --- |
| `frontend/src/views/workflows/WorkflowListView.vue` | 由占位改为真实监控列表（筛选、分页、轮询、失败告警、刷新恢复） |
| `frontend/src/router/index.ts` | 新增 `/tasks` 任务管理路由；`task-detail` 的 `activeMenu` 由 `/projects` 改为 `/tasks` |
| `frontend/src/components/task/TaskTable.vue` | 新增 `hideWorkflow` 属性：全局任务列表不再显示「工作流」列（跨项目无法一次拿到每个任务的最新运行，避免把有运行的任务误标为「未启动」） |
| `frontend/src/utils/format.ts` | 新增 `parseDateTime`：无时区偏移的 ISO 串按 UTC 解析。SQLite 返回不带偏移的 UTC 串，此前被浏览器当成本地时间，同一运行的「开始时间」与「发起时间」相差 8 小时 |
| `frontend/src/views/workflows/WorkflowDetailView.vue` | 审批记录表加 `workflow-approvals` 类名（供验收脚本精确定位） |
| `frontend/src/utils/download.ts` | `revokeObjectURL` 延时由 1 s 改为 60 s：下载尚未结束时提前撤销 Blob URL 会被浏览器取消下载 |

## 3. 使用的后端 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/tasks/{task_id}` | 任务基本信息；404 判定不存在 |
| PUT | `/api/v1/tasks/{task_id}` | 编辑任务 |
| GET | `/api/v1/tasks?page&page_size&project_id&status&priority&keyword` | 任务管理列表 |
| GET | `/api/v1/tasks/{task_id}/artifacts?page&page_size&stage` | PRD（`stage=design`）与研发成果列表 |
| POST | `/api/v1/tasks/{task_id}/artifacts` | 上传需求文档（multipart，`stage=design`） |
| GET | `/api/v1/artifacts/{artifact_id}/download` | 下载产物（`FileResponse` + `Content-Disposition` + `X-Content-SHA256`） |
| GET | `/api/v1/tasks/{task_id}/workflows?page&page_size` | 该任务的历史运行 |
| POST | `/api/v1/tasks/{task_id}/workflow/start` | 启动运行，响应含 `id` / `thread_id` |
| GET | `/api/v1/workflows?page&page_size&status&project_id&task_id` | 监控列表与轮询 |
| GET | `/api/v1/workflows/{workflow_id}` | 详情与轮询 |
| GET | `/api/v1/workflows/{workflow_id}/logs?page&page_size` | 事件日志（`sequence` 升序）与轮询 |
| POST | `/api/v1/workflows/{workflow_id}/resume` | 恢复执行（仅 `paused`，只带后端 `thread_id`） |
| GET | `/api/v1/projects`、`/api/v1/projects/{id}` | 筛选候选项目、解析工作流所属项目名称 |

## 4. 是否新增后端接口及原因

未新增。M3 的每一项数据都能在既有接口上取到；两处曾考虑新增，最终按「优先复用、不改契约」的约束留在前端：

1. **产物下载文件名**：后端已回 `Content-Disposition`，前端直接读取，无需新接口。
2. **跨项目任务列表的最新运行状态**：需要「按 task_id 批量取最新工作流」的能力。前端选择隐藏该列而不是发 N 次请求，建议任务 6 评估在 `TaskRead` 增加可选的 `latest_workflow_status` 字段（纯新增、向后兼容）。

## 5. 数据库变更

无。未新增迁移，未改动模型与既有数据。

## 6. 页面实际运行截图

环境：后端 `127.0.0.1:8123`（临时 SQLite 库 + 本地文件存储，M1/M2 验收数据），Vite `127.0.0.1:5174`；headless Edge 157 经 CDP 驱动真实页面，视口 1680×1000（另附 1440×900 对照）。截图为真实渲染结果，非设计稿。

### 6.1 任务详情页

![任务详情 1680](./images/M3/01-task-detail-1680.png)
![任务详情 1440](./images/M3/02-task-detail-1440.png)

首屏四个卡片：基本信息、需求文档（PRD）、研发成果、工作流运行。存活运行存在时「启动工作流」按钮为禁用态并有警告条。1440×900 下 `docScrollWidth 1440 = clientWidth`、`mainScrollWidth 1212 = clientWidth`，无横向滚动。

### 6.2 上传校验与版本

![类型不符](./images/M3/03-upload-bad-type.png)
![上传成功](./images/M3/04-upload-v1.png)
![同名再传](./images/M3/05-upload-v2.png)

`.exe` 文件被前端拦截，日志中该步骤的上传请求数为 0（`apiUploads: []`）。合法上传后 toast「已上传 prd-m3.md（v5）」，同名再传生成 v6，v5 及更早版本审核状态变为「已被替换」，全部版本仍可下载。研发成果区同时列出人工上传的设计阶段文件与模拟工作流产物，来源列区分「人工上传 / 模拟成果」。

### 6.3 上传 / 下载失败

![上传失败](./images/M3/07-upload-network-error.png)

后端被拦截时显示「网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」，进度条消失（`uploading: false`）；下载失败同样提示，不静默。

### 6.4 编辑任务与任务已结束

![编辑任务](./images/M3/09-task-edited.png)
![任务已结束](./images/M3/10a-finished-task.png)

负责人改为「M3 验收」后页面与后端 `GET /tasks/{id}` 一致。任务 #2 的运行完成后其状态变为「已完成」，页面按钮禁用并显示「任务已结束（已完成或已取消），不能再启动工作流。」——与后端 409 规则一致。

### 6.5 启动工作流

![启动对话框](./images/M3/10-start-dialog.png)
![启动后跳转](./images/M3/12-workflow-detail.png)

对话框含模拟流程说明；确认后请求 `POST /tasks/0c0c9899…/workflow/start`，页面 URL 变为 `/workflows/69abfcf5-be7e-45ab-a439-3de4fa06b29e`，该 id 与后端响应体一致；后端记录 `status=waiting_approval`、`thread_id=wf-69abfcf5-…`、`current_step=human_approval`。

### 6.6 工作流详情：节点、事件、轮询

![事件展开](./images/M3/12b-event-expanded.png)
![轮询失败](./images/M3/14-poll-error.png)
![1440 适配](./images/M3/15-workflow-detail-1440.png)
![终态](./images/M3/28-workflow-completed.png)

节点路径为 START → 加载任务 → 生成模拟产物 → 校验产物 → 人工审批 → 完成，待审批时「人工审批」节点为等待态并高亮。9 秒窗口内实测 2 次详情 + 2 次日志请求（间隔 4 秒，无叠加）。拦截详情接口后仅出现告警且数据保留（5 个节点仍在），恢复后告警消失。运行完成后五个节点全为已完成，终态后 9 秒实测 0 个请求。

### 6.7 重复启动

![409 处理](./images/M3/16-duplicate-409.png)
![按钮禁用](./images/M3/17-start-disabled.png)

验收脚本先拦截 `GET /tasks/{id}/workflows` 使按钮可点，再点击启动：后端返回 409，toast 显示「状态冲突：该任务已有进行中的工作流（request_id: c2519042212c40c1b98cde7b3cef0f48）」，同时弹出确认框「工作流已存在 / 该任务已有进行中的工作流，不能重复启动。是否前往查看？」，选择「前往查看」后跳转到 `existing_workflow_id` 对应的详情页；页面重新加载后按钮回到禁用态。

### 6.8 工作流监控列表

![列表 1680](./images/M3/18-workflow-list-1680.png)
![筛选](./images/M3/19-workflow-list-filtered.png)
![刷新恢复](./images/M3/20-workflow-list-restore.png)
![空态](./images/M3/21-workflow-list-empty.png)
![列表 1440](./images/M3/22-workflow-list-1440.png)
![列表网络错误](./images/M3/26-workflow-list-network-error.png)

三个筛选（项目 / 任务 / 状态）与分页写入 URL，刷新后候选框显示已选中文案、请求串带上三个筛选参数；空结果显示「没有符合条件的工作流运行」+「清除筛选条件」；接口被拦截时整页错误态 +「重试」，重试后恢复 2 行。

### 6.9 任务管理列表与 404

![任务列表](./images/M3/23-task-list.png)
![任务 404](./images/M3/24-task-not-found.png)
![工作流 404](./images/M3/25-workflow-not-found.png)

关键词「搭建」+ 状态「开发中」筛选后仅 1 行，URL 带 `keyword=搭建&status=in_progress`。两种 404 均显示后端 message、`request_id` 与对应返回入口。

## 7. 测试命令和真实测试结果

### 7.1 前端

```
$ npm run type-check
> vue-tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json
（无输出，退出码 0）

$ npm run build
✓ built in 19.93s
（仅 Vite 既有的主包 >500 kB 提示，非错误）
```

### 7.2 后端

本阶段未改动后端代码，未重新执行 `pytest` / `ruff`；完整后端回归在任务 5 集成测试阶段统一执行（见最终验收报告）。

### 7.3 浏览器端功能验收（CDP 驱动真实页面）

脚本 `%TEMP%\m1run\m3shots.mjs`，输出 `m3shots.log` / `m3shots.json`，共 39 个步骤（另含 4 个前置/汇总步骤），全部通过；`console.error` 0 条、未捕获异常 0 条、`console.warn` 0 条。补充脚本 `%TEMP%\m1run\m3download.mjs`、`m3check.mjs` 用于下载内容与审批记录表。

关键实测数据：

| 项目 | 实测结果 |
| --- | --- |
| 类型不符文件上传 | 前端拦截，`POST` 请求数 0 |
| 同名上传版本 | v5 → v6，旧版 `superseded`，后端返回一致 |
| 下载内容 | 页面交给浏览器的 Blob：名称 `prd-m3.md`、137 B、与原文件逐字节相同；请求仅 `GET /artifacts/{id}/download` |
| 启动后跳转 | URL id == 后端响应 id == `69abfcf5-be7e-45ab-a439-3de4fa06b29e` |
| 轮询频率 | 9 秒内 2 次详情 + 2 次日志（4 秒间隔） |
| 终态停止轮询 | 完成后 9 秒内 0 个请求 |
| 409 重复启动 | 提示 + 确认框 + 跳转到 `existing_workflow_id` |
| 审批记录表 | 1 行：`1 / 已通过 / M3-script / 意见 / 2026-11-11 09:51:33`，与后端 `approvals` 一致 |
| 1440×900 / 1680×1000 | 两分辨率下主区域 `scrollWidth === clientWidth`，无横向滚动 |

### 7.4 未验证项

| 项目 | 原因 | 复验方式 |
| --- | --- | --- |
| `paused` → 「继续执行」按钮的 UI 路径 | `paused` 只在后端服务重启、由检查点恢复时产生；本轮验收未重启临时后端，无法在浏览器中构造该状态。逻辑已按后端契约实现（仅 `status==='paused'` 显示、确认框、只回传后端 `thread_id`、loading 防重复提交），恢复执行本身已由后端自动化测试覆盖 | 重启后端使存在 `paused` 运行后打开 `/workflows/{id}`；或 `python -m pytest backend/tests -q -k resume` |
| blob 下载落盘文件 | headless Edge 对 `blob:` 下载的落盘会被取消（`Browser.downloadProgress` 末态 `canceled`），属浏览器无头模式限制 | 在真实 Edge/Chrome 中点击「下载」，确认文件内容；页面侧内容已逐字节校验通过 |
| 事件日志超过 100 条时的翻页 | 当前模拟流程一轮最多 6 条事件 | 集成测试阶段构造多轮驳回运行后观察 |

## 8. 遗留问题

| 编号 | 说明 | 影响 | 建议 |
| --- | --- | --- | --- |
| M3-1 | 后端无「暂停」接口 | 页面没有暂停按钮，只能等运行进入终态或由重启恢复为 `paused` 后继续 | 若产品需要暂停，任务 6 评估新增 `POST /workflows/{id}/pause`（新接口 + 测试，不改既有契约） |
| M3-2 | 跨项目任务列表无法一次取得每个任务的最新运行 | 该页隐藏「工作流」列（项目详情页仍显示） | 任务 6 评估为 `TaskRead` 增加可选 `latest_workflow_status` |
| M3-3 | SQLite 下时间戳不带时区偏移，PostgreSQL 带 | 已在 `parseDateTime` 统一按 UTC 解析；若后端改为本地时区写入则会再次偏差 | 任务 6 评估后端统一返回带 `+00:00` 的 ISO 串 |
| M3-4 | 验收在临时库累积了 6 个 PRD 版本与 3 次运行（#1 待审批、#2/#3 已完成） | 仅影响本机临时 SQLite 库 | 无需处理；M4 验收将使用任务 #1 的待审批运行 |
| M3-5 | 事件日志需先取尽再前端分页 | 单次运行事件量小（每轮 6 条），当前无压力 | 事件量增大时改为后端分页 + 增量拉取 |

## 9. 结论

M3 功能点全部落地：任务详情的基本信息 / 编辑、需求文档上传（校验、进度、版本、下载）、研发成果列表与模拟成果标注、启动工作流与重复启动防护；工作流监控列表的筛选 / 分页 / 轮询 / 刷新恢复；工作流详情的节点路径、事件日志、轮询与终态停止、待审批的专门呈现。`type-check` 与 `build` 通过，39 步 CDP 真实验收全部通过且无控制台错误，未新增后端接口与数据库迁移。可以进入 M4。
