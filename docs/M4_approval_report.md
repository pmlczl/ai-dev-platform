# M4 —— 人工审批 交付报告

> 日期：2026-11-11
> 范围：任务 5 的 M4 阶段——一级导航「人工审批」的待审批队列 `/approvals` 与审批详情 `/approvals/:workflow_id`，含按类型页内预览、通过 / 驳回决定、二次确认、幂等提交、审批历史与全部异常态。
> 前置：M0（类型 / API 封装 / 公共组件 / 路由）、M1（项目列表）、M2（项目详情）、M3（任务详情 + 工作流监控）已完成；M1–M4 改动均未提交。

## 0. 开发前检查结论

- 已通读 `docs/task5_task6_api_inventory.md`、`docs/task5_task6_implementation_plan.md`、`docs/M0_development_report.md`、`docs/M1_project_management_report.md`、`docs/M2_project_detail_report.md`、`docs/M3_task_workflow_report.md`，并逐一核对 `backend/app/api/v1/endpoints/*.py`、`app/schemas/*.py`、`app/services/*.py` 的真实行为。
- M4 所需数据与动作全部有既有接口可用，**本阶段未新增任何后端接口，未新增数据库迁移，未改动既有 API 契约，未改动 LangGraph 核心图，未改动审批规则**。
- 核对后确认的后端事实，直接决定了页面设计：
  1. **没有独立的审批表接口**。待审批队列就是 `GET /workflows?status=waiting_approval`；审批详情所需的待办信息全部在 `GET /workflows/{id}` 的 `pending_approval` 里（`app/services/workflows.py:595-611`：`request_id`、`iteration`、`artifact_id`、`artifact_version`、`preview`、`revision_comments[]`、`requested_at`），审批历史在同一响应的 `approvals[]` 中。页面不自建“审批单”概念，也不缓存这些字段。
  2. **提交决定只有一个入口**：`POST /workflows/{id}/resume`。`WorkflowResumeRequest` 要求 `thread_id`、`decision`、`approver`（`app/schemas/workflow.py:59`「提交审批结果时必须提供审批人」）、可选 `comment`（≤5000）与 `idempotency_key`（`^[A-Za-z0-9._:-]+$`，≤100）。
  3. **后端防护顺序**（`app/services/workflows.py:292-337`，实测逐条命中）：`thread_id` 只是断言，不一致直接 409「thread_id 与工作流实例不一致」；同一幂等键命中已有记录 → 返回当前状态、**不新增记录**；已结束 → 409「工作流已结束，无法继续」；待审批但未带决定 → 409「工作流正在等待审批，必须提交审批结果」；决定已落库但图未推进（进程中途退出）→ 补推进且**不写第二条记录**。
  4. **`thread_id` 一律取自 `GET /workflows/{id}` 的响应**并原样回传，前端不拼接 `wf-{id}`（该格式只写在后端）。
  5. **产物版本语义**：模拟流程每轮生成的产物路径为 `workflow/…/iteration-N/demo-artifact.md`，其 `version` 恒为 1——版本号递增属于 PRD 上传（同一文件的新版本），不属于生成的轮次。页面显示后端给出的 `pending_approval.artifact_version`，不假设“轮次 = 版本”。
  6. **平台没有登录与权限校验**，`approver` 是自报姓名。页面在对话框与详情页各有一条说明，措辞为「审批人为自报姓名，仅作为记录写入审批历史」，不出现“已认证”“当前用户”之类的表述。
  7. 后端另有 `POST /artifacts/{id}/review`（只改产物审核状态、不推动运行）。审批页**没有**使用它：审批的语义是让人工决定驱动图前进，只改产物状态会让产物与运行状态不一致；产物状态由 resume 之后的服务层统一写入。
  8. 文件内容只经 `GET /artifacts/{id}/download`（`FileResponse` + `Content-Disposition` + `X-Content-SHA256`）读取，前端不构造任何存储路径。
- 既有工作流为 LangGraph **模拟**流程，产物由固定模板生成。详情页标题写作「研发工作流（模拟）」，产物卡片带「模拟成果」标签，预览卡片说明写明内容来自后端下载接口。

