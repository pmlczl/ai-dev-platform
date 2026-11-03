# 第一阶段基础工程验收报告（Iteration 1 Acceptance Report）

- 项目路径：`D:\project\ai-dev-platform`
- 验收日期：2026-11-03
- 验收方式：实际执行命令 + 真实服务进程 + 真实浏览器会话
- 验收范围：工程结构、后端独立运行、前端独立运行、数据库、Docker Compose、前后端联合
- 本次变更：**未修改任何项目文件**（仅新增本报告）。所有修复建议均待确认后再执行。

---

## 0. 结论速览

| 维度 | 通过 | 失败 | 未执行 |
| --- | --- | --- | --- |
| 工程结构检查 | 6 | 1 | 0 |
| 后端独立运行检查 | 10 | 2 | 0 |
| 前端独立运行检查 | 9 | 0 | 1 |
| 数据库检查 | 3 | 0 | 3 |
| Docker Compose 检查 | 1（静态） | 0 | 4 |
| 前后端联合检查 | 3 | 0 | 1 |
| **合计** | **32** | **3** | **9** |

**总体判定：有条件通过。**

基础工程的骨架、配置加载、迁移链路、API 契约、前端构建与运行均已实测通过，具备进入第二阶段的功能开发条件。但存在 **2 个 P0 级缺陷**（根目录 `.env` 不被后端读取；500 响应丢失 `request_id` 与 `X-Request-ID` 响应头），且 **Docker Compose 与真实 PostgreSQL 全链路未能在本机实测**（环境不具备，非代码问题），因此不能判定为「完全达标」。修复 2 个 P0 并补做 Compose 实测后即可判定达标。

---

## 1. 验收环境与能力边界（前置说明）

本节先说明哪些测试在本机能真实执行、哪些不能，避免后文出现「未执行却标为通过」。

### 1.1 实测到的环境能力

| 组件 | 实测结果 | 依据 |
| --- | --- | --- |
| Python | 3.13.14（venv：`backend/.venv`） | `python --version` |
| Node.js / npm | v24.20.0 / 11.19.0 | `node --version`、`npm --version` |
| winget | 1.29.380 | `winget --version` |
| WSL | Ubuntu-22.04，默认版本 2 | `wsl --status` |
| Docker CLI | **未安装** | `docker version` → `command not found`；`C:\Program Files\Docker` 不存在；`sc query com.docker.service` → 1060（服务未安装） |
| PostgreSQL | **未安装** | `C:\Program Files\PostgreSQL` 不存在；`where psql` 无结果 |

### 1.2 因此产生的三项「未执行」

| 编号 | 未执行内容 | 原因 | 替代验证方式 |
| --- | --- | --- | --- |
| N1 | `docker compose config` / `up -d --build` / `ps` / `logs` | 本机无 Docker CLI / Docker Desktop。尝试 `winget install -e --id Docker.DockerDesktop` 被运行环境安全策略拦截（安装外部厂商安装包需本轮显式授权）。 | 以 YAML 解析 + 静态审查替代（见第 6 节），**不计入「通过」** |
| N2 | PostgreSQL 服务启动、真实连接、`SELECT 1`（PostgreSQL 方言） | 本机无 PostgreSQL 实例，且无法通过 Docker 拉起 | 用 SQLite 走**同一套** SQLAlchemy 引擎与连接池代码路径做替身冒烟（见第 5 节），**替身结果不计入 PostgreSQL 项** |
| N3 | 前后端镜像构建与容器内运行 | 依赖 N1 | 用 `pip wheel` 验证后端打包（等价于镜像内 `pip install .`），前端仅静态审查 |

### 1.3 本轮实际拉起的进程

| 服务 | 端口 | 启动方式 | 当前状态 |
| --- | --- | --- | --- |
| FastAPI（默认 PostgreSQL DSN） | 127.0.0.1:8000 | `python -m uvicorn app.main:app` | 运行中 |
| FastAPI（SQLite 替身 DSN） | 127.0.0.1:8011 | 同上 + `DATABASE_URL=sqlite+aiosqlite:///...` | 验收后已停止，临时库已删除 |
| Vite 开发服务器 | 5173 | `npm run dev` | 运行中 |
| Vite 预览服务器（生产产物） | 4173 | `npm run preview` | 运行中 |

---

## 2. 工程结构检查

### 2.1 实际目录结构（排除 .git / node_modules / .venv / __pycache__ / dist）

```
ai-dev-platform/
├── .env.example
├── .gitignore
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── docs/
│   ├── iteration1_code_review.md          # 上一轮静态代码检查报告
│   └── iteration1_acceptance_report.md    # 本报告
├── backend/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/0001_baseline.py
│   ├── app/
│   │   ├── main.py
│   │   ├── api/{__init__,deps}.py
│   │   ├── api/v1/{__init__,router}.py
│   │   ├── api/v1/endpoints/{__init__,health}.py
│   │   ├── core/{__init__,config,context,database,exceptions,logging,middleware}.py
│   │   ├── models/{__init__,base}.py
│   │   ├── schemas/{__init__,health}.py
│   │   ├── services/__init__.py
│   │   ├── workflows/{__init__,base,langgraph_runtime,registry}.py
│   │   └── agents/__init__.py
│   ├── tests/{conftest,test_exceptions,test_health,test_readiness}.py
│   ├── ai_dev_platform_backend.egg-info/   # 构建残留（已被 .gitignore 覆盖）
│   └── build/lib/app/...                    # 构建残留副本（已被 .gitignore 覆盖）
└── frontend/
    ├── .dockerignore
    ├── .env.example
    ├── Dockerfile
    ├── nginx.conf
    ├── index.html
    ├── package.json / package-lock.json
    ├── tsconfig.json / tsconfig.node.json
    ├── vite.config.ts
    └── src/
        ├── App.vue / main.ts / env.d.ts
        ├── api/{client,health,index}.ts
        ├── components/layout/{AppHeader,AppSidebar,index}.{vue,ts}
        ├── router/index.ts
        ├── stores/{app,index}.ts
        ├── styles/index.css
        └── views/{HomeView,WorkbenchView,NotFoundView}.vue
```

