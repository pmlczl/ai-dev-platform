# 任务 5 人工验收指南（M2 项目详情 / M3 任务与工作流 / M4 人工审批）

生成日期：2026-11-11
适用代码：`develop` 分支 HEAD `2af903b` 之上的工作区改动（M1–M4 前端改动尚未提交，见最终验收报告 G-18）
配套报告：[task5_final_acceptance_report.md](./task5_final_acceptance_report.md)、[M2_project_detail_report.md](./M2_project_detail_report.md)、[M3_task_workflow_report.md](./M3_task_workflow_report.md)、[M4_approval_report.md](./M4_approval_report.md)

> **重要前提**：本平台的 LangGraph 工作流是**模拟流程**，节点不调用任何大模型，审批通过后也不触发真实 AI。验收时看到的「生成模拟产物」节点输出由代码模板拼装，页面与接口都带有「模拟」字样标识。

---

## 0. 怎么使用本指南

1. 第 1 章确认验收范围，第 2 章起环境，第 3 章准备数据。
2. 第 4–11 章是八个验收场景，每个场景都是一张「步骤 / 操作 / 预期结果 / 失败判定」表。按行执行即可，不需要读代码。
3. 每行只有三种结论：**通过**（与预期结果一致）、**缺陷**（命中「失败判定」描述的现象）、**已知项**（第 13 章列出的、按当前范围刻意不实现的行为，不计缺陷）。
4. 第 12 章把人工步骤映射到自动化已跑过的证据编号与截图，遇到不一致时可对照排查。
5. 第 14 章是验收记录表，可直接复制填写；第 15 章是缺陷提交模板。

判定口径统一为三句话：

- 页面显示的内容与后端接口返回的内容一致 → 通过；
- 刷新后页面内容从后端重新加载、不依赖内存状态 → 通过；
- 任何异常都要有中文提示，且能看到 `request_id` 供排查 → 通过。

---

## 1. 验收目标与范围

| 模块 | 验收目标 | 对应页面 |
| --- | --- | --- |
| M2 | 项目列表 → 项目详情，详情能管理该项目下的任务 | `/projects`、`/projects/:project_id` |
| M3 | 任务详情、PRD 上传与版本、下载、启动工作流、工作流监控（节点/事件/轮询） | `/tasks`、`/tasks/:task_id`、`/workflows`、`/workflows/:workflow_id` |
| M4 | 待审批队列、审批详情预览、通过/驳回、审批历史（只追加） | `/approvals`、`/approvals/:workflow_id` |
| 全局 | 一级导航、Loading/Empty/Error/Success/NotFound 五态、布局无横向滚动、刷新恢复 | 站点框架 |

**不在本次验收范围内**（属于任务 6 或平台后续能力）：真实 AI 模型调用、真实 Agent 调度、用户登录与角色权限、GitLab 真实仓库联动、Docker/PostgreSQL 环境验证、PDF 与图片类产物的在线预览。

---

## 2. 环境准备

### 2.1 依赖

| 组件 | 版本要求 | 自检命令 |
| --- | --- | --- |
| Python | 3.11+ | `python --version` |
| Node.js | 18+（本次自动化在 24.20.0 上跑通） | `node --version` |
| 数据库 | PostgreSQL 或 SQLite 均可（本项目验收用 SQLite 临时库） | 见 2.2 |
| 浏览器 | Chrome / Edge 最新版 | 手动 |

### 2.2 后端启动（干净环境）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # PowerShell 禁止脚本时改用 .\.venv\Scripts\activate.bat
pip install -e ".[dev]"
Copy-Item ..\.env.example ..\.env     # 按需修改 POSTGRES_* 或直接设 DATABASE_URL
python -m alembic upgrade head        # 建表；等价于 .\scripts\init_db.ps1
python -m uvicorn app.main:app --reload --port 8000
```

不想装 PostgreSQL 时，用 SQLite 跑整套验收（本次自动化就是这么跑的）：

```powershell
# 在项目根目录的 .env 里设置（或在启动命令前临时覆盖）
$env:DATABASE_URL = "sqlite+aiosqlite:///./dev.db"
$env:WORKFLOW_CHECKPOINT_BACKEND = "sqlite"     # 默认即 sqlite
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

关键环境变量（完整清单见 README「环境变量」章）：