## 1. 功能清单

### 1.1 待审批队列 `/approvals`

| 需求 | 实现 | 状态 |
| --- | --- | --- |
| 只显示 `status=waiting_approval` 的运行 | `GET /workflows?status=waiting_approval&page&page_size`，该状态由代码固定而非用户可选；无独立审批表 | 完成 |
| 列：项目名 / 任务名 / 轮次 / 等待时长 | 列头实测为 工作流 ID、项目、任务、轮次、待审批产物、状态、发起时间、**等待时长**、操作；项目与任务名经 `useReferenceStore` 按 id 解析（每个 id 只查一次），任务名带 `#序号` 并可点击跳转 | 完成 |
| 待审批产物可见 | 文件名（tooltip 为完整相对路径）+ `vN` + 大小，数据来自 `current_artifact` 与 `pending_approval.artifact_version` | 完成 |
| 分页 + 按项目 / 任务筛选 | 筛选与分页写入 URL；任务下拉随项目联动，URL 中的 `task_id` 即使不在候选里也会解析出名称；「清除筛选」一键回到无条件 | 完成 |
| 筛选后为空 | 「没有符合条件的待审批运行」+「清除筛选条件」按钮；无条件为空时为「当前没有等待人工审批的运行」+「前往工作流监控」 | 完成 |
| 轮询 5 秒 | `APPROVAL_QUEUE_POLL_INTERVAL_MS = 5000`，`setTimeout` 链式调度：上一请求未返回不排下一次；列表有行才轮询；页头显示「每 5 秒自动刷新 · 更新于 …」 | 完成 |
| 离开页面停止轮询 | `onBeforeUnmount` 置 `unmounted` 并清定时器；定时器回调再检查 `route.name !== 'approvals'` | 完成 |
| 轮询失败不打断阅读 | 只在页头下方追加告警「自动刷新失败，列表可能不是最新：网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」，已有行保留、继续轮询；恢复后告警自动消失 | 完成 |
| 他处已决定的运行自动离开队列 | 队列每次刷新都重新读后端，无本地“待办”副本；实测：另一页面先提交后，本页刷新即少一行 | 完成 |
| 刷新恢复 | 重新加载后 URL 的 `project_id / page / page_size` 全部生效，请求参数与 URL 一致 | 完成 |

### 1.2 审批详情 `/approvals/:workflow_id`