### 2.2 逐项检查结果

| # | 检查项 | 状态 | 结论 |
| --- | --- | --- | --- |
| S1 | 后端六大目录 `api/core/models/schemas/services/workflows/agents` | **通过** | 全部存在且职责清晰，`agents/` 仅有占位 docstring，无任何 Agent 实现 |
| S2 | 前端五大目录 `api/components/views/router/stores` | **通过** | 全部存在；`components/layout/` 具名组件按目录组织 |
| S3 | 根级配置与文档（`docker-compose.yml`/`.env.example`/`.gitignore`/`README.md`/`AGENTS.md`） | **通过** | 五项齐全且内容真实可用，非占位空文件 |
| S4 | Docker 资产（前后端 `Dockerfile` + `nginx.conf` + `.dockerignore`） | **通过** | 文件齐全；内容静态审查合理，构建实测见 N3 |
| S5 | 测试目录 | **通过** | `backend/tests/` 4 个文件、11 条用例；**前端无任何单元测试/无 Vitest 配置** |
| S6 | `docs/` 目录 | **通过** | 已存在，存放本轮与上一轮检查报告 |
| S7 | `storage/`、`scripts/` 目录 | **失败** | 缺失。第一阶段当前无文件上传/产物落盘与运维脚本需求，**属可接受缺口**，但第二阶段引入产物存储前必须补建 |
| S8 | 工作区洁净度 | **失败** | `backend/build/lib/app/**` 是 `app/` 的**陈旧完整副本**（上轮 `pip install` 产物）。虽被 `.gitignore` 的 `build/` 覆盖，但存在「改错目录、代码不生效」的实质风险 |
| S9 | Git 仓库状态 | **失败** | `git log` 报 `your current branch 'master' does not have any commits yet`，全部文件处于 untracked 状态，工程**尚未有任何版本记录** |

---

## 3. 后端独立运行检查

### 3.1 实际执行的命令与结果

| # | 命令 | 结果 | 状态 |
| --- | --- | --- | --- |
| B1 | `python -m pip check` | `No broken requirements found.` | 通过 |
| B2 | `python -m ruff check .` | `All checks passed!` | 通过 |
| B3 | `python -m pytest -q` | `11 passed in 0.15s` | 通过 |
| B4 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | `Application startup complete.` / `Uvicorn running on http://127.0.0.1:8000` | 通过 |
| B5 | `curl -i http://127.0.0.1:8000/api/v1/health` | `HTTP/1.1 200 OK`，响应头含 `x-request-id: 327af7d6...`，体含 `status/app/version/environment/timestamp` | 通过 |
| B6 | `curl -i http://127.0.0.1:8000/api/v1/health/ready`（无 PostgreSQL） | `HTTP/1.1 503 Service Unavailable`，体 `{"status":"not_ready","database":{"status":"unavailable","latency_ms":null}}` | 通过（降级语义正确） |
| B7 | `curl /docs`、`/redoc`、`/openapi.json` | 分别 `200`（1014 B / 896 B / 2218 B） | 通过 |
| B8 | `curl http://127.0.0.1:8000/` | `{"name":"AI Dev Platform","version":"0.1.0","docs":"/docs"}` | 通过 |
| B9 | 17 个 `app.*` 模块逐个 `importlib.import_module` | `RESULT: ALL OK`（17/17） | 通过 |
| B10 | `python -m alembic upgrade head` → `current` → `history` → `downgrade base` → `upgrade head` | `Running upgrade -> 0001_baseline` / `0001_baseline (head)` / `<base> -> 0001_baseline (head)` / `Running downgrade` / 再次 upgrade 成功 | 通过 |
| B11 | `python -m alembic check` | `No new upgrade operations detected.`（模型与迁移无漂移） | 通过 |
| B12 | `python -m alembic upgrade head --sql`（README 记录的离线渲染） | 正确输出 PostgreSQL 方言 DDL（`CREATE TABLE alembic_version ...`） | 通过 |
| B13 | `python -m pip wheel . --no-deps`（等价镜像内 `pip install .`） | `Successfully built ai-dev-platform-backend`，wheel 17,302 B / 29 个条目，含 `app/main.py`、`app/core/config.py`、`app/workflows/`、`app/agents/`、`app/api/`、`app/schemas/` | 通过 |
| B14 | `ruff format --check .`（附加项） | `1 file would be reformatted, 30 files already formatted` | 提示（非阻断，AGENTS.md 仅要求 `ruff check`） |
| **B15** | **`.env` 加载路径实测**（见 3.2） | **根目录 `.env` 不生效** | **失败（P0-1）** |
| **B16** | **500 异常响应实测**（见 3.3） | **`request_id` 为 `"-"`，且无 `X-Request-ID` 响应头** | **失败（P0-2）** |

### 3.2 失败详情 B15（P0-1）：根目录 `.env` 不被后端读取

**实测过程**（在仓库根与 `backend/` 各放一个临时 `.env`，测完立即删除）：

```
# 临时文件：<root>/.env        -> POSTGRES_PASSWORD=root-env-value
#           <root>/backend/.env -> POSTGRES_PASSWORD=backend-env-value

cwd=backend/  ->  postgres_password = 'backend-env-value'
cwd=仓库根    ->  postgres_password = 'backend-env-value'
```

**原因**：`backend/app/core/config.py:23` 的 `env_file=(".env", "backend/.env")` 由 **pydantic-settings 按当前工作目录（CWD）解析**，而非按包位置解析：