| 变量 | 默认值 | 验收时要知道的事 |
| --- | --- | --- |
| `STORAGE_ROOT` | `backend/storage` | 上传文件的落盘目录，数据库只存相对路径；下载内容与此处的文件逐字节一致 |
| `STORAGE_MAX_UPLOAD_SIZE` | 52428800（50 MiB） | 超过即拒绝，用于场景六的「文件过大」用例 |
| `STORAGE_ALLOWED_EXTENSIONS` | pdf,docx,md,markdown,txt,json,yaml,yml | 白名单外的扩展名前端直接拦截，不发请求 |
| `WORKFLOW_MAX_ITERATIONS` | 3 | 返工轮次上限，超过后工作流判定失败；场景五只跑到第 2 轮，不会触发 |
| `WORKFLOW_CHECKPOINT_BACKEND` | sqlite | `postgres` / `sqlite` / `memory` 三种；`memory` 重启即丢流程状态，验收请用前两种 |
| `API_V1_PREFIX` | `/api/v1` | 所有接口的统一前缀 |

### 2.3 前端启动（另开终端）

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local     # 默认把 /api 代理到 http://localhost:8000
npm run dev
```

- 访问地址：`http://localhost:5173`
- 后端端口不是 8000 时，改 `.env.local` 的 `VITE_DEV_API_PROXY_TARGET`（本次自动化用的是 `8123` 后端 + `5174` 前端）
- 前端**没有 lint 脚本**，静态检查命令是 `npm run type-check`

### 2.4 冒烟检查（开始验收前必做）

| 检查 | 命令 / 操作 | 预期 |
| --- | --- | --- |
| 后端活着 | `curl -i http://127.0.0.1:8000/api/v1/health` | HTTP 200；响应体 `{"status":"ok","app":"AI Dev Platform","version":"0.1.0","environment":"development","timestamp":"…"}`；**响应头**有 `X-Request-ID`（`request_id` 只在响应头，不在 `/health` 响应体里，属正常） |
| 迁移到位 | `cd backend; python -m alembic heads`（离线，不连库） | `0004_workflow_engine (head)` |
| 库已升级 | `cd backend; python -m alembic current` | 同样输出 `0004_workflow_engine (head)`；若本机没有 PostgreSQL，这条命令会先报 `ConnectionRefusedError`——请先按 2.2 设置 `DATABASE_URL` 或 `POSTGRES_*` |
| 接口可读 | 浏览器打开 `http://127.0.0.1:8000/api/v1/projects?page=1&page_size=5` | JSON，`items` 为数组，`total`/`page`/`page_size` 齐全 |
| 前端可开 | 访问 `http://localhost:5173/projects` | 左侧出现四个一级菜单：项目管理 / 任务管理 / 工作流监控 / 人工审批 |

---

## 3. 测试数据准备

二选一。**方案 A 更贴近真实验收**（自己造数，链路最干净）；**方案 B 更快**（直接复用自动化留下的靶子数据）。

### 3.1 方案 A：全新库 + 手工造数

1. 用 2.2 的命令初始化一个空库（或删除 `dev.db` / 空 PostgreSQL 库后重新 `python -m alembic upgrade head`）。
2. 在 `/projects` 点「新建项目」，填：

   | 字段 | 建议值 |
   | --- | --- |
   | 项目编号 | `DEMO2026`（唯一，字母数字与短横线） |
   | 项目名称 | `任务 5 人工验收项目` |
   | 项目描述 | 任意中文 |
   | 负责人 | `验收人-张三` |

3. 在项目详情点「新建任务」建两个任务：
   - 任务一：`验收任务一：一轮通过`
   - 任务二：`验收任务二：驳回后二轮`
   描述里写清需求，模拟节点会把需求文本带进产物内容，便于第 8 场景核对「驳回理由真的进了下一轮」。
4. 准备三个本地文件（放在任意目录，用完可删）：

   | 文件 | 用途 | 要求 |
   | --- | --- | --- |
   | `prd.md` | 正常上传 | Markdown，几 KB 即可；内容里保留一行独特文本（如项目编号），下载后逐字比对 |
   | `bad.exe` | 类型不符 | 任意内容的 `.exe`（或 `.zip`）文件，不需要真的是可执行文件 |
   | `big.md` | 大小超限 | 大于 50 MiB 的 `.md`。PowerShell：`[IO.File]::WriteAllBytes("$PWD\big.md", (New-Object byte[] 52428801))`；Git Bash：`dd if=/dev/zero of=big.md bs=1M count=51` |
   | 额外 | 404 用例 | 不需要文件，用全零 UUID `00000000-0000-4000-8000-000000000000` |

### 3.2 方案 B：复用自动化环境的靶子数据