| 需求 | 实现 | 状态 |
| --- | --- | --- |
| A. 审批对象信息 | 「审批对象」卡片 `el-descriptions`：所属项目（名称 + 代号）、所属任务（`#序号 标题`，可跳转）、工作流类型、运行状态、当前节点（中文标签 + 后端原始值 `human_approval`）、轮次、审批请求 ID、发起时间、开始时间、工作流 ID | 完成 |
| B. 待审批产物 | 文件名（相对路径 tooltip）、版本、大小、审核状态、生成时间、SHA-256；卡片带「模拟成果」标签与「刷新」按钮 | 完成 |
| B. 历史修改意见 | `pending_approval.revision_comments` 非空时列出「历史修改意见（N 条，本轮之前）」，为空时写明「本轮之前没有收到修改意见。」 | 完成 |
| C. 按类型页内预览 | `ArtifactPreview` 按 `file_type` 分支：Markdown → 自研安全渲染器；txt/json/yaml → 转义后 `<pre>`；PDF → 临时 object URL 交给浏览器查看器；其他类型只给下载。内容仅 `GET /artifacts/{id}/download`，Blob 在内存中读取，不落地路径 | 完成（PDF / 其他类型分支未在浏览器中构造，见 7.5） |
| C. 预览安全 | `utils/markdown.ts` 先转义 `& < > " '` 再仅用本模块自写的标签构造 HTML；链接仅 `http(s)`、`#`、同源绝对路径可点击，`javascript:` / `data:` / 协议相对 `//host` 保持纯文本。实测注入样本中 `previewUnsafeNodes = 0`（无 `href="javascript:"`、无 `onclick`、无外部脚本节点） | 完成 |
| D. 通过 | 「通过」→ 对话框（审批人必填、意见可选）→ 二次确认「确认通过工作流 … 的产物「demo-artifact.md」？通过后本轮被接受，运行进入完成。」→ `POST /workflows/{id}/resume`（`decision=approved`）→ 成功提示「已通过，运行状态：已完成」→ 用后端响应更新页面 | 完成 |
| D. 驳回 | 同上，理由**必填**：留空提交时表单报「驳回必须填写理由，下一轮生成依赖这段说明。」且不发请求、不弹确认框；确认后文案引用该理由，`decision=rejected` | 完成 |
| D. 防重复提交 | 对话框按钮 `:loading` + 父组件 `submitting` 双重防护；DOM 层连点两次「确认提交」实测只产生 1 个 `POST /resume` | 完成 |
| D. 幂等 | 每个审批请求一个键：`web-<request_id>:<decision>`（`request_id` 即后端 `pending_approval.request_id`，形如 `<workflow_id>:<iteration>`）。同一键重放实测返回 200 且审批记录仍为 1 条 | 完成 |
| E. 并发 / 过期页面 | 页面停留在旧状态再提交 → 后端 409，提示「状态冲突：工作流已结束，无法继续（request_id: …）」，页面立即重读真实状态并转为只读：标签「已完成 / 本页只读」、告警「该运行当前为「已完成」，不在待审批状态，不能提交审批决定。」、提交卡片消失，历史仍为 1 条 | 完成 |
| 审批历史只追加 | 「审批历史」表按 `sequence` 升序显示 序号 / 结果 / 审批人 / 意见 / 时间；页面没有编辑或删除入口，数据源为 `GET /workflows/{id}` 的 `approvals` | 完成 |
| 非待审批状态可追溯但只读 | 终态运行仍可读：产物、历史、`当前节点`；`轮次`、`审批请求 ID`、`发起时间` 显示「—」 | 完成 |
| 404 | 「未找到：工作流 00000000-… 不存在（request_id: …）」+ 说明「该审批不存在，或对应的运行已被删除。」+「返回审批列表」/「重试」 | 完成 |
| 接口失败 | 显示后端中文 message 与 `request_id`，「重试」重新读取 | 完成 |

### 1.3 布局与状态

一级导航为 项目管理 / 任务管理 / 工作流监控 / 人工审批；`/approvals/:workflow_id` 为二级路由，`meta.activeMenu = '/approvals'` 保证菜单高亮停在「人工审批」，面包屑「首页 / 人工审批 / 审批详情」。Loading / Empty / Error / Success 四态由 `PageState` 统一呈现，错误文案为中文并带 `request_id`。1440×900 与 1680×1000 实测：文档与主区域 `scrollWidth === clientWidth`，队列表格 `body.scrollWidth === body.clientWidth`（横向溢出 0），长文件名以 ellipsis + tooltip 截断，无无意义横向滚动。刷新后路由与数据均由后端重新加载，Pinia 只保存跨页上下文（最近查看的运行 id 等），不是任何页面的唯一数据源。

## 2. 新增和修改的文件

### 新增

| 文件 | 说明 |
| --- | --- |
| `frontend/src/views/approvals/ApprovalDetailView.vue` | 审批详情页（审批对象 / 待审批产物 / 预览 / 历史 / 提交决定，只读态与冲突处理） |
| `frontend/src/components/approval/ApprovalQueueTable.vue` | 队列表格（9 列，含轮次、产物版本与大小、等待时长） |
| `frontend/src/components/approval/ApprovalDecisionDialog.vue` | 决定对话框（审批人 / 意见、驳回理由必填、提交前二次确认、无鉴权说明） |
| `frontend/src/components/approval/ArtifactPreview.vue` | 按类型页内预览（Markdown / 文本 / PDF / 仅下载），内容只走后端下载接口 |
| `frontend/src/utils/markdown.ts` | 转义优先的安全 Markdown 渲染器与 `escapeHtml` |
| `frontend/src/constants/approval.ts` | 审批字段上限（与 `WorkflowResumeRequest` 对齐）、`approvalIdempotencyKey()`、队列轮询间隔 |