- 从 `backend/` 启动（README 第 88 行 `cd backend`）时，`.env` 解析为 `backend/.env`，`backend/.env` 解析为 `backend/backend/.env`（不存在）→ **仓库根的 `.env` 从未被读取**。
- 从仓库根启动时，根 `.env` 会被读取，但随后被 `backend/.env` 覆盖（pydantic-settings 多文件 dotenv 语义：**后者覆盖前者**）。

**影响**：README 第 90 行 `Copy-Item ..\.env.example ..\.env` 把配置复制到**仓库根**，而按 README 方式启动的后端永远读不到它 → 本地开发时 `POSTGRES_PASSWORD` 恒为空 → 连库必然失败；`ENVIRONMENT=production` 时 `settings.runtime_errors()` 也会因缺密码而拒绝启动。用户会误判为「配置已生效」，排查成本高。

**修复建议**（改 `config.py`，用包位置推导绝对路径）：

```python
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]      # backend/
_PROJECT_ROOT = _BACKEND_DIR.parent                      # 仓库根

model_config = SettingsConfigDict(
    env_file=(str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env")),
    ...
)
```

保持「后者覆盖前者」的语义不变（`backend/.env` 仍可覆盖根 `.env`），但两种启动目录下根 `.env` 都能生效。同理建议 `alembic/env.py` 的 `script_location` 与 `alembic.ini` 的相对路径改为绝对路径或统一约定在 `backend/` 下执行。

### 3.3 失败详情 B16（P0-2）：500 响应丢失 `request_id` 与 `X-Request-ID`

**实测过程**（在 `create_app()` 返回的应用上临时挂一个抛异常路由，走完整中间件栈）：

```
status_code        : 500
X-Request-ID header: None
body               : {"code":"INTERNAL_SERVER_ERROR","message":"Internal server error",
                     "detail":null,"request_id":"-","timestamp":"2026-11-03T11:24:19.055607+00:00"}
```

日志侧可见请求 ID 本身是正确的（`app.core.middleware | acceptance-probe-001 | GET /__acceptance_boom -> error`），但**错误响应体与响应头丢失了它**。

**原因**：`backend/app/core/middleware.py:33` 在 `finally` 中执行 `request_id_var.reset(token)`，而 Starlette 最外层的 `ServerErrorMiddleware`（位于用户中间件之外）在异常穿透后才调用兜底 handler；此时 contextvar 已被重置，`app/core/exceptions.py` 的 `build_error_payload` 取到默认值 `"-"`。同时 `RequestContextMiddleware` 的 `response.headers[REQUEST_ID_HEADER] = request_id` 位于异常路径之后，永不执行。

**影响**：违反 README 第 160–172 行声明的错误响应契约（`request_id` 必须存在且可用于日志定位），排障时无法用响应体/响应头反查日志；也使 `X-Request-ID` 不再「每个响应都带」。此外现有测试 `test_request_id_header_is_echoed` 只覆盖成功路径，未能拦住该缺陷。

**修复建议**：

1. `build_error_payload` 优先从 `request.scope["state"]["request_id"]` / `request.state.request_id` 取值，contextvar 仅作兜底（`request.state` 由 `scope["state"]` 承载，不随 contextvar 重置而丢失）。
2. 500 的 `JSONResponse` 显式带上 `headers={"X-Request-ID": request_id}`。
3. 补一条测试：故意触发 500，断言响应体 `request_id` 非 `"-"` 且响应头含 `X-Request-ID`。

### 3.4 其他风险提示（非失败）

| # | 现象 | 影响 | 建议 |
| --- | --- | --- | --- |
| W1 | 就绪探针在数据库不可达时耗时 **4,096 ms** 才返回 503（`GET /api/v1/health/ready -> 503 4096.1ms`） | 无连接超时，探针无法快速失败；后端容器 `HEALTHCHECK` 超时 5s，余量很小 | 为 asyncpg 增加 `connect_args={"timeout": 3}`，或用 `asyncio.wait_for` 包裹探针 |
| W2 | `docker-compose.yml:38-39` 的 `migrate` 服务手工拼接未编码的 `DATABASE_URL`，且 `DATABASE_URL` 优先级高于 `POSTGRES_*` | 实测 `make_url('postgresql+asyncpg://postgres:p@ss@db:5432/...')` → `password='p'`、`host='ss@db'`；密码含 `@ : / #` 时 migrate 与 backend 指向**不同 DSN**（backend 走 `quote_plus`，编码为 `p%40ss`） | 删除该行，`migrate` 只用 `POSTGRES_*`；或改为从同一份 `DATABASE_URL` 注入 |
| W3 | `backend/Dockerfile:18` `COPY tests ./tests`，但运行镜像未安装 `pytest` | 镜像内无法跑测试，徒增体积 | 生产镜像不 COPY tests，或加 `dev` 目标 |
| W4 | `python-dotenv` 与 `pydantic-settings` 功能重叠；`langgraph` 作为运行时依赖引入 `langchain-core/langsmith/httpx2` | 镜像体积与依赖面放大 | `python-dotenv` 可移除；`langgraph` 移入 `optional-dependencies.agents` |
| W5 | `backend/app/main.py:69` 注释「CORS 是最外层」不准确（`ServerErrorMiddleware` 仍在更外层） | 注释与实际栈序不符，误导后续维护 | 修正注释 |

---

## 4. 前端独立运行检查

### 4.1 实际执行的命令与结果