本次自动化使用的后端仍在 `http://127.0.0.1:8123`、前端在 `http://127.0.0.1:5174`（数据文件 `%TEMP%\m1run\app.db`）。若要复用，直接访问这两个地址即可；靶子数据如下（均为实测值）：

| 对象 | ID / 标识 | 当前状态（实测） |
| --- | --- | --- |
| 项目 | `13aa36f1-a9b4-4bae-8270-f7b913147bae`（编号 `PRJ-2026-001`，名称「AI 研发平台基础工程」） | `active` |
| 任务 | `aa6ece90-f7bf-4f3f-a257-8fcbb38828b2`（「搭建项目骨架」） | `in_progress`，可启动审批 |
| **保留靶子运行** | `798e9e90-db16-4856-a95f-5824a94bc176` | `waiting_approval`、第 1 轮、停在 `human_approval`、审批记录 0 条 |
| 该运行待审产物 | `e0871552-bc58-49e8-af90-805b81fe2d1d` | 版本 1，`review_status = pending` |
| 审批队列 | `GET /api/v1/workflows?status=waiting_approval` | `total = 1`，就是上面这条运行 |
| 集成验收项目 | `86815b0f-0341-45ca-8733-6a62a2a46745`（编号 `INT493415`） | 3 个任务、3 次运行全部 `completed`，8 个产物、4 条审批记录，可作为「已闭环样例」查看，**不要在上面重复验收** |

> 若选择方案 B，请勿改动 `798e9e90…` 这条运行以外的既有靶子；它是 M4 报告与最终报告引用的复现样本。提交它的审批决定同样可以，只是下一次复现需重新造数。

### 3.3 数据准备完成的判定

| 检查 | 操作 | 预期 |
| --- | --- | --- |
| 项目已建 | `/projects` 搜索项目编号 | 表格仅 1 行，任务数列 = 已建任务数 |
| 任务已建 | 项目详情 → 任务列表 | 两个任务都在，状态 `pending`/`in_progress` |
| 队列可见 | `/approvals` | 至少 1 行（或明确显示空态文案），标题右侧「共 N 项等待决定」与行数一致 |

---

## 4. 场景一：M2 项目管理与项目详情（对应流程 A）

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 1.1 | 打开 `/projects` | 页面出现搜索条与项目表格；首次加载有骨架/loading，不出现「加载中」永久停留 | 一直 loading、空白、或出现英文错误 |
| 1.2 | 点「新建项目」，四项都留空后提交 | 表单就地标红必填提示，**不发出** `POST /projects`（可在 DevTools Network 确认） | 发出请求、或提示语为英文 |
| 1.3 | 项目编号填 `DEMO2026`，其余必填项按要求填完，提交 | 绿色 toast 提示创建成功，列表自动刷新且新项目出现在结果中；`POST /projects` 只发出 **1 次** | 出现两条 `POST /projects`（重复提交）、或创建成功但列表仍看不到新项目 |
| 1.4 | 搜索条输入项目编号 | 停止输入约 300 ms 后自动过滤，只剩该项目一行；无需点「搜索」按钮 | 需要手动刷新、或过滤结果为空 |
| 1.5 | 点项目名称进入详情 | 面包屑「项目管理 / 项目详情」，左侧「项目管理」菜单保持高亮；页面有基本信息、任务列表、工作流概览三块 | 页面空白、面包屑缺失、菜单高亮丢失 |
| 1.6 | 按 F5 刷新 | URL 不变，基本信息与任务列表由后端重新加载（Network 里能看到 `GET /projects/{id}` 与 `GET /tasks?project_id=…`） | 刷新后回到列表页、或数据丢失且无错误提示 |
| 1.7 | 在详情「任务列表」点「新建任务」，填名称与描述提交 | toast 成功；任务列表出现新任务，「工作流」列显示「未启动」；卡片标题「共 N 个任务」的 N 同步 +1；回到 `/projects` 后该项目的「任务数」列也是同一个值 | 任务出现但计数不更新（说明只改了内存状态）、或列表页「任务数」与实际不符 |
| 1.8 | 点任务进入 `/tasks/{id}`，再点「编辑任务」，改任务名称与负责人后保存，刷新 | 标题显示新名称，详情页负责人为新值；`PUT /tasks/{id}` 只发 1 次；刷新后仍是新值 | 刷新后回显旧值（说明只改了 Pinia）、或保存后页面不更新 |
| 1.9 | 把项目编号改成已存在的值并提交 | 后端 409 冲突，页面显示中文冲突提示与 `request_id`，对话框不关闭、数据不被覆盖 | 提示消失且项目被覆盖、或显示英文/无提示 |