### 修改

| 文件 | 改动 |
| --- | --- |
| `frontend/src/views/approvals/ApprovalQueueView.vue` | 由 M0 占位（`el-empty`「页面在 M5 实现」）改为真实队列：筛选、分页、5 秒轮询、轮询失败行内告警、刷新恢复、跳转审批 |
| `frontend/src/router/index.ts` | 新增 `/approvals/:workflow_id`（`approval-detail`，`hideInMenu`，`activeMenu=/approvals`） |
| `frontend/src/utils/format.ts` | 新增 `formatElapsedSince()`：把时间差渲染为「不足 1 分钟 / N 分钟 / N 小时 M 分 / N 天 M 小时」，整点不显示 0 分，未来时间不显示负值（队列「等待时长」列） |

未改动：`api/approvals.ts`（M0 已有 `submitWorkflowApproval()`，仅转发 `resumeWorkflow`）、`api/workflows.ts`、`api/artifacts.ts`、`types/index.ts`（`pending_approval` / `approvals` 字段 M0 已声明）、后端全部文件。

## 3. 使用的后端 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/workflows?status=waiting_approval&page&page_size&project_id&task_id` | 待审批队列、筛选、分页与 5 秒轮询 |
| GET | `/api/v1/workflows/{workflow_id}` | 审批详情：`pending_approval`、`current_artifact`、`approvals`、`thread_id` |
| POST | `/api/v1/workflows/{workflow_id}/resume` | 提交通过 / 驳回（`thread_id` 取自上一条响应，带 `idempotency_key`） |
| GET | `/api/v1/artifacts/{artifact_id}` | 产物元数据（名称、版本、大小、审核状态、SHA-256） |
| GET | `/api/v1/artifacts/{artifact_id}/download` | 预览内容与「下载原文件」（唯一的内容来源） |
| GET | `/api/v1/projects/{id}`、`/api/v1/tasks/{id}` | 解析队列与详情中的项目名、任务名 |
| GET | `/api/v1/projects?page&page_size`、`/api/v1/tasks?project_id&page&page_size` | 队列筛选候选项 |
| GET | `/api/v1/health` | 顶栏后端状态灯（既有能力，非本阶段新增） |

## 4. 是否新增后端接口及原因

未新增。队列、详情、决定、预览、历史所需的每一项数据都能由既有接口取得；两处曾考虑新增，最终按「优先复用、不改契约」的约束留在前端或留给任务 6：

1. **「按审批状态排序 / 等待时长」的服务端计算**：等待时长由 `pending_approval.requested_at` 与浏览器时间差渲染。若任务 6 需要「超时未审批」提醒，建议后端补一个只读的 `waiting_seconds` 字段（纯新增、向后兼容），避免各页面各自计算。
2. **审批人身份**：平台没有登录，`approver` 只能自报。未新增任何“伪登录”接口；页面用两条文案把这一点说明清楚。真实身份需要任务 6 的鉴权设计。

## 5. 数据库变更

无。未新增迁移，未改动模型与既有数据；审批记录仍由后端服务写入 `workflow_approvals`（只追加）。

## 6. 页面实际运行截图

环境：后端 `127.0.0.1:8123`（临时 SQLite 库 + 本地文件存储，M1–M3 验收数据），Vite `127.0.0.1:5174`；headless Edge 157（`Edg/157.0.4341.42`）经 CDP 驱动真实页面，视口 1680×1000，另附 1440×900 对照。截图为真实渲染结果，非设计稿。

验收数据由脚本现场创建：任务 #9「M4 验收：驳回后二轮通过」、#10「M4 验收：并发审批提示」、#11「M4 验收：始终不启动」（用于筛选空态），#12「M4 验收：连点两次通过」。任务 #1 的运行 `798e9e90`（第 1 轮、0 条审批）**全程未被提交决定**，留作人工验收对象。

### 6.1 待审批队列

![队列 1680](./images/M4/01-queue-1680.png)

3 行待审批运行，列头含轮次与等待时长；页头「共 3 项等待决定」「每 5 秒自动刷新 · 更新于 …」。