| # | 命令 | 结果 | 状态 |
| --- | --- | --- | --- |
| F1 | `npm ls --depth=0` | 12 个直接依赖全部正确解析（`vue@3.5.44`、`element-plus@2.14.7`、`vite@6.4.5` 等），**无 `UNMET DEPENDENCY` / `invalid`** | 通过 |
| F2 | `npm ci --dry-run` | 无 lockfile 不同步错误，仅提示 2 个包有 install scripts 未被 allowScripts 覆盖 | 通过 |
| F3 | `npm run type-check` | `vue-tsc --noEmit` + `tsc --noEmit` 均无输出，退出码 0 | 通过 |
| F4 | `npm run build` | `✓ 1696 modules transformed.` / `✓ built in 6.86s`，退出码 0 | 通过 |
| F5 | `npm run dev` | `VITE v6.4.5 ready in 495 ms` → `http://localhost:5173/` | 通过 |
| F6 | `curl http://127.0.0.1:5173/` | `200`，返回含 `<title>AI Dev Platform</title>` 与 `/src/main.ts` 的 SPA 骨架 | 通过 |
| F7 | 浏览器访问 `http://127.0.0.1:5173/` | 页面标题「首页 · AI Dev Platform」；侧边/顶部导航、面包屑、首页卡片、状态表格全部正确渲染（后端状态=正常、版本=0.1.0、运行环境=development、数据库=-） | 通过 |
| F8 | 浏览器访问 `http://127.0.0.1:5173/workbench` | 页面标题「工作台 · AI Dev Platform」，占位文案与后端版本号正确渲染 | 通过（history 路由生效） |
| F9 | 浏览器控制台检查（刷新后） | 仅 2 条 `[vite] connecting/connected` debug 消息；**0 条 JS 异常、0 条 Vue 警告**；唯一 error 为网络层 `503 /api/v1/health/ready`（数据库未启动所致，属预期） | 通过 |
| F10 | `npm run preview`（生产产物） | `http://localhost:4173/` 返回 200，加载 `assets/index-BwqhR67V.js`；浏览器访问渲染正确、控制台同样仅有预期的 503 | 通过 |
| F11 | 浏览器截图 | **未执行** —— in-app Browser 未提供正尺寸可见视口（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`），已改用结构化快照（take_snapshot）作为等价证据 | 未执行 |

### 4.2 构建产物体量（实测数据）

```
dist/index.html                       0.40 kB │ gzip:   0.28 kB
dist/assets/index-CbWZVfA4.css     362.78 kB │ gzip:  48.57 kB
dist/assets/index-BwqhR67V.js    1,275.43 kB │ gzip: 412.93 kB
dist/assets/HomeView-wf1MB_lc.js     2.85 kB │ gzip:   1.41 kB
dist/assets/WorkbenchView-BFZOLlKA.js 0.77 kB │ gzip:   0.54 kB
```

Vite 给出 `Some chunks are larger than 500 kB after minification` 警告。

**原因**：`frontend/src/main.ts` 全量注册 Element Plus 与全部图标，未做按需引入与路由级分包。

**影响**：首屏 JS gzip 约 413 KB，二次访问前的解析/执行成本偏高；本阶段规模可接受，但第二阶段页面增多后应立即处理。

**修复建议**：改用 `unplugin-vue-components` + `unplugin-auto-import` 按需引入；或对 Element Plus 做手动分块 `manualChunks`；路由视图改 `() => import(...)` 动态导入。

### 4.3 其他风险提示（非失败）

| # | 现象 | 影响 | 建议 |
| --- | --- | --- | --- |
| W6 | 启动 `npm run dev` 时端口 5173 被**上一会话遗留的 dev server 进程**占用，Vite 静默改用 5174（`Port 5173 is in use, trying another one...`） | `vite.config.ts` 未设 `strictPort`，端口被占用时静默漂移，开发者按 README 访问 5173 会打到别的服务或连接失败 | 增加 `strictPort: true`，让端口冲突显式报错；本轮已清理遗留进程，最终以 5173 启动成功 |
| W7 | 首页对 `/api/v1/health` 与 `/api/v1/health/ready` 各发起 **2 次**重复请求（网络面板 reqid=172/174 与 175 各两条） | 无谓的网络开销与后端日志噪声 | 顶部导航与首页各自拉取健康信息，可在 Pinia store 中做一次性缓存 |
| W8 | 前端无 ESLint / Prettier 配置与 `lint` 脚本 | 缺少与后端 Ruff 对等的静态约束 | 第二阶段前补齐 ESLint + `npm run lint` |
| W9 | `frontend/src/api/client.ts:41` 的 `extractErrorMessage` 无任何调用方 | 死代码 | 接入统一错误提示或删除 |

---

## 5. 数据库检查

### 5.1 实际执行结果

| # | 检查项 | 命令 / 方式 | 结果 | 状态 |
| --- | --- | --- | --- | --- |
| D1 | PostgreSQL 是否正常启动 | `ls "C:/Program Files/PostgreSQL"`、`where psql` | 本机无 PostgreSQL 安装 | **未执行** |
| D2 | 数据库是否可以连接（PostgreSQL） | 后端启动日志 + 就绪探针 | `postgresql+asyncpg://postgres:***@localhost:5432/ai_dev_platform` → 连接被拒 | **未执行**（无实例可连） |
| D3 | 后端能否通过 SQLAlchemy 执行 `SELECT 1`（PostgreSQL） | — | 依赖 D2，无法执行 | **未执行** |
| D4 | `SELECT 1`（SQLite 替身，走同一 `app.core.database.engine`） | `DATABASE_URL=sqlite+aiosqlite:///./.acceptance_smoke.db` + `text("SELECT 1")` | `SELECT 1 result: 1` / `RESULT: PASS` | 通过（替身） |
| D5 | 就绪探针在「数据库可达」时 | 同上 DSN 起 uvicorn，`GET /api/v1/health/ready` | `HTTP 200`，`{"status":"ok","database":{"status":"ok","latency_ms":4.89}}` | 通过（替身） |
| D6 | 数据库连接失败时是否有合理错误提示 | `GET /api/v1/health/ready`（无库环境） | 响应：`503` + `{"status":"not_ready","database":{"status":"unavailable"}}`；日志：`WARNING | app.api.v1.endpoints.health | d8e6f8b4... | Database readiness probe failed: [WinError 1225] ...`（含 request_id） | 通过 |