---

## 5. 场景二：M3 任务详情与 PRD 文件（流程 B 前半）

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 2.1 | 打开任务详情 | 显示任务基本信息、产物/文件区、上传入口与提示文案（说明允许类型与 50 MiB 上限） | 页面结构缺失、上传入口不可用 |
| 2.2 | 选择 `prd.md` 上传 | 出现上传进度条，随后绿色 toast「上传成功」；`POST /tasks/{id}/artifacts` 发 1 次；文件列表新增一行，版本 = 1，评审状态 = `pending` | 无进度反馈、按钮长期 loading、或列表未刷新 |
| 2.3 | 刷新页面 | 刚上传的文件仍在列表中，版本仍为 1 | 刷新后文件消失（说明只存了前端状态） |
| 2.4 | 再上传同一个 `prd.md` | 生成 **版本 2**，旧版本状态变为 `superseded`；历史记录不被删除（列表能看到两行或能查到旧版本） | 版本仍为 1（被覆盖）、或旧版本消失 |
| 2.5 | 点「下载」，用文本编辑器打开下载的文件 | 下载文件名与上传文件一致；内容与本地 `prd.md` 逐字相同 | 内容不同、下载了空文件、或文件名变成 UUID |
| 2.6 | 在 DevTools Network 检查下载请求 | 响应头有 `x-content-sha256`，其值等于本地文件的 SHA-256；`content-disposition` 带原始文件名 | 校验值与本地内容不一致 |
| 2.7 | 选择 `bad.exe` 上传 | 前端直接给出中文错误提示（类型不允许），**不发出** 上传请求 | 发出了 `POST` 请求、或静默失败 |
| 2.8 | 选择 `big.md`（>50 MiB）上传 | 前端按大小上限拦截并给出中文提示，不发出上传请求 | 请求发出并卡住、或浏览器崩溃 |

---

## 6. 场景三：M3 启动工作流与监控页（流程 B 后半）

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 3.1 | 任务详情点「启动工作流」 | 打开确认对话框，说明这是**模拟**流程；`POST` 请求在确认后才发出 | 未确认就启动、或对话框无「模拟」字样 |
| 3.2 | 确认启动 | 后端同步推进到第一个审批，页面提示启动成功并给出运行入口；工作流状态为 `waiting_approval`，当前节点「人工审批」 | 状态停在 `running` 不动、或报「启动失败」但实际已创建运行 |
| 3.3 | 双击 / 连续点「启动工作流」按钮 | 只发出 **1 次**启动请求；若已存在进行中的运行，返回 409 并提示「该任务已有进行中的工作流」，同时给出已有运行的链接、按钮禁用 | 产生两条运行记录；或按钮可无限点击且无冲突提示 |
| 3.4 | 进入 `/workflows/{id}` 监控页 | 显示节点路径：加载任务 → 生成模拟产物 → 校验产物 → 人工审批 → 完成；前四个节点状态符合当前进度（第 4 个为等待中），并显示轮询提示「每 4 秒自动刷新」 | 节点顺序错乱、状态与后端不一致 |
| 3.5 | 查看事件列表 | 表格按时间先后列出事件（每条含步骤、事件、消息、时间）；卡片显示「共 N 条 · 按时间先后排列」 | 列表为空但后端确有事件、或顺序倒置 |
| 3.6 | 页面停留 10 秒观察 | 每 4 秒自动刷新一次，状态与节点随之更新；页面顶部显示「更新于 …」时间 | 完全不刷新、或每次刷新都闪一次整页 loading |
| 3.7 | 刷新监控页 | 仍停留在同一运行，状态从后端恢复，节点与事件重新加载 | 跳到列表页、或状态被重置为初始值 |
| 3.8 | 打开 `/workflows` 列表页 | 列出运行，含项目/任务关联列与状态标签；标题右侧显示「共 N 次运行」且与实际条数一致；点行可进详情 | 计数与行数不符、或点击无效 |
| 3.9 | 在任务详情确认产物区 | 上传的 PRD（需求阶段）与工作流生成的模拟产物（研发阶段）**共存**，互不覆盖 | 启动工作流后 PRD 消失 |

---