![项目筛选](./images/M4/02-queue-filter-project.png)

![筛选空态](./images/M4/03-queue-empty-filter.png)

![刷新恢复](./images/M4/04-queue-refresh-restore.png)

### 6.2 审批详情与页内预览

![详情 1680](./images/M4/05-detail-1680.png)

![Markdown 页内预览](./images/M4/06-preview-markdown.png)

### 6.3 驳回

![驳回理由必填](./images/M4/07-reject-reason-required.png)

![驳回二次确认](./images/M4/08-reject-confirm.png)

![驳回后第二轮](./images/M4/10-after-reject-round2.png)

### 6.4 通过

![通过对话框](./images/M4/11-approve-dialog.png)

![通过二次确认](./images/M4/12-approve-confirm.png)

![通过后已完成且只读](./images/M4/14-after-approve-completed.png)

### 6.5 并发决定与连点提交

![停留在旧状态的页面](./images/M4/15-page-before-conflict.png)

![重复提交得到 409](./images/M4/16-duplicate-approval-409.png)

![连点两次确认提交](./images/M4/25-double-click-one-request.png)

### 6.6 异常态

![审批不存在](./images/M4/18-detail-not-found.png)

![列表网络失败](./images/M4/19-queue-network-error.png)

![重试后恢复](./images/M4/20-queue-recovered.png)

### 6.7 补充验收（轮询、等待时长、单产物请求、轮询失败）

![队列 1440×900](./images/M4/21-queue-columns-1440.png)

![自动刷新失败但行保留](./images/M4/22-queue-poll-error.png)

![详情页产物接口只调一次](./images/M4/23-detail-single-artifact-request.png)

![队列 1680×1000](./images/M4/24-queue-columns-1680.png)

![队列 1440（主验收）](./images/M4/21-queue-1440.png)

![详情 1440（主验收）](./images/M4/22-detail-1440.png)

![队列收尾](./images/M4/24-queue-final.png)

## 7. 测试命令和真实测试结果

### 7.1 前端

```
$ npm run type-check
> vue-tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json
（无输出，退出码 0）

$ npm run build
✓ built in 8.29s
（仅 Vite 既有的主包 >500 kB 提示，非错误）
```

两条命令在 M4 最后一次改动（`formatElapsedSince`、队列轮询、详情页产物请求合并）之后重新执行，均为真实退出码 0。

### 7.2 后端

本阶段未改动后端代码，未在此处重新执行 `pytest` / `ruff`；完整后端回归在任务 5 集成测试阶段统一执行，结果见 `docs/task5_final_acceptance_report.md`。

### 7.3 渲染器与格式化函数（Node 直接导入真实模块，非 Mock）

```
$ node --experimental-strip-types %TEMP%\m1run\m4markdown.mjs
{"summary":"8/8 通过", ...}      # headings-and-lists / code / emphasis / html-is-escaped / link-whitelist / quote / plain-text / escape

$ node --experimental-strip-types %TEMP%\m1run\m4format.mjs
{"summary":"12/12 通过", ...}    # 空值 / 无法解析 / 不足 1 分钟 / 未来时间 / 42 分钟 / 59 分钟 / 1 小时 / 2 小时 15 分 / 23 小时 59 分 / 1 天 / 3 天 5 小时 / 时间戳格式
```

两个脚本用 `file:///D:/project/...` 动态导入 `frontend/src/utils/markdown.ts` 与 `frontend/src/utils/format.ts` 本体，`m4format.mjs` 另取真实队列行的 `requested_at` 复核显示值（`2026-11-10T14:55:20Z` → 「12 小时 1 分」）。

### 7.4 浏览器端功能验收（CDP 驱动真实页面）

主脚本 `%TEMP%\m1run\m4shots.mjs` → `m4shots.log` / `m4shots.json`，25 个步骤全部通过；`console.error` 0 条、`console.warn` 0 条、未捕获异常 0 条。补充脚本 `%TEMP%\m1run\m4queue.mjs`（8 步）与 `%TEMP%\m1run\m4double.mjs`（5 步），同样控制台干净。