> **D4/D5 是替身验证，不等同于 PostgreSQL 通过。** `sqlite+aiosqlite` 走的是同一份 `app/core/database.py` 的引擎创建、会话工厂与 `get_db()` 依赖链路，仅驱动与方言不同；PostgreSQL 专属行为（asyncpg 驱动、连接池 `pool_size/max_overflow/pool_recycle` 参数、真实事务与 `RETURNING`）仍需在有实例后复测。

### 5.2 关于「数据库就绪检查接口」的补充建议

**该接口已存在，无需新增。** `GET /api/v1/health/ready` 已实现并实测有效：

- 实现位置：`backend/app/api/v1/endpoints/health.py:44-73`
- 契约：数据库可达 → `200 {"status":"ok","database":{"status":"ok","latency_ms":<float>}}`；不可达 → `503 {"status":"not_ready","database":{"status":"unavailable","latency_ms":null}}`
- 已纳入 OpenAPI（`test_health.py::test_health_endpoint_is_documented` 断言 `/api/v1/health/ready` 在 `paths` 中）
- 前端 `frontend/src/api/health.ts` 已封装 `fetchReadiness()`，首页「数据库」卡片已在消费该结果
- `docker-compose.yml` 的 `backend` 健康检查目前指向 `/api/v1/health`（存活），**未**指向 `/api/v1/health/ready`（就绪）

**建议（可选优化，非缺陷）**：为 Compose 增加一个依赖 `db` 健康状态的 `ready` 探针使用点，或在 CI 中把 `/api/v1/health/ready` 作为「数据库连通性」门禁，与 `/api/v1/health` 的「进程存活」语义区分开。同时建议为该接口补一条「延迟阈值」约定（当前只回传实测延迟，未定义阈值，超时即视为不可用）。

### 5.3 迁移链路实测

| 命令 | 结果 |
| --- | --- |
| `alembic upgrade head` | `Running upgrade -> 0001_baseline, Baseline revision of the platform scaffold.` |
| `alembic current` | `0001_baseline (head)` |
| `alembic history` | `<base> -> 0001_baseline (head), Baseline revision of the platform scaffold.` |
| `alembic downgrade base` | `Running downgrade 0001_baseline -> , ...` |
| `alembic upgrade head`（再次） | 成功，说明可重复执行 |
| `alembic check` | `No new upgrade operations detected.`（模型与迁移无漂移） |
| `alembic upgrade head --sql` | 正确渲染 PostgreSQL 方言 DDL |
| 建表结果 | 仅 `alembic_version` 一张表 —— 符合「第一阶段不建业务表」的约束 |

`alembic.ini` 中未保存任何凭据，DSN 全程从环境变量解析，符合 AGENTS.md 约束。

---

## 6. Docker Compose 检查

### 6.1 实际执行结果

| # | 命令 | 结果 | 状态 |
| --- | --- | --- | --- |
| N1 | `docker compose config` | `bash: docker: command not found` | **未执行** |
| N3 | `docker compose up -d --build` | 同上，Docker CLI 不存在 | **未执行** |
| N3 | `docker compose ps` | 同上 | **未执行** |
| N3 | `docker compose logs` | 同上 | **未执行** |
| N3 | `winget install -e --id Docker.DockerDesktop` | 被运行环境安全策略拦截（安装外部厂商安装包需本轮显式授权） | **未执行** |
| C1 | Compose YAML 静态解析（Python `yaml.safe_load`） | 解析成功：`services = ['db','migrate','backend','frontend']`，`volumes = ['postgres_data']` | 通过（静态） |

### 6.2 静态审查发现（**不计入通过，仅为修复提供依据**）

| 项 | 静态结论 | 风险 |
| --- | --- | --- |
| 服务拓扑 | `db` → `migrate`（`service_healthy`）→ `backend`（`service_completed_successfully`）→ `frontend`（`service_healthy`），依赖链完整 | 链路本身合理 |
| 数据库持久化 | `postgres_data` 命名卷挂载至 `/var/lib/postgresql/data`，`db` 配 `pg_isready` 健康检查 | 合理 |
| PostgreSQL 变量 | `POSTGRES_USER/PASSWORD/DB` 均带默认值并可被 `.env` 覆盖 | 合理 |
| **migrate 的 DSN** | 见 W2：手工拼接的 `DATABASE_URL` 未编码且优先级高于 `POSTGRES_*` | **高**：特殊字符密码会导致 migrate 与 backend 指向不同数据库 |
| **backend 的 CORS 默认值** | `docker-compose.yml:57` 为 `http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://127.0.0.1`，与 `config.py:46` 的默认值不同 | 低：容器内前端走 nginx 同源代理，不触发 CORS；但两处默认值漂移易误导 |
| **前端 Dockerfile** | `npm install` 而非 `npm ci` | 中：`package-lock.json` 不参与安装校验，构建不可复现（本轮已用 `npm ci --dry-run` 验证锁文件与 `package.json` 同步，改 `npm ci` 安全） |
| **nginx 配置** | `location /api/` + `proxy_pass http://backend:8000;`（无 URI 部分 → 保留原路径）+ `try_files` SPA 回退 | 静态合理，但 **nginx 容器内实测未执行** |
| Dockerfile 构建 | 后端 `pip install .` 已用 `pip wheel .` 等价验证；前端构建已用 `npm run build` 等价验证 | 但**镜像构建本身未执行** |

---

## 7. 前后端联合检查

| # | 检查项 | 方式 | 结果 | 状态 |
| --- | --- | --- | --- | --- |
| J1 | 浏览器能够访问前端首页 | browser-use MCP 打开 `http://127.0.0.1:5173/` | 渲染完整（标题、导航、面包屑、首页卡片、状态表格） | 通过 |
| J2 | 前端能够请求后端 API | 浏览器网络面板 | `GET http://127.0.0.1:5173/api/v1/health → 200 xhr application/json`，响应体 `{"status":"ok","app":"AI Dev Platform",...}`；页面「后端 正常」 | 通过 |
| J3 | 后端能够连接 PostgreSQL | — | 无 PostgreSQL 实例 | **未执行** |
| J4 | 完整运行环境能够通过 Docker Compose 启动 | — | Docker 不可用 | **未执行** |
| J5 | 生产产物（`npm run preview`）与后端联调 | 浏览器 + curl | `http://127.0.0.1:4173/` 渲染正确；`GET /api/v1/health` 经 preview 代理返回 200 | 通过（等价于 nginx 同源代理路径） |