## 7. 场景四：M4 审批一轮通过（流程 C）

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 4.1 | 打开 `/approvals` | 队列列出「等待人工决定」的运行；每行能看出项目、任务、当前轮次、待审产物名称与版本、等待时长；顶部「共 N 项等待决定」= 行数；提示「每 5 秒自动刷新 · 更新于 …」 | 队列里出现已完成/已失败的运行；计数与实际不符 |
| 4.2 | 按项目筛选（URL 带 `?project_id=…`） | 只显示该项目的待审批运行；刷新页面后筛选条件保留 | 筛选无效、或刷新后筛选丢失 |
| 4.3 | 点某行进入 `/approvals/{workflow_id}` | 显示待审产物 Markdown 预览（标题、列表正常渲染）、当前轮次、驳回/通过两个操作，以及审批历史卡片 | 预览只显示原始 Markdown 文本、或历史卡片报错 |
| 4.4 | 点「通过」但审批人留空 | 表单内联提示「请填写审批人」，不发请求 | 请求发出并 422 |
| 4.5 | 填审批人名、意见可留空，提交 | 二次确认框显示将提交的决定；确认后 `POST /workflows/{id}/resume` 只发 **1 次**；页面提示成功 | 无二次确认；或发出多次请求 |
| 4.6 | 成功后观察页面 | 工作流进入终态 `completed`，节点路径全部「已完成」，审批历史出现第 1 条（`approved`、审批人、意见、时间） | 仍显示 `waiting_approval`；或历史为空 |
| 4.7 | 刷新审批详情页 | 仍是终态只读视图，历史保留 | 刷新后又变成可提交状态 |
| 4.8 | 回 `/approvals` 队列 | 该运行已从队列消失（5 秒内自动刷新或手动刷新后），队列计数减少 | 队列仍显示该运行（说明队列不是来自 `GET /workflows?status=waiting_approval`） |
| 4.9 | 检查关联任务 | 任务详情的工作流状态为「已完成」，任务本身状态与后端一致（模拟流程走完会置为 `completed`）；工作流监控页显示的状态与 `GET /workflows/{id}` 完全一致 | 页面显示的状态比后端「更新」或「更旧」 |
| 4.10 | 查看 `/workflows/{id}` 的审批区 | 同一第 1 条记录出现在工作流详情的审批历史里 | 两处历史不一致 |

> 关于审批人身份：平台**没有登录与鉴权**，「审批人」是操作者自报的姓名，仅用于审计留痕。验收时请把它当作填写项，而不是身份认证结果（见最终报告 G-4）。

---

## 8. 场景五：M4 驳回 → 第二轮 → 通过（流程 D）

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 5.1 | 在任务二上重复 1.7→3.2，使运行进入 `waiting_approval` | 队列出现该运行 | 无法进入等待审批 |
| 5.2 | 进审批详情，点「驳回」，理由留空提交 | 内联提示「驳回必须填写理由，下一轮生成依赖这段说明。」，**不发请求** | 空理由被提交成功 |
| 5.3 | 填写驳回理由（例如「需求描述里缺少验收标准，请补充」）并提交 | `POST /workflows/{id}/resume` 发 1 次，`decision = rejected`；页面提示驳回成功 | 提交后无反馈、或发出多次请求 |
| 5.4 | 观察驳回后的状态 | 运行回到 `running`/推进到下一轮审批，轮次变为 **2**；审批历史记录第 1 条为 `rejected` | 轮次仍为 1；或历史显示 `approved` |
| 5.5 | 查看第 2 轮产物 | 产物路径含 `iteration-2/`，版本递增；产物内容里能看到上一轮的**驳回理由被带入**（`revision_comments` 出现在生成内容或上下文中） | 第 2 轮产物与第 1 轮内容完全相同（说明理由未传递） |
| 5.6 | 队列核对 | 第 2 轮的待审请求出现在队列里，轮次列显示 2 | 队列显示的是第 1 轮 |
| 5.7 | 第 2 轮点「通过」 | 历史变成两条：`[1 rejected, 2 approved]`；工作流进入 `completed`；任务状态变为已完成 | 只有一条历史（说明记录被覆盖而非追加） |
| 5.8 | 核对审批记录只追加 | 用接口 `GET /workflows/{id}` 看 `approvals` 数组：两条记录 `sequence` 分别为 1、2，第 1 条内容未被改写；数据库 `approval_records` 无 `updated_at` 字段（设计上不可改） | 第 1 条记录内容被第二次决定覆盖 |

---

## 9. 场景六：异常与防护（流程 E）