关键实测数据：

| 验收标准 | 实测结果 |
| --- | --- |
| 队列只含待审批 | 请求 `GET /workflows?status=waiting_approval&page=1&page_size=20`；`共 3 项等待决定`，3 行状态列均为「待审批」 |
| 列含项目 / 任务 / 轮次 / 等待时长 | 列头 `工作流 ID / 项目 / 任务 / 轮次 / 待审批产物 / 状态 / 发起时间 / 等待时长 / 操作`；等待时长实测「不足 1 分钟」（新建 1 分钟内）与「12 小时 4 分」（跨天） |
| 轮询 5 秒 | 12 秒窗口内列表请求 2 次（间隔 5 秒），页头时间随之更新；请求未回不叠加 |
| 轮询失败 | 拦截列表接口后出现「自动刷新失败，列表可能不是最新：网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」，行仍为 1 条；解除拦截后点「刷新」告警消失 |
| 筛选与刷新恢复 | URL `?project_id=…&page=1&page_size=10` → 请求同参数、`共 3 条 10条/页`、项目下拉显示「PRJ-2026-001 AI 研发平台基础工程」 |
| 筛选空态 | `?project_id=…&task_id=<未启动任务>` → 「没有符合条件的待审批运行」+「清除筛选条件」 |
| 详情请求集合 | `GET /workflows/{id}`、`/projects/{id}`、`/tasks/{id}`、`/artifacts/{id}`、`/artifacts/{id}/download` 各 1 次；`GET /artifacts/{id}` 次数 = 1（修复前为 2），刷新后仍为 1；`POST` 次数 = 0 |
| 预览内容来源 | 只有 `/artifacts/{id}/download` 返回内容；页内渲染 H1/H2 标题 4 个、列表 3 组、段落 3 段；注入样本的危险节点数 0 |
| 驳回理由必填 | 留空提交：`formErrors=["驳回必须填写理由，下一轮生成依赖这段说明。"]`，`messageBox=null`，`POST /resume` 次数 0 |
| 驳回生效 | 1 个 `POST /workflows/{id}/resume`；后端 `waiting_approval` 第 2 轮、`request_id …:2`、`revision_comments=[理由原文]`、审批记录 1 条「已驳回 / M4-验收-王五」；页面出现「历史修改意见（1 条，本轮之前）」与告警「本轮之前已有 1 次决定；当前是第 2 轮的审批请求，提交后立即生效。」 |
| 通过生效 | toast「已通过，运行状态：已完成」；后端 `completed`、`current_step=complete_workflow`、任务状态 `completed`、两条审批记录（1 rejected / 2 approved）；产物 `iteration-2/demo-artifact.md` 502 B、审核状态「已通过」 |
| 连点两次「确认提交」 | `POST /resume` 次数 = 1，键 `web-<request_id>:approved`；后端 `completed` + 1 条记录；随后用同一键直接重放 → 200、状态 `completed`、记录仍 1 条 |
| 过期页面重复审批 | 另一路径先决定后，本页提交得到「状态冲突：工作流已结束，无法继续（request_id: 6fcc3c3c…）」，自动重读为只读（标签「已完成」「本页只读」，提交卡片消失），历史仍 1 条 |
| 接口防护（直连后端复核） | 同键重放 200 无新记录；终态 + 新键 409「工作流已结束，无法继续」；错误 `thread_id` 409「thread_id 与工作流实例不一致」；`798e9e90` 前后均为 `waiting_approval`、审批记录 0 → 0 |
| 404 | 「未找到：工作流 00000000-… 不存在（request_id: 34e56d00…）」+「返回审批列表」/「重试」 |
| 列表接口断网 | 「网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」+「重试」，恢复后队列重新显示 |
| 1440×900 / 1680×1000 | 两分辨率下 `docScrollWidth == docClientWidth`、`mainScrollWidth == mainClientWidth`；队列表格 `horizontalScroll = 0` |
| 数据可追溯 | 收尾核对：`waiting=[798e9e90/aa6ece90]`，9 次运行的项目 / 任务 / 产物 / 审批记录一一对应，队列最终 `共 1 项等待决定` |