### 7.1 联调链路说明

实际打通的链路为：

```
浏览器 → Vite dev server (5173) ── proxy /api ──→ FastAPI (8000) ──→ PostgreSQL(未启动)
浏览器 → Vite preview (4173) ── proxy /api ──→ FastAPI (8000) ──→ PostgreSQL(未启动)
```

代理行为符合 `frontend/vite.config.ts:22-27` 的定义（`/api` 前缀、无 `rewrite`，路径原样透传），与生产环境 `frontend/nginx.conf` 的 `location /api/` + `proxy_pass http://backend:8000;`（同样无 URI 部分，路径原样保留）语义一致。

**跨域说明**：开发期浏览器只与 Vice 同源通信，`/api` 由 dev server 代理，不产生跨域；生产期浏览器只与 nginx 同源通信，`/api` 由 nginx 代理，同样不产生跨域。`CORS_ORIGINS` 仅在前后端**分属不同域名**部署时才起作用，属兜底配置。这一点已由 J2/J5 的实测（无任何 CORS 预检失败、无控制台 CORS 报错）佐证。

---

## 8. 验收结果汇总表

### 8.1 通过（32 项）

| 分类 | 编号 | 项目 |
| --- | --- | --- |
| 结构 | S1–S6 | 后端/前端目录、根级配置、Docker 资产、测试目录、docs 目录 |
| 后端 | B1–B4, B6–B14 | pip check、ruff、pytest 11 passed、uvicorn 启动、health 200、ready 503 语义、docs/redoc/openapi、根路由、17 模块 import、alembic 全链路、alembic check、离线 SQL、pip wheel |
| 前端 | F1–F10 | npm ls、npm ci --dry-run、type-check、build、dev 启动、首页 HTTP、首页渲染、SPA 路由、控制台、preview 生产产物 |
| 数据库 | D4, D5, D6 | SQLite 替身 SELECT 1、替身就绪 200、连接失败降级与错误提示 |
| 部署 | C1 | Compose YAML 静态解析（4 服务 + 命名卷 + 依赖链） |
| 联调 | J1, J2, J5 | 浏览器首页、前端→后端 API、生产产物联调 |

### 8.2 失败（3 项）

| 编号 | 项目 | 级别 | 状态 |
| --- | --- | --- | --- |
| B15 | 根目录 `.env` 不被后端读取（P0-1） | P0 | 失败（已实测复现） |
| B16 | 500 响应丢失 `request_id` 与 `X-Request-ID` 头（P0-2） | P0 | 失败（已实测复现） |
| S7 | `storage/`、`scripts/` 目录缺失 | P3 | 失败（第一阶段可接受，第二阶段前必须补） |

> 另有 S8（`backend/build/lib` 陈旧副本）、S9（Git 零提交）两项结构性失败，以及 W1–W9 共 9 条风险提示。

### 8.3 未执行（9 项）

| 编号 | 项目 | 原因 |
| --- | --- | --- |
| N1-a | `docker compose config` | Docker CLI 未安装 |
| N1-b | `docker compose up -d --build` | 同上 |
| N1-c | `docker compose ps` | 同上 |
| N1-d | `docker compose logs` | 同上 |
| N3-a | 后端镜像构建 | 依赖 Docker |
| N3-b | 前端镜像构建 | 依赖 Docker |
| N3-c | nginx 容器内反向代理实测 | 依赖 Docker |
| D1–D3 | PostgreSQL 启动、连接、`SELECT 1`（PostgreSQL 方言） | 本机无 PostgreSQL 实例 |
| F11 | 浏览器页面截图 | in-app Browser 无可见视口，已用结构化快照替代 |

**以上 9 项均未执行，不得计为通过。**

---

## 9. 修复建议汇总（按优先级，待确认后执行）

| 优先级 | 问题 | 修复方案 | 预计改动面 |
| --- | --- | --- | --- |
| **P0** | B15：`.env` 路径解析 | `config.py` 改用 `Path(__file__).resolve().parents[2]` 推导的绝对 `env_file` 元组；同步在 README 明确「根 `.env` 或 `backend/.env` 二选一，后者优先」 | `backend/app/core/config.py`、`README.md` |
| **P0** | B16：500 响应丢 `request_id` | `build_error_payload` 优先读 `request.state.request_id`；500 响应显式带 `X-Request-ID` 头；补一条 500 契约测试 | `backend/app/core/exceptions.py`、`backend/app/core/middleware.py`、`backend/tests/` |
| **P1** | W2：migrate 的 DSN 未编码 | 删除 `docker-compose.yml` 中手写的 `DATABASE_URL`，统一走 `POSTGRES_*` | `docker-compose.yml` |
| **P1** | W1：探针无连接超时 | asyncpg `connect_args={"timeout": 3}` 或 `asyncio.wait_for` 包裹 | `backend/app/core/database.py` |
| **P1** | 前端包体过大 | Element Plus 按需引入 + 路由动态导入 + `manualChunks` | `frontend/src/main.ts`、`frontend/vite.config.ts` |
| **P2** | 严格端口 | `server.strictPort = true` | `frontend/vite.config.ts` |
| **P2** | 构建可复现 | `npm install` → `npm ci` | `frontend/Dockerfile` |
| **P2** | 依赖瘦身 | 移除 `python-dotenv`；`langgraph` 移入 extras | `backend/pyproject.toml` |
| **P2** | 运行镜像瘦身 | 生产镜像不 `COPY tests` | `backend/Dockerfile` |
| **P2** | CORS 默认值漂移 | 统一 `config.py` 与 `docker-compose.yml` 的默认值 | 两处 |
| **P3** | S8/S9 | 删除 `backend/build/`；完成首次 Git 提交（提交前确认 `.env` 未被纳入） | 仓库 |
| **P3** | S7 | 第二阶段引入产物存储前补 `storage/`、`scripts/` 并更新 README 目录树 | 仓库 |
| **P3** | W7/W8/W9 | 健康信息在 store 内去重；补 ESLint + `npm run lint`；处理 `extractErrorMessage` 死代码 | 前端 |