| # | 用例 | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- | --- |
| E1 | 项目不存在 | 访问 `/projects/00000000-0000-4000-8000-000000000000` | 错误态（非空白），显示后端中文「未找到」提示与 `request_id`，有返回入口 | 页面一直 loading、或白屏、或只有英文 |
| E2 | 任务不存在 | 访问 `/tasks/00000000-…0000` | 同上 | 同上 |
| E3 | 工作流不存在 | 访问 `/workflows/00000000-…0000` | 同上 | 同上 |
| E4 | 审批对象不存在 | 访问 `/approvals/00000000-…0000` | 同上 | 同上 |
| E5 | ID 格式非法 | 访问 `/tasks/not-a-uuid` | 显示参数错误提示，不出现未捕获异常（控制台不应有红色报错堆栈） | 白屏或控制台抛错 |
| E6 | 上传失败 | 见第 13 章已知项：可用 DevTools「Network → Request blocking」阻断 `**/tasks/*/artifacts` 模拟服务端 5xx；或用类型/大小校验触发前端拦截 | 失败有明确提示、按钮解除 loading、文件列表**不出现新版本**（不留脏数据） | 列表出现一条永远 pending 的版本；或按钮永久转圈 |
| E7 | 下载失败 | 阻断 `**/artifacts/*/download**` 后点下载 | 有失败 toast，按钮恢复可用，页面不卡死 | 下载了 0 字节文件、或按钮一直 loading |
| E8 | 重复启动 | 已有进行中运行时再次点启动 | 后端 409，提示「该任务已有进行中的工作流」并链接到已有运行，按钮禁用 | 创建出第二条运行 |
| E9 | 已结束工作流重复审批 | 打开一条已完成运行的审批页并尝试提交 | 页面为只读；若强行提交，后端 409 提示「工作流已结束，无法继续」，不产生新审批记录 | 产生第三条审批记录、或状态回退 |
| E10 | 连点提交 | 在决定确认框里快速点两次「确认」 | 只发出 **1 次** `resume` 请求；即使网络慢，第二次点击被禁用/忽略 | 两次 `POST`；或产生 `sequence` 重复的记录 |
| E11 | 断网 | 停掉后端进程（Ctrl+C），等待页面自动刷新触发 | 队列/监控页显示错误态与中文提示「网络连接失败，无法访问后端服务，请检查网络或后端是否已启动」，页面框架不崩 | 页面白屏、或提示消失后仍显示旧数据且无任何标记 |
| E12 | 网络恢复 | 重启后端，回到错误页 | 点「重试」或刷新即恢复，数据重新加载；恢复后队列/状态与后端一致 | 必须重开页面才能恢复 |
| E13 | 后端 500 | 见第 13 章已知项；如需真实复现，可临时把 `VITE_DEV_API_PROXY_TARGET` 指向一个只返回 500 JSON 信封的假服务 | 显示「服务内部错误：…（request_id: …）」，页面不崩 | 白屏、或提示里没有 `request_id` |
| E14 | 自动轮询撞上失败 | 断网期间停留 10 秒以上 | 轮询失败时页面给出「自动刷新失败，列表可能不是最新：…」的警告条，且不覆盖已有数据 | 静默失败、用户以为数据是最新的 |

---

## 10. 场景七：布局、导航与刷新恢复

| # | 操作 | 预期结果 | 失败判定 |
| --- | --- | --- | --- |
| 7.1 | 窗口设为 **1440×900**（DevTools 设备仿真） | 依次打开 `/projects`、`/approvals`、`/approvals/{id}`、`/workflows`、`/workflows/{id}`、`/tasks/{id}`；每页 `document.documentElement.scrollWidth === clientWidth`（无横向滚动条），表格列可横向内部滚动而非整页滚动 | 出现整页横向滚动条、按钮被裁掉 |
| 7.2 | 窗口设为 **1680×1000** | 同上，卡片间距正常，无大面积空白 | 内容只占半屏或元素重叠 |
| 7.3 | 一级导航 | 只有项目管理 / 任务管理 / 工作流监控 / 人工审批四个业务入口（首页与工作台为脚手架遗留，不属于本模块） | 出现重复或无效入口 |
| 7.4 | 详情页刷新 | 面包屑、菜单高亮、URL 均保持；数据重新从后端加载 | 刷新后跳到首页 |
| 7.5 | 列表页刷新 | 搜索关键字、页码、筛选（如队列的 `project_id`）从 URL 恢复 | 刷新后回到第 1 页且筛选丢失 |
| 7.6 | 访问未知路由 `/not-exist-page` | NotFound 页面，中文提示与返回按钮 | 空白页 |

---

## 11. 场景八：数据一致性抽查

### 11.1 接口口径（无需读数据库）