### 7.5 未验证项

| 项目 | 原因 | 复验方式 |
| --- | --- | --- |
| PDF 与其他类型的页内预览分支 | 模拟流程只产出 Markdown，审批页的预览对象始终是生成的 `.md` 文件；本轮没有构造出“待审批的 PDF 产物”。分支逻辑（`file_type` → object URL / 仅下载）已按 `constants/artifact.ts` 判定实现，内容来源与 M3 的下载实测为同一接口 | 上传 PDF 作为 PRD 后在任务详情下载验证接口；或在有 PDF 类型工作流产物时打开 `/approvals/{id}` 观察 iframe |
| 审批人身份校验 | 平台无登录，后端只校验 `approver` 非空与长度 | 任务 6 引入鉴权后，`approver` 改为取自会话而非输入框 |
| 队列分页超过 1 页 | 本轮最多 3 条待审批运行，未触发翻页（翻页控件与 `page_size` 切换已实测） | 批量启动 ≥20 个运行后翻页 |
| 详情页自动刷新 | 计划只要求待办列表轮询；详情页不轮询，避免定时器替换审批人正在填写的表单，改为「刷新」按钮 + 提交后立即用后端响应更新 + 409 时强制重读 | 人工验收时开两个标签页复现并发场景 |

## 8. 遗留问题

| 编号 | 说明 | 影响 | 建议 |
| --- | --- | --- | --- |
| M4-1 | 无登录与角色，审批人自报且任何人可提交 | 审批记录无法作为责任凭证；并发决定靠后端 409 与幂等键兜住 | 任务 6 引入最小鉴权（会话 + 角色），`approver` 改由后端从会话写入 |
| M4-2 | 队列没有「超时未审批」提醒 | 长时间等待只能靠「等待时长」列人工判断 | 任务 6 评估后端返回 `waiting_seconds` 与阈值提醒 |
| M4-3 | 详情页不轮询，可能显示旧状态 | 他处先决定时本页会撞 409 后自动纠正（已实测），不会写出错误数据 | 若需要即时性，可在详情页加「有新决定」提示（读取 `pending_approval.request_id` 变化），但不自动覆盖表单 |
| M4-4 | 每轮生成的产物 `version` 恒为 1，轮次信息只在 `iteration` / 路径中 | 审批人看到的「版本 v1」不体现第几轮，易被误读 | 保持与后端一致（不自造版本）；任务 6 若要让生成产物也走版本递增，需同时改校验与历史语义 |
| M4-5 | 验收在临时库累积了多轮运行与任务（#6–#12，含 8 次已完成运行） | 仅影响本机临时 SQLite 库 | 无需处理；`798e9e90` 仍为待审批、0 条记录，供人工验收使用 |
| M4-6 | 队列轮询期间 `reference` 缓存只增不减 | 长时间停留在本页且运行频繁变化时，缓存条目缓慢增长 | 任务 6 可给 `useReferenceStore` 加容量上限或按路由清空 |

## 9. 结论

M4 功能点全部落地：待审批队列（只读自 `status=waiting_approval`、9 列含轮次与等待时长、筛选 / 分页 / 5 秒轮询 / 失败行内告警 / 刷新恢复）、审批详情（对象与产物信息、按类型页内预览且内容只经后端下载接口、安全渲染器实测 0 危险节点）、通过 / 驳回（驳回理由必填、二次确认、`thread_id` 取自后端、每审批单一个幂等键、连点只提交一次）、审批历史只追加、并发与过期页面的 409 处理、404 与断网中文提示、1440×900 与 1680×1000 无横向滚动。`type-check` 与 `build` 通过，25 步主验收 + 8 步队列补充 + 5 步连点验收全部通过且控制台无错误、无警告、无未捕获异常；未新增后端接口与数据库迁移，未改动 LangGraph 核心与审批规则。任务 5 的 M2–M4 业务闭环（项目 → 任务 → 需求文档 → 工作流 → 待审批 → 通过 / 驳回 → 下一轮或完成）已在真实页面上跑通，可以进入集成测试与最终验收文档。