---

## 10. 是否满足第一阶段验收标准

对照最初提出的 10 项工程要求逐条判定：

| # | 工程要求 | 判定 | 依据 |
| --- | --- | --- | --- |
| 1 | 前后端分离 + 模块化单体 | **满足** | 前后端独立进程/独立构建，代码分层符合约束 |
| 2 | 后端按 api/core/models/schemas/services/workflows/agents 划分 | **满足** | S1；`agents/` 为空占位，未提前实现业务 |
| 3 | 前端按 api/components/views/router/stores 划分 | **满足** | S1 |
| 4 | 配置统一由环境变量管理，代码不硬编码密码 | **不满足** | B15：密码未硬编码（满足），但根 `.env` 机制失效（不满足）→ **P0 待修** |
| 5 | `GET /api/v1/health` | **满足** | B5 实测 200 |
| 6 | 跨域、统一异常处理、日志、API 文档 | **部分满足** | CORS/日志/API 文档均实测通过（B7）；统一异常的 500 分支丢失 `request_id`（B16）→ **P0 待修** |
| 7 | Dockerfile + docker-compose 支持三服务启动 | **待定** | 文件与拓扑静态合理（C1），但 **9 项 Docker 相关测试未执行**，不能判为通过 |
| 8 | `.env.example` / `.gitignore` / `README.md` / `AGENTS.md` | **满足** | S3；`.env.example` 覆盖 `config.py` 全部可配项；`.gitignore` 正确忽略 `.env`、`.env.*` 并保留 `.env.example` |
| 9 | 前端基础布局、侧边导航、顶部导航、首页占位 | **满足** | F7/F8 浏览器实测渲染正确 |
| 10 | Windows 开发环境 + Linux Docker 环境均可运行 | **部分满足** | Windows 侧全部实测通过；Linux/Docker 侧**未实测** |

**结论：第一阶段基础工程「有条件通过」。**

- 10 项要求中 **7 项完全满足、2 项部分满足、1 项不满足**。
- 不满足项（要求 4、要求 6）均为**同一个模块（core 层）的两个 P0 缺陷**，修复量小、影响面清晰。
- 要求 10 的 Docker 侧为**环境受限导致的未验证**，不是代码缺陷，但同样不能计为通过。

**判定为「完全达标」的条件**：修复 B15、B16 两个 P0，并在具备 Docker 与 PostgreSQL 的环境中补做 9 项未执行测试（重点是 `docker compose up -d --build` 三服务全绿 + 后端对 PostgreSQL 的真实 `SELECT 1`）。

---

## 11. 下一阶段是否具备开发条件

**结论：具备，但建议先修复 2 个 P0 再开工。**

### 11.1 已具备的条件（实测支撑）

| 能力 | 证据 |
| --- | --- |
| 应用可启动、生命周期健康 | B4 |
| 路由与契约可扩展 | B7、路由按 `api/v1/router.py` 聚合，新增模块可独立挂载 |
| 迁移链路可用且与模型无漂移 | B10、B11 —— 第二阶段加表时 `alembic revision --autogenerate` 流程可直接使用 |
| 配置可由环境变量驱动 | B1/B15（机制存在，路径待修） |
| 错误契约基本成立 | B16（500 分支待修；4xx 分支实测正常） |
| 前端可构建、可运行、可联调 | F3–F10、J1/J2/J5 |
| 自动化测试基线 | B3（11 条用例全绿，可作为后续回归基线） |
| 浏览器可自动化验收 | F7–F9 已跑通 browser-use 流程，后续可复用于前端回归 |

### 11.2 开工前建议完成的事项

| 优先级 | 事项 | 理由 |
| --- | --- | --- |
| 必修 | 修复 B15（`.env` 路径） | 第二阶段每个开发者都要连库配密码，配置不生效会立刻阻塞全员 |
| 必修 | 修复 B16（500 契约） | 第二阶段接口增多后，错误响应格式会被前端大量依赖，事后改契约成本高 |
| 必修 | 完成首次 Git 提交 | 当前零版本记录，任何改动无法回滚 |
| 建议 | 安装 Docker Desktop 并补做 Compose 实测 | 第二阶段需在容器内跑迁移与联调，提前暴露镜像问题 |
| 建议 | 补 `storage/`、`scripts/` 目录 | 第二阶段涉及 Agent 产物与运行脚本 |
| 建议 | 前端引入 ESLint | 与后端 Ruff 对齐，避免风格漂移 |

### 11.3 不构成阻塞的事项

Element Plus 全量引入导致的包体偏大（W2 相关的 F 部分）、`extractErrorMessage` 死代码、注释与实际中间件栈序不符等，均可在第二阶段推进中并行处理，不必因此推迟开工。

---

## 12. P0 缺陷修复与复验记录（2026-11-03）

经确认后已修复本报告第 3.2、3.3 节记录的两个 P0 缺陷。下表为修复内容与复验证据。

### 12.1 P0-1：根目录 `.env` 不被后端读取

| 项 | 内容 |
| --- | --- |
| 根因 | `env_file=(".env", "backend/.env")` 由 pydantic-settings 按 **CWD** 解析，从 `backend/` 启动时仓库根的 `.env` 从未被读取 |
| 修复 | `backend/app/core/config.py`：新增 `BACKEND_DIR` / `PROJECT_ROOT` 常量，`env_file` 改用绝对路径元组 `(PROJECT_ROOT/".env", BACKEND_DIR/".env")`，保持「后者覆盖前者」语义 |
| 连带 | `README.md` 补充 dotenv 加载顺序说明（本地开发与「环境变量」两节） |