对场景四或场景五刚跑完的一条运行 `<run_id>` 依次执行（浏览器或 `curl` 均可）：

| 检查 | 命令 | 预期 |
| --- | --- | --- |
| 运行 ↔ 任务 | `GET /api/v1/workflows/<run_id>` | `task_id` 就是发起启动的那个任务 |
| 任务 ↔ 项目 | `GET /api/v1/tasks/<task_id>` | `project_id` 就是场景一创建的项目 |
| thread 约定 | 同上 11.1 第 1 行响应 | `thread_id == "wf-" + id` |
| 运行 → 产物 | `GET /api/v1/tasks/<task_id>/artifacts?page=1&page_size=50` | 模拟产物行的 `workflow_instance_id == <run_id>`，且 `project_id`/`task_id` 与运行一致 |
| 运行 → 审批 | `GET /api/v1/workflows/<run_id>` 的 `approvals` 数组 | `sequence` 从 1 连续递增，无重复、无缺口；条数 = 提交决定的次数 |
| 队列口径 | `GET /api/v1/workflows?status=waiting_approval&page=1&page_size=50` | 已通过/已驳回并完成流程的运行**不在**其中；只有 `waiting_approval` |
| 页面 vs 后端 | 对比 `/workflows/<run_id>` 显示的状态与上述响应 | 完全一致 |

### 11.2 SQL 口径（SQLite，PostgreSQL 去掉 `lower()`/`replace()` 即可）

> 说明：SQLite 里 UUID 主键存成 32 位无短横线的小写十六进制，而 `thread_id` 是带短横线的文本，所以比较前先去掉短横线。

```sql
-- 1) thread_id 是否等于 wf-<运行 id>（应为 total 与 ok 相同）
select count(*) as total,
       sum(case when lower(replace(replace(thread_id,'wf-',''),'-','')) = lower(id) then 1 else 0 end) as ok
from workflow_instances;

-- 2) 产物归属是否与所属运行一致（应为 0 行）
select a.id
from artifacts a
join workflow_instances w on lower(w.id) = lower(a.workflow_instance_id)
where a.workflow_instance_id is not null
  and (lower(a.task_id) <> lower(w.task_id) or lower(a.project_id) <> lower(w.project_id));

-- 3) 审批记录是否都能找到对应运行（应为 0 行）
select r.id
from approval_records r
left join workflow_instances w on lower(w.id) = lower(r.target_id)
where r.target_type = 'workflow_instance' and w.id is null;

-- 4) 审批顺序是否连续且不重复（每个运行一行，min=1、cnt=distinct）
select target_id, count(*) as cnt, min(sequence) as mn, max(sequence) as mx, count(distinct sequence) as dc
from approval_records
where target_type = 'workflow_instance'
group by target_id
having mn <> 1 or cnt <> dc or cnt <> (mx - mn + 1);

-- 5) 终态运行是否仍留在队列口径里（后端查询应为 0 行；对应接口 status=waiting_approval）
select id, status from workflow_instances
where status in ('completed','failed','cancelled') and status = 'waiting_approval';
```

**本指南编写时在自动化验收库上实测结果**：查询 1 `total=13, ok=13`；查询 2、3、4、5 均返回 0 行。人工环境应得到同样的结论（total 随造数增长，ok 与 total 相等）。

---

## 12. 自动化证据对照表

自动化两轮共 52 个步骤，截图在 [`docs/images/task5-integration/`](./images/task5-integration/)（30 张）。人工执行遇到疑问时，可先查对应截图：

| 本指南场景 | 自动化步骤编号 | 截图 |
| --- | --- | --- |
| 场景一（创建/编辑/刷新） | a1、a2、a3、a4、a5、a6 | `a1-project-form.png`、`a2-project-detail.png`、`a6-task-edited.png` |
| 场景二（PRD 上传/版本/下载） | b1、b2、b3 | `b1-prd-uploaded.png`、`b3-prd-downloaded.png` |
| 场景三（启动/监控/刷新） | b4、b5、x1、x2、x3 | `b4-start-dialog.png`、`b5-workflow-detail.png`、`x1-project-task-list.png`、`x2-workflow-nodes-events.png`、`x3d-prd-and-result.png` |
| 场景四（一轮通过） | c1、c2、c3、c4、x6 | `c2-approval-detail.png`、`c3-approve-confirm.png`、`c4-approved.png`、`x6c-queue-after-approve.png` |
| 场景五（驳回二轮） | d1–d5 | `d2-reject-reason-required.png`、`d3-reject-confirm.png`、`d4-after-reject.png`、`d5-round2-approved.png` |
| 场景六（异常防护） | e1–e9、x4、x5 | `e1-upload-bad-type.png`、`e2-upload-too-large.png`、`e3-duplicate-start.png`、`e4-not-found.png`、`e5-queue-offline.png`、`e7-server-error-500.png`、`e9-decided-twice.png`、`x4a-download-500.png`、`x5-upload-500.png` |
| 场景七（布局与恢复） | f1–f5 | `f3-queue-1440.png`、`f4-detail-1440.png`、`f5-monitoring-1680.png` |
| 场景八（数据一致性） | f2、f6、x7 | 无截图（接口与 SQL 断言，见最终报告 E.7） |