复验（临时 `.env` 用后即删）：

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 仅仓库根 `.env` 存在，cwd=`backend/` | `''`（**未加载**） | `'root-env-value'` ✅ |
| 仅仓库根 `.env` 存在，cwd=仓库根 | `'backend-env-value'` | `'root-env-value'` ✅ |
| 根 `.env` 与 `backend/.env` 同时存在 | `backend/.env` 恒胜出 | `backend/.env` 胜出（符合设计）✅ |
| 切换 CWD 后的加载结果 | 随 CWD 漂移 | 两种 CWD 结果一致 ✅ |

### 12.2 P0-2：500 响应丢失 `request_id` 与 `X-Request-ID`

| 项 | 内容 |
| --- | --- |
| 根因 | `RequestContextMiddleware` 在 `finally` 中重置 contextvar，而最外层 `ServerErrorMiddleware` 触发的兜底 handler 才读取它；`request.state` 仍保留着 ID 但此前未被使用 |
| 修复 | ① `app/core/context.py` 新增 `REQUEST_ID_HEADER` 常量与 `resolve_request_id(request)`（优先读 `request.state.request_id`，contextvar 兜底）；② `app/core/exceptions.py` 的 `build_error_payload` 改为必须接收 `request`，四个异常 handler 统一通过 `_response_headers()` 带上 `X-Request-ID`；③ `app/core/middleware.py` 改从 `context` 导入常量并补充说明 |
| 连带 | `backend/tests/test_exceptions.py` 强化原弱断言（`assert payload["request_id"]` 对 `"-"` 恒真）并新增两条契约测试；`backend/tests/test_config.py` 为新增文件，5 条用例覆盖 dotenv 路径与优先级 |

复验：

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 500（客户端指定 ID） | 头缺失，body `request_id="-"` | 头 `live-500-hdr`，body `request_id="live-500-hdr"` ✅ |
| 500（服务端生成 ID） | 头缺失，body `request_id="-"` | 头与 body 一致，均为 `73b0ddfd...` ✅ |
| 404 | 头与 body 一致 | 保持一致，未回归 ✅ |
| 200 正常路径 | 头正常 | 保持正常，未回归 ✅ |

> 500 场景通过真实 uvicorn 进程（临时挂载一个抛异常路由）与 `TestClient` 两条路径分别验证；验证用的探针进程与临时文件均已清理。

### 12.3 修复后的整体检查

| 命令 | 结果 |
| --- | --- |
| `python -m ruff check .` | `All checks passed!` |
| `python -m pytest -q` | `18 passed in 0.25s`（修复前 11 条，新增 7 条） |
| `python -m uvicorn app.main:app --port 8000` | `Application startup complete.` |
| `curl /api/v1/health` | `200`，`x-request-id` 正常回显 |
| `curl /api/v1/health/ready` | `503`（无 PostgreSQL），降级语义未变 |
| `curl /api/v1/nope` | `404`，错误信封含 `request_id` 与 `X-Request-ID` |

**结论**：两个 P0 已修复并复验通过。第一阶段要求 4（配置统一由环境变量管理）与要求 6（统一异常处理）由「不满足 / 部分满足」改为**满足**。除第 6 节的 9 项未执行测试（Docker / PostgreSQL 环境受限）外，其余验收项全部通过；**第一阶段由「有条件通过」上调为「通过（Docker 与 PostgreSQL 全链路待补测）」**。

---

## 附录 A：本轮实际执行的命令清单

```powershell
# 环境探测
docker --version ; docker compose version ; where psql ; ls "C:/Program Files/PostgreSQL"
sc query com.docker.service ; winget --version ; winget list --name "Docker" ; wsl --status

# 后端
cd backend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011   # DATABASE_URL=sqlite+aiosqlite:///...
.\.venv\Scripts\python.exe -m alembic upgrade head | current | history | downgrade base | upgrade head | check | upgrade head --sql
.\.venv\Scripts\python.exe -m pip wheel . --no-deps -w /tmp/wheelout

# 后端接口
curl -i http://127.0.0.1:8000/api/v1/health
curl -i http://127.0.0.1:8000/api/v1/health/ready
curl -i http://127.0.0.1:8000/docs ; /redoc ; /openapi.json ; /

# 前端
cd frontend
npm ls --depth=0 ; npm ci --dry-run ; npm run type-check ; npm run build ; npm run dev ; npm run preview
curl http://127.0.0.1:5173/ ; http://127.0.0.1:5173/api/v1/health ; http://127.0.0.1:4173/ ; http://127.0.0.1:4173/api/v1/health

# 浏览器（browser-use MCP）
navigate http://127.0.0.1:5173/ ; take_snapshot ; list_console_messages ; list_network_requests
navigate http://127.0.0.1:5173/workbench ; navigate http://127.0.0.1:4173/ ; reload
```

## 附录 B：本轮的临时文件与进程清理

| 项 | 处理 |
| --- | --- |
| 临时 `<root>/.env`、`<root>/backend/.env`（用于验证 P0-1） | 已删除，验证后确认不存在 |
| 临时 `backend/.acceptance_smoke.db`（SQLite 替身） | 已删除，验证后确认不存在 |
| 上一会话遗留的 Vite dev server（PID 48940，17:53 启动） | 已终止，释放 5173 端口 |
| SQLite 替身后端进程（8011） | 已停止 |
| 保留运行：FastAPI(8000)、Vite dev(5173)、Vite preview(4173) | 保持运行，便于人工复核 |
| 项目源文件 | **未做任何修改**；`git status` 显示的均为未跟踪的新增文件（仓库尚无提交） |