---

## 13. 已知项：不要按缺陷上报

| 编号 | 现象 | 为什么不是缺陷 | 对应遗留项 |
| --- | --- | --- | --- |
| K-1 | 工作流监控页没有「暂停/继续」按钮可点 | 后端当前没有暂停端点，`resume` 只服务于审批与检查点续跑；UI 因此不暴露无效操作 | G-1、G-3 |
| K-2 | PDF / docx / 图片产物在线预览只显示下载入口 | 只有 Markdown 走前端渲染分支，其他类型按下载处理 | G-13 |
| K-3 | 队列超过 1 页时，自动刷新只保证当前页 | 队列分页 + 轮询的组合未做跨页保持 | G-14 |
| K-4 | 审批详情页不轮询：他人已提交决定时，本页要下一次操作才提示已过期（409） | 设计上详情页不做轮询，用 409 兜住，避免覆盖只追加的历史 | G-15 |
| K-5 | 下载失败时 toast 只有「请求失败：服务返回了异常状态 500」，不含后端 `message` 与 `request_id` | blob 响应分支未解析 JSON 错误体（自动化实测现象，已记为技术债） | G-5 |
| K-6 | 队列进入错误态时，顶部「共 0 项等待决定」与错误态并存 | 错误态下计数被重置为 0，未保留上次数值 | G-6 |
| K-7 | 「审批人」是手填姓名，任何浏览器都能提交 | 平台无登录无鉴权（任务 5 明确不做身份体系） | G-4 |
| K-8 | 产物内容是「# 模拟研发产物 …」模板文 | 工作流为模拟实现，未接任何大模型 | G-2 |
| K-9 | 需要真实 500 时，正常操作很难触发 | 自动化用 CDP 拦截伪造响应体验证了错误渲染；人工可用第 9 章 E6/E13 的替代手法 | — |

---

## 14. 验收记录表（复制填写）

| 场景 | 步骤区间 | 结论（通过/缺陷/已知项） | 备注 |
| --- | --- | --- | --- |
| 一 M2 项目 | 1.1–1.9 | | |
| 二 M3 任务与 PRD | 2.1–2.8 | | |
| 三 M3 启动与监控 | 3.1–3.9 | | |
| 四 M4 一轮通过 | 4.1–4.10 | | |
| 五 M4 驳回二轮 | 5.1–5.8 | | |
| 六 异常防护 | E1–E14 | | |
| 七 布局与恢复 | 7.1–7.6 | | |
| 八 数据一致性 | 11.1–11.2 | | |

回归命令（验收前后各跑一次，全部应与下列结果一致）：

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .   # 预期：All checks passed!
.\.venv\Scripts\python.exe -m pytest -q      # 预期：95 passed, 1 warning

cd ..\frontend
npm run type-check                            # 预期：退出码 0，无输出错误
npm run build                                 # 预期：✓ built in …s，退出码 0
```

> 前端构建会提示主 JS 产物超过 500 kB（当前约 0.5 MB gzip 前），这是 G-17 记录的技术债，不算失败。

---

## 15. 缺陷提交模板

```text
标题：[任务5][场景四 4.6] 审批通过后队列未移除该运行
环境：后端 127.0.0.1:8000（SQLite）/ 前端 localhost:5173 / Edge 157 / 1680×1000
复现步骤：
  1) …
  2) …
  3) …
预期结果：（引用本指南对应行的「预期结果」原文）
实际结果：（页面文案、状态值）
证据：
  - request_id：……
  - GET /api/v1/workflows/<id> 响应片段：……
  - 截图：……
  - 浏览器控制台报错：……
是否命中第 13 章已知项：否 / 是（K-x）
```

`request_id` 从哪里找：错误提示文案括号里、或 DevTools Network 中失败响应的 `x-request-id` 头；把它交给后端同学即可在服务日志里定位同一次请求。
