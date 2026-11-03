# 第一轮代码级静态检查报告（Iteration 1）

- 检查对象：`D:\project\ai-dev-platform`
- 检查日期：2026-11-03
- 检查范围：后端（6 项）、前端（5 项）、部署（5 项），共 16 个检查项
- 检查性质：只读代码检查 + 本机可执行的动态验证；**未修改任何工程文件**（仅新增本报告）

> 说明：本报告的所有结论都基于真实读取的文件内容与真实执行的命令，不以“文件存在”推断“功能正常”。
> 动态验证环境：Windows 11 / Python 3.13.14（`backend/.venv`）/ Node v24.20.0 / npm 11 / Docker **未安装**（本轮无法做容器级验证，已在文末“未验证项”中如实标注）。

---

## 0. 结论速览

共发现 **19 项**问题，其中 2 项为 P0（会直接导致本地开发环境配置失效 / 生产排障线索丢失），7 项 P1，6 项 P2，4 项 P3。

| 级别 | 数量 | 代表问题 |
| --- | --- | --- |
| P0 阻断 | 2 | ① 后端读不到根目录 `.env`；② 500 响应丢失 `request_id` 与 `X-Request-ID` 头 |
| P1 严重 | 7 | compose `migrate` 使用未编码的裸 DSN、前端镜像未用 `npm ci`、主包 1.27 MB 等 |
| P2 一般 | 6 | nginx 上传体积上限、依赖体积、镜像重复构建等 |
| P3 轻微 | 4 | 死代码、配置项未接线、preflight 缺请求 ID 等 |

已验证**正确**的关键链路：FastAPI 应用工厂与中间件顺序、SQLAlchemy 2.x 异步引擎与连接池分支、Alembic 离线/在线双模式与 DSN 注入、pytest 配置与 11 条用例全绿、Vue3+TS 初始化与类型检查、Vite 开发代理与生产构建、nginx 反代路径保留、compose 服务依赖链与数据卷、`.env.example` 对 Settings 的覆盖率。

---

# 一、后端检查

## 1. FastAPI 入口及应用初始化

**检查文件**
`backend/app/main.py`、`backend/app/core/middleware.py`、`backend/app/core/exceptions.py`、`backend/app/core/logging.py`、`backend/app/core/context.py`、`backend/app/api/v1/router.py`

**检查结果**

- 应用工厂 `create_app()` + 模块级 `app = create_app()` 结构正确，`uvicorn app.main:app` 可用。
- `lifespan` 正确：启动时调用 `settings.runtime_errors()` 做配置校验（生产环境缺密码 / `DEBUG=true` 会直接 `RuntimeError` 拒绝启动），关闭时 `dispose_engine()` 释放连接池；DSN 只以 `masked_database_uri` 形式落日志，无明文密码泄露。
- 中间件顺序注释与实际一致：Starlette 的 `add_middleware` 是“后加者更外层”，因此实际顺序为 `ServerErrorMiddleware`（框架内置，最外）→ `CORSMiddleware` → `RequestContextMiddleware` → `AccessLogMiddleware` → `ExceptionMiddleware` → 路由。CORS 在最外层，保证预检请求不会被内部中间件拦截。
- 路由聚合正确：`api_router` 仅挂载 `health`，统一前缀 `/api/v1`，`/` 根路由 `include_in_schema=False`。
- 统一异常体系完整：`ErrorCode` 稳定枚举 + `AppException` 家族 + `StarletteHTTPException` / `RequestValidationError` / `Exception` 四类处理器，返回统一信封 `{code,message,detail,request_id,timestamp}`。
- 日志：`ContextFilter` 注入 `request_id`，文本与 JSON 两种格式，清理了 `uvicorn.access` / `sqlalchemy.engine.Engine` 的 handler。

**发现的问题**

1. **【P0】500 响应的 `request_id` 恒为 `"-"`，且响应头缺少 `X-Request-ID`。**
   `RequestContextMiddleware`（`middleware.py:24-32`）在 `finally` 中 `request_id_var.reset(token)`，而 Starlette 的 `ServerErrorMiddleware` 位于所有用户中间件之外；未被业务代码捕获的 `Exception` 由它调用注册的兜底处理器，此时 contextvar 已被重置为默认值 `"-"`（`context.py` 中 `ContextVar("request_id", default="-")`）。
   实测（`backend/.venv` 内执行）：
   ```
   status: 500
   body:   {"code":"INTERNAL_SERVER_ERROR","message":"Internal server error","detail":null,"request_id":"-",...}
   resp X-Request-ID header: None
   ```
   同时实测确认：`request.state.request_id` 在该处理器中**仍然可用**（实测值 `abc123`），因为 `request.state` 落在 `scope["state"]` 上，不随 contextvar 重置而丢失。
   另外，`middleware.py:31` 的 `response.headers[REQUEST_ID_HEADER] = request_id` 在异常路径上根本执行不到（异常穿过了 `call_next`），所以 500 响应连 `X-Request-ID` 头也没有。

2. **【P3】CORS 预检（OPTIONS）响应没有 `X-Request-ID`。**
   `CORSMiddleware` 在 `RequestContextMiddleware` 之外，预检被它直接短路返回，实测 `x-request-id: None`。AGENTS.md 声明“所有响应带 `X-Request-ID`”，此处未满足。

3. **【P3】`main.py:69` 的注释只描述了用户中间件的相对顺序，未说明 `ServerErrorMiddleware` 更外层**，这正是问题 1 长期未被发现的原因。

4. **【P3】`server_host` / `server_port` 定义了但从未被使用**（见后文 5.2），启动命令与配置项脱钩。

**问题影响**

- P0-1：线上 500 事故中，前端拿不到可用于检索后端日志的 `request_id`，`AGENTS.md` 中“错误响应体都包含 request_id”的契约实际不成立，跨服务链路定位会被显著拖慢；`tests/test_exceptions.py` 里的 `assert payload["request_id"]` 因为 `"-"` 也是真值而**未发现该缺陷**。
- P0-2：同上，响应头缺失使前端/网关无法回传与检索该 ID。
- P3-2：预检响应缺少链路 ID，影响面很小。

**修复建议**

- 在 `exceptions.py` 中让错误信封优先从请求状态读取 ID，而不是只读 contextvar：
  ```python
  def build_error_payload(code, message, detail=None, request: Request | None = None) -> dict:
      request_id = getattr(getattr(request, "state", None), "request_id", None) or request_id_var.get()
      ...
  ```
  并让 `_unhandled_exception_handler` / `_http_exception_handler` 把 `request` 传进去。
- 让 500 路径也带上响应头：可在 `RequestContextMiddleware` 中捕获异常并自行构造响应，或在 `_unhandled_exception_handler` 的 `JSONResponse` 上显式设置 `headers={"X-Request-ID": request_id}`。
- 在 `main.py` 注释中补充 `ServerErrorMiddleware` 的位置说明。
- 预检场景可在 `CORSMiddleware` 内层再加一层，或直接在 `Response` 上补 `X-Request-ID`。

---

## 2. Python 依赖配置完整性

**检查文件**
`backend/pyproject.toml`（另核对 `backend/.venv` 实际安装版本）

**检查结果**

- 运行期依赖覆盖了全部实际 import：`fastapi` / `uvicorn[standard]` / `pydantic` / `pydantic-settings` / `sqlalchemy[asyncio]` / `asyncpg` / `alembic` / `langgraph`。实测已安装：`fastapi 0.162.0`、`uvicorn 0.54.0`、`pydantic 2.14.2`、`pydantic-settings 2.16.2`、`SQLAlchemy 2.1.6`、`asyncpg 0.32.0`、`alembic 1.20.1`、`langgraph 0.6.11`。
- 开发依赖 `pytest` / `pytest-asyncio` / `httpx` / `aiosqlite` / `ruff` 齐备，且与 `tests/` 中实际用到的能力一一对应（`TestClient` 需要 `httpx`，SQLite 异步需要 `aiosqlite`）。
- 打包配置正确：`[tool.setuptools.packages.find] include=["app*"]`，`pip wheel . --no-deps` 实测成功产出 `ai_dev_platform_backend-0.1.0-py3-none-any.whl`（17,302 字节），说明 PEP 517 构建链路可用。
- `ruff` 校验实跑通过：`All checks passed!`；`pytest -q` 实跑 `11 passed in 0.18s`。

**发现的问题**

1. **【P2】`python-dotenv>=1.0.1` 是冗余依赖。** `pydantic-settings 2.x` 自身已依赖 `python-dotenv`（本机实测已装 `python-dotenv 1.2.4`），显式声明不会出错，但属于重复约束，容易在升级时产生版本冲突的噪音。
2. **【P2】`langgraph>=0.2.0,<1.0.0` 被放在运行期依赖里，显著放大镜像体积。** 实测它连带引入 `langchain-core 1.7.4`、`langsmith 0.14.17`、`langgraph-sdk 0.2.15`、`langgraph-checkpoint 3.0.1`、`langgraph-prebuilt 0.6.5` 以及 `httpx2 2.16.0`。而 `app/workflows/langgraph_runtime.py` 是**惰性导入**、且 `app/workflows` 目前只有抽象与注册表，业务代码根本没用到 LangGraph。
3. **【P2】`httpx2` 这一“下一代 HTTP 客户端”被间接引入生产依赖树**（来源为 `langsmith`）。它与项目实际使用的 `httpx 0.28.1` 并存，属于不必要的供应链暴露面。
4. **【P3】`requires-python = ">=3.11"` 但本机 venv 实际是 Python 3.13.14**，Dockerfile 用 `python:3.11-slim`。3.11 运行时行为（尤其 `datetime.UTC`、`StrEnum`、asyncio 细节）无法在本机完全等价验证。
5. **【P3】没有覆盖率工具与阈值**（未引入 `pytest-cov`），`[tool.pytest.ini_options]` 无 `addopts` 覆盖率门禁。

**问题影响**

- 2、3：后端镜像体积与依赖攻击面被无谓放大；`langgraph` 升级时还会牵动 `langchain-core` 的破坏性升级。
- 4：本地“测试全绿”不等于 3.11 镜像内“测试全绿”，存在版本漂移风险。
- 5：关键分支（如统一异常信封的 request_id）无覆盖率护栏。

**修复建议**

- 把 `langgraph` 移到可选依赖组：`[project.optional-dependencies] workflow = ["langgraph>=0.2.0,<1.0.0"]`，Dockerfile 用 `pip install .`（不含该组），需要工作流时再 `pip install ".[workflow]"`；同时可移除显式的 `python-dotenv`。
- 在 CI 中统一到 Python 3.11 矩阵，并补 `pytest --cov=app --cov-report=term-missing`。
- 若要保留 `langgraph` 在运行期依赖，至少锁定 `langchain-core` 上界，防止未来自动升级到不兼容版本。

---

## 3. SQLAlchemy 数据库连接配置

**检查文件**
`backend/app/core/database.py`、`backend/app/core/config.py`

**检查结果**

- 使用 SQLAlchemy 2.x 现代写法：`async_sessionmaker` / `create_async_engine` / `DeclarativeBase` / `Mapped` + `mapped_column`，`get_db()` 以 `AsyncGenerator` 形式作为 FastAPI 依赖。
- 连接池按驱动分支处理正确：SQLite 走 `NullPool`（无服务端连接池可调），PostgreSQL 走 `pool_size` / `max_overflow` / `pool_timeout` / `pool_recycle`，并统一开启 `pool_pre_ping`（连接前探活，避免拿到已被数据库或中间件断开的死连接）。SQLite 分支由 `settings.uses_sqlite`（前缀判定）驱动，与 `test_readiness.py` 的用法一致。
- 生命周期完整：引擎在模块级创建，`dispose_engine()` 在 `lifespan` 关闭阶段调用并记录日志。
- DSN 不硬编码：优先使用 `DATABASE_URL` 整体覆盖，否则用 `quote_plus` 拼装 `postgresql+asyncpg://user:password@host:port/db`。
- **DSN 编码实测通过**：`Settings(postgres_password="p@ss:w/rd #x", postgres_user="u ser")` → `postgresql+asyncpg://u+ser:p%40ss%3Aw%2Frd+%23x@h:5432/d`，反解得回原密码 `p@ss:w/rd #x`；`masked_database_uri` 正确输出 `://u+ser:***@h:5432/d`。

**发现的问题**

1. **【P1】连接参数缺少超时上限，数据库“假死”时请求会无限期挂起。** `db_pool_timeout` 只约束**从池中取连接**的等待，不约束**建立连接**的耗时；asyncpg 的连接超时默认 60s，而 `/health/ready` 的探测没有 `asyncio.wait_for` 包裹。这会让健康探针与业务请求在最坏情况下长时间占用协程。
2. **【P3】引擎在模块导入期创建，配置被“快照”固化。** `settings = get_settings()` 在模块顶层执行，`get_settings` 带 `lru_cache`，因此任何在导入之后才设置的环境变量都不会生效。对当前工程无实际影响，但会让“改环境变量没反应”的排查变复杂。
3. **【P3】未使用 SQLAlchemy 的 `async_` 之外的现代能力**：例如 `pool_reset_on_return` 默认行为、`AsyncSession` 的 `expire_on_commit=False` 已正确设置；此项仅作记录，无缺陷。

**问题影响**

- 1：数据库网络分区时 `/health/ready` 可能超出编排器健康检查窗口（compose 中 backend 健康检查 `timeout: 5s`）而长期挂起；同时会累积未释放的协程。
- 2：可维护性问题，非功能缺陷。

**修复建议**

- 在 `_engine_kwargs()` 中为 PostgreSQL 增加 `connect_args={"timeout": 5, "command_timeout": 30}`（asyncpg 参数），并给 `/health/ready` 的 `db.execute` 包一层 `asyncio.wait_for(..., timeout=settings.db_pool_timeout)`，超时按 `unavailable` 处理。
- 保持 DSN 组装逻辑不变（`quote_plus` 已正确），但把同样的编码规则复用/暴露给部署层，避免 compose 里出现另一套未编码写法（见部署检查 3.1）。

---

## 4. Alembic 数据库迁移配置

**检查文件**
`backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/versions/0001_baseline.py`、`backend/alembic/script.py.mako`

**检查结果**

- 凭据不入库：`alembic.ini` 中 `sqlalchemy.url` 留空，DSN 由 `env.py` 在运行时从 `get_settings().sqlalchemy_database_uri` 取，并做了 `%` → `%%` 转义（避免 ConfigParser 插值报错），已确认 `config.get_main_option("sqlalchemy.url")` 拿到的是未转义的原始 DSN。
- 离线 / 在线双模式完整：`context.is_offline_mode()` 分支提供 `literal_binds=True` + `paramstyle="named"`；在线分支使用 `async_engine_from_config` + `pool.NullPool` + `connection.run_sync`，符合 asyncpg 场景。
- `target_metadata` 通过 `_target_metadata()` 惰性导入 `app.models` 后取 `Base.metadata`，保证 autogenerate 时模型已注册。
- `compare_type=True` 已在两处开启，字段类型变更可被 autogenerate 检出。
- 迁移脚本 `0001_baseline.py` 同时实现 `upgrade()` / `downgrade()`，符合 AGENTS.md 要求。
- **命令可用性实测**：
  - `cd backend && python -m alembic --version` → `alembic 1.20.1`；
  - `cd backend && python -m alembic history` → `<base> -> 0001_baseline (head), Baseline revision of the platform scaffold.`；
  - **包遮蔽风险已排除**：本地 `backend/alembic/` 目录没有 `__init__.py`，但在 venv 中 `import alembic` 实际解析到 `site-packages/alembic/__init__.py`（命名空间片段会被后出现的常规包覆盖，符合 PEP 420），在临时目录构造同名 `alembic/` 目录复现验证：`python -m alembic history` 退出码 0，`import alembic` 仍指向 site-packages。**不存在“本地目录遮蔽 alembic 包”的问题。**

**发现的问题**

1. **【P3】`alembic.ini` 的 `script_location = alembic` 与 `prepend_sys_path = .` 都是相对当前工作目录解析的**，因此所有 Alembic 命令必须在 `backend/` 目录下执行。从仓库根目录执行时实测报 `FAILED: No 'script_location' key found in configuration.` —— 错误信息对新手不够直观（真实原因是没找到 `backend/alembic.ini`）。
2. **【P3】`env.py` 中 `fileConfig(config.config_file_name)` 使用了默认的 `disable_existing_loggers=True`**，在 Alembic 上下文中可能禁用 `app.*` logger，使迁移期间应用日志被静默。
3. **【P3】未配置 `include_schemas` / `compare_server_default`**，后续若引入多 schema 或希望 autogenerate 检出服务端默认值变更，需再调整。
4. **【P3】`0001_baseline` 为空迁移**（当前无业务表，符合阶段目标），但 `alembic_version` 表会成为第一个落库对象，属于预期行为。

**问题影响**

- 1：新人或 CI 在错误目录执行迁移命令时会遇到难以定位的报错。
- 2：迁移过程中应用日志可能被吞掉，排查迁移期问题困难。
- 3、4：暂不影响当前阶段。

**修复建议**

- 在 `backend/alembic.ini` 顶部加注释明确“必须在本目录执行”，并在 `AGENTS.md` 的迁移章节补一句“所有 Alembic 命令需先 `cd backend`”；或在仓库根增加一个 `alembic` 包装脚本。
- `fileConfig(config.config_file_name, disable_existing_loggers=False)`。
- 后续引入业务表时补 `compare_server_default=True`。

---

## 5. pytest 配置及测试代码

**检查文件**
`backend/pyproject.toml`（`[tool.pytest.ini_options]`）、`backend/tests/conftest.py`、`backend/tests/test_health.py`、`backend/tests/test_exceptions.py`、`backend/tests/test_readiness.py`

**检查结果**

- 配置完整：`pythonpath = ["."]`（保证 `import app` 可用）、`testpaths = ["tests"]`、`asyncio_mode = "auto"`、`asyncio_default_fixture_loop_scope = "function"`（后者是 pytest-asyncio ≥ 0.24 必需项，避免每次运行刷 deprecation 警告）。
- 实跑结果：**`11 passed in 0.18s`**，无 warning、无 error。
- 用例覆盖了有价值的路径：健康检查返回体与契约、OpenAPI 中存在 `/api/v1/health` 与 `/api/v1/health/ready`、`/docs` 可访问、`X-Request-ID` 头回显、CORS 预检允许 `http://localhost:5173`、404/422/500 三类错误信封、就绪探针在 SQLite 可达时返回 200 且带 `latency_ms`、在驱动异常与连接拒绝两种故障下返回 503 且 `status=not_ready`。
- 测试隔离设计合理：`test_readiness.py` 用 `dependency_overrides[get_db]` 注入临时 SQLite 引擎（`NullPool` 避免文件锁）与故障 Session 双桩，不会污染真实数据库；`tmp_path` 保证隔离。
- 之前的真实缺陷（就绪探针 500 而非 503）已被 `test_readiness.py` 的 `SQLAlchemyError` / `ConnectionRefusedError` 参数化用例固化，属于高质量回归测试。

**发现的问题**

1. **【P1】断言强度不足，导致 P0 缺陷漏检。** `test_exceptions.py` 中 `assert payload["request_id"]` 与 `assert payload["request_id"]`（500 用例）都只断言“非空”，而 `"-"` 同样非空，因此未捕获到 500 响应 request_id 恒为 `"-"` 的问题（已实测确认）。同理，500 用例未断言响应头 `X-Request-ID`。
2. **【P2】`tests/test_exceptions.py` 在模块级 `app = create_app()`，与 `conftest.py` 的 session 级 app 是两个不同实例**，测试路由 `/_test/boom`、`/_test/echo` 也未加 `include_in_schema=False`；当前无副作用，但与被测应用分叉，后续容易出现“测试路由污染 Schema”的隐患。
3. **【P2】缺少针对核心基础能力的单测**：`config.py` 的 DSN 拼装与 `quote_plus` 编码、`masked_database_uri` 脱敏、`runtime_errors()` 生产校验、`.env` 文件解析与优先级、异常信封结构 —— 这些都是本次 P0/P1 缺陷的高发区，目前零覆盖。
4. **【P3】未接入 `pytest-cov`**，无覆盖率报告与阈值。

**问题影响**

- 1：直接后果就是本次 P0-1 未被测试拦下，修复后也应补强断言。
- 2：潜在不一致。
- 3：回归防护缺口。

**修复建议**

- 把断言改为严格匹配，例如 `assert payload["request_id"] == response.headers["X-Request-ID"]`，且 `!= "-"`；并对 500 用例补充响应头断言。
- 新增 `tests/test_config.py`：覆盖 DSN 编码、密码脱敏、生产配置校验、`.env` 优先级（含多文件顺序语义，实测**后者优先级更高**）。
- 将测试路由统一加 `include_in_schema=False`，并让 `test_exceptions.py` 复用 `conftest` 的 app fixture（用 `app.dependency_overrides` 或独立 fixture 挂载路由）。
- 引入 `pytest-cov` 并设定基线阈值。

---

## 6. 后端 Dockerfile 可构建性

**检查文件**
`backend/Dockerfile`、`backend/.dockerignore`、`backend/pyproject.toml`

**检查结果**

- 基础镜像 `python:3.11-slim` 与 `requires-python = ">=3.11"` 一致；环境变量 `PYTHONDONTWRITEBYTECODE` / `PYTHONUNBUFFERED` / `PIP_NO_CACHE_DIR` / `PIP_DISABLE_PIP_VERSION_CHECK` 设置正确（日志即时输出、无 pip 缓存）。
- 依赖安装顺序合理：先 `COPY pyproject.toml`（配合 setuptools 的 PEP 517 元数据准备），再 `COPY app/alembic/alembic.ini/tests`，最后 `pip install --upgrade pip && pip install .`。
- 安全实践到位：`useradd --create-home --uid 10001 appuser` + `chown -R` + `USER appuser`，容器不以 root 运行。
- 健康检查使用 `curl -fsS http://127.0.0.1:8000/api/v1/health`，且 `curl` 已在同一层通过 `apt-get install --no-install-recommends` 安装（不会在运行时才发现缺命令）。
- `EXPOSE 8000` 与 `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000` 一致，也与 compose 中 `8000:8000` 映射一致。
- `.dockerignore` 正确排除了 `.venv/`、`__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`.ruff_cache/`、`*.db`、`*.sqlite3` 以及 `.env` / `.env.*`（保留 `.env.example`）。
- **构建可行性做了等价验证**：`pip wheel . --no-deps` 实测成功；`python -m pytest` 在同版本依赖下 11 项全绿；`alembic` CLI 在 `backend/` 下可用（`alembic 1.20.1`）。

**发现的问题**

1. **【P2】`COPY tests ./tests` 把测试代码带进生产镜像**，而 `pip install .` 又不会安装 `tests`（`packages.find` 只含 `app*`），属于纯粹的体积与信息冗余。
2. **【P2】`pip install .` 之后 `/app/app` 与 site-packages 中同时存在一份 `app`**，重复占用空间；运行时 uvicorn 的 sys.path 以 CWD 优先，最终生效的是 `/app/app`。行为正确但不必要。
3. **【P2】`pip install --upgrade pip && pip install .` 依赖构建期外网**（PEP 517 隔离构建需要下载 `setuptools>=68`）。CI 环境若无代理/镜像源会显著变慢甚至失败。
4. **【P3】未设置 `PORT` / `HOST` 等运行期可调项**，端口写死在 CMD 中，与 `settings.server_host/server_port` 形同虚设（配置项未接线）。
5. **【P3】未做镜像体积/层数优化**（如 `--no-cache-dir` 已由 `PIP_NO_CACHE_DIR` 覆盖，但缺少 builder 多阶段分层：可在 builder 阶段装依赖、runtime 阶段只拷 site-packages）。

**问题影响**

- 1、2：镜像体积与攻击面轻微膨胀。
- 3：构建稳定性依赖外部网络。
- 4：部署时改端口需要改镜像。

**修复建议**

- 删除 `COPY tests ./tests`（或在独立的 test stage 中保留）。
- 改为多阶段：`builder` 阶段 `pip wheel` 产出 wheel，`runtime` 阶段 `pip install --no-index --find-links=/wheels *.whl`，并把 `app` 以源码或包二选一（推荐只装包，删掉 `COPY app`，运行时用 site-packages 版本）。
- 配置 pip 镜像源（`PIP_INDEX_URL`）或在 CI 中预热依赖缓存。
- 让 CMD 读取环境变量：`CMD ["uvicorn","app.main:app","--host","${SERVER_HOST:-0.0.0.0}","--port","${SERVER_PORT:-8000}"]`（需配合 shell 形式），或改用 `python -m uvicorn ... --env-file` 之外的入口脚本。

---

# 二、前端检查

## 1. Vue 3 与 TypeScript 初始化

**检查文件**
`frontend/package.json`、`frontend/tsconfig.json`、`frontend/tsconfig.node.json`、`frontend/src/env.d.ts`、`frontend/index.html`

**检查结果**

- `npm ls --depth=0` 实测：所有声明依赖均已安装，无 `UNMET DEPENDENCY`、无 extraneous。实测版本：`vue 3.5.44`、`vue-router 4.6.4`、`pinia 2.3.1`、`element-plus 2.14.7`、`@element-plus/icons-vue 2.3.2`、`axios 1.21.0`、`vite 6.4.5`、`@vitejs/plugin-vue 5.2.4`、`typescript 5.6.3`、`vue-tsc 2.2.12`、`@types/node 22.20.5`。
- `tsconfig.json` 严格：`strict: true`、`noUnusedLocals`、`noUnusedParameters`、`noFallthroughCasesInSwitch`、`useUnknownInCatchVariables`、`isolatedModules`、`verbatimModuleSyntax` 未开但 `isolatedModules` 已开，配 `import type` 的写法一致；`moduleResolution: "bundler"` 与 Vite 6 匹配；`paths` 中 `@/* → ./src/*` 与 `vite.config.ts` 的 alias 一致。
- `tsconfig.node.json` 单独覆盖 `vite.config.ts`（`types: ["node"]`），`npm run type-check` 实跑通过（`vue-tsc` + `tsc` 均无输出即成功）。
- `env.d.ts` 完整声明了 `ImportMetaEnv` 的 5 个 `VITE_` 变量，与 `frontend/.env.example` 的键完全对应，`import.meta.env.VITE_XXX` 无 `any` 泄漏。
- `index.html` 使用 `lang="zh-CN"`，挂载点 `#app` 与 `main.ts` 一致。

**发现的问题**

1. **【P3】`package.json` 的 `engines.node = ">=20.19.0"` 与实际 Node 大版本约束偏松**，未限制上界；本机 Node 24、Docker 用 `node:22-alpine`，两者都满足当前依赖，但缺少 `engines` 与 Vite 6 的对应关系校验（Vite 6 官方支持 `^18.0.0 || ^20.0.0 || >=22.0.0`）。
2. **【P3】`tsconfig.json` 未开启 `verbatimModuleSyntax`**，与 `isolatedModules` 组合下类型导入仍靠人工约定，可读性略低。

**问题影响**：均为规范层面，无功能影响。

**修复建议**：在 `engines` 中写明 `>=20.19.0 <25`（或与 Vite 6 官方支持矩阵对齐），并考虑开启 `verbatimModuleSyntax`。

---

## 2. `main.ts` 与 `App.vue`

**检查文件**
`frontend/src/main.ts`、`frontend/src/App.vue`、`frontend/src/components/layout/AppSidebar.vue`、`frontend/src/components/layout/AppHeader.vue`、`frontend/src/views/*.vue`

**检查结果**

- `main.ts` 装配顺序正确：`createApp` → `createPinia` → `router` → `ElementPlus`（带 `zh-cn` locale）→ 全局注册图标 → `mount('#app')`。Element Plus 样式与自定义 `styles/index.css` 均已引入，中文语言包生效（界面上表现为“后端 正常 / 检测中”等中文文案）。
- `App.vue` 采用 `el-container` + 侧栏 + 头部 + `router-view` 的经典后台布局，`.app-layout { height: 100vh }` 保证内部滚动；`AppSidebar` / `AppHeader` 通过 `@/components/layout` 统一出口引入，符合 AGENTS.md 的目录约定。
- 状态管理分层清晰：`stores/app.ts` 用 Pinia setup store 持有 `health` / `readiness` / `backendOnline`，页面通过 `@/stores` 导入，不直接调 axios；`views/` 不含 axios 调用，符合 AGENTS.md 的依赖方向。
- 路由懒加载到位：`createWebHistory` + 三个路由均使用 `() => import(...)` 动态导入，构建产物确认 `HomeView` / `WorkbenchView` / `NotFoundView` 被拆分为独立 chunk。

**发现的问题**

1. **【P1】全量引入 Element Plus + 全量注册所有图标，导致主包 1.27 MB。** `main.ts:3-21` 同时做了 `import ElementPlus from 'element-plus'`、`import 'element-plus/dist/index.css'`、`import * as ElementPlusIconsVue from '@element-plus/icons-vue'` 并逐个 `app.component()` 注册。实测 `npm run build` 输出：
   ```
   dist/assets/index-BwqhR67V.js   1,275.43 kB │ gzip: 412.93 kB
   dist/assets/index-CbWZVfA4.css    362.78 kB │ gzip:  48.57 kB
   (!) Some chunks are larger than 500 kB after minification.
   ```
   1696 个模块被转换，Vite 已明确告警。
2. **【P3】图标组件依赖“全局注册”这一隐式约定**：`AppSidebar.vue` 用 `<component :is="menu.icon" />` 动态渲染字符串图标名，`AppHeader.vue` 直接用 `<Platform />`、`<Refresh />`。这些写法只有在全局注册全部图标时才可用，与问题 1 的优化方向（按需引入）直接冲突 —— 一旦改为按需引入而忘记同步模板，会静默失效。
3. **【P3】`AppHeader.vue` 中混用 `$route`（模板内全局属性）与 `useRoute()`**，风格不统一（`AppSidebar` 用的是 `useRoute()`）。
4. **【P3】`App.vue` 中 `AppHeader` / `AppSidebar` 直接 import 具体文件**，而 `@/components/layout/index.ts` 已提供统一出口，风格不统一（不影响功能）。

**问题影响**

- 1：首屏需要下载 413 KB（gzip）JS + 48 KB CSS，移动端与弱网首屏明显变慢；随 Element Plus 升级还会继续增长。
- 2：优化时容易踩坑。
- 3、4：仅可读性。

**修复建议**

- 引入 `unplugin-vue-components` + `unplugin-auto-import`（Element Plus 官方推荐），改为按需自动导入组件与样式；图标改为在使用的 SFC 内显式 `import { Platform, Refresh, HomeFilled, Monitor } from '@element-plus/icons-vue'`。
- 若暂不引入插件，至少手工把 Element Plus 改为按需 `import { ElButton, ElCard } from 'element-plus'` + 对应 `element-plus/es/components/*/style/css`，并把 `main.ts` 的全量图标注册替换为按需注册。
- 配合 `build.rollupOptions.output.manualChunks` 把 `vue` / `vue-router` / `pinia` / `element-plus` 拆成独立 chunk。
- 统一使用 `useRoute()`，并统一从 `@/components/layout` 导入布局组件。

---

## 3. Vite 配置及开发服务器配置

**检查文件**
`frontend/vite.config.ts`、`frontend/.env.example`、`frontend/nginx.conf`

**检查结果**

- `loadEnv(mode, process.cwd(), '')` 前缀为空串，因此 `VITE_DEV_API_PROXY_TARGET`、`VITE_PORT`、`VITE_PREVIEW_PORT` 这类**非 `VITE_` 暴露要求**的变量也能被读取，用于开发期代理配置，思路正确（`VITE_` 前缀只影响是否注入浏览器 bundle，这里读取的是构建期配置）。
- 开发服务器：`host: true`、`port: env.VITE_PORT ?? 5173`；**`server.proxy` 与 `preview.proxy` 都配置了 `/api` → `http://localhost:8000`，且未设置 `rewrite`**，因此 `/api/v1/health` 原样转发到后端 `/api/v1/health` —— 这点很关键，若误加 `rewrite` 会把 `/api` 前缀去掉导致 404。当前实现正确。
- `@` 别名通过 `fileURLToPath(new URL('./src', import.meta.url))` 定义，与 tsconfig `paths` 一致，且不依赖 `path.resolve` 在 Windows 下的分隔符问题。
- 构建：`outDir: 'dist'`、`sourcemap: mode !== 'production'`（生产不出 sourcemap，良好实践）。
- `npm run build` 实测成功（6.61s），产物落盘 `frontend/dist`。

**发现的问题**

1. **【P3】`server.host = true` 会把开发服务器暴露到局域网**，同网段设备可直接访问开发后端代理；公共网络/共享环境存在风险。
2. **【P3】未设置 `server.strictPort`**，端口被占用时会静默切换到 5174/5175，而 README 与 `.env.example` 中写死的是 5173，容易造成“文档写的端口打不开”的困惑。
3. **【P3】`loadEnv(mode, process.cwd(), '')` 依赖启动目录**，若从仓库根执行 `npm --prefix frontend run dev`，`process.cwd()` 会变成仓库根，读不到 `frontend/.env.local`。
4. **【P3】未配置 `build.chunkSizeWarningLimit` / `manualChunks`**，因此问题 2.1 的体积问题没有任何缓解与告警阈值。

**问题影响**

- 1：开发环境暴露风险（低）。
- 2、3：使用体验与文档一致性问题。
- 4：性能债务无告警。

**修复建议**

- 开发期把 `host` 改为 `'localhost'`（如确需局域网访问则显式传 `VITE_HOST=0.0.0.0`）。
- 增加 `strictPort: true`。
- 在 `vite.config.ts` 中用 `fileURLToPath(new URL('.', import.meta.url))` 取代 `process.cwd()`，使 `.env` 查找不依赖启动目录。
- 配置 `build.chunkSizeWarningLimit` 与 `manualChunks`。

---

## 4. 前端 API 请求地址正确性

**检查文件**
`frontend/src/api/client.ts`、`frontend/src/api/health.ts`、`frontend/src/api/index.ts`、`frontend/src/stores/app.ts`、`frontend/src/env.d.ts`

**检查结果**

- baseURL 解析正确：`export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'`，开发期由 Vite 代理接管，生产期由 nginx 反代接管，两条链路都不产生跨域。
- 请求路径拼接正确：`http.get('/health')` + baseURL `/api/v1` → `/api/v1/health`；`http.get('/health/ready')` → `/api/v1/health/ready`，与后端 `api_v1_prefix = "/api/v1"` 及路由挂载一致（实测后端 OpenAPI 中两个路径均存在）。
- 错误信封解析正确：拦截器从 `error.response.data` 取 `message`，与后端 `{code,message,detail,request_id,timestamp}` 结构对齐；`extractErrorMessage` 同样按 `data.message` 优先。
- axios 实例配置合理：`timeout: 15000`、`Content-Type: application/json`。
- `env.d.ts` 声明了 `VITE_API_BASE_URL`，`import.meta.env` 有类型，无 `any`。

**发现的问题**

1. **【P2】`extractErrorMessage` 是死代码。** 全仓库检索（`frontend/src`）仅在定义处出现，无任何调用点。
2. **【P2】错误拦截器只覆盖 `response.data.message`，未覆盖 `error.response.data` 非对象形态的情况。** 当后端返回 HTML 错误页（nginx 502/504）或网关返回纯文本时，`payload?.message` 为 `undefined`，最终回落到 `error.message`（如 `Request failed with status code 502`）—— 可接受，但缺少对 `request_id` 的提取，前端无法把后端的链路 ID 呈现给用户。
3. **【P3】`timeout: 15000` 与 `/health/ready` 的最长耗时不匹配**：就绪探针要真实往返数据库，叠加连接池等待与后端可能的连接超时（见 3.1），15s 有被击穿的可能。
4. **【P3】拦截器用 `Object.assign(error, { message })` 就地改写 axios error 对象**，属于可变副作用；虽可行，但会让 `error.message` 与 `error.response.data.message` 语义混淆。

**问题影响**

- 1：无功能影响，仅冗余。
- 2：故障排查时前端拿不到后端 `request_id`，与后端 P0-1 叠加后定位链路更弱。
- 3：就绪状态可能显示为“不可用”而非真实原因。
- 4：可读性。

**修复建议**

- 删除 `extractErrorMessage`（或在 `stores/app.ts` 中真正使用它，把后端 `message` 统一转成用户可读文案）。
- 让拦截器一并提取 `request_id`，附加到错误对象上（例如 `Object.assign(error, { message, requestId })`），供 UI 展示。
- 为就绪探针单独设置更长超时（或独立 axios 实例，`timeout: 30000`）。
- 改为返回一个新的、带规范化字段的错误对象，避免就地修改。

---

## 5. 生产构建配置及前端 Dockerfile

**检查文件**
`frontend/Dockerfile`、`frontend/nginx.conf`、`frontend/.dockerignore`、`frontend/package.json`

**检查结果**

- **构建实跑通过**：`npm run build` → `vue-tsc --noEmit` + `vite build` 全绿，产物 `dist/index.html`、`dist/assets/index-*.js`、`dist/assets/index-*.css` 及按路由拆分的 chunk 均正常生成。
- Dockerfile 为标准两阶段：`node:22-alpine` 构建 → `nginx:1.27-alpine` 运行，`COPY --from=builder /app/dist /usr/share/nginx/html` 只搬运产物，源码不进入运行镜像；`EXPOSE 80` 与 `CMD ["nginx","-g","daemon off;"]` 正确。
- **Vite 变量以构建期 ARG 注入**：`ARG VITE_API_BASE_URL=/api/v1` → `ENV VITE_API_BASE_URL=$VITE_API_BASE_URL`，与 compose 的 `build.args` 对应，语义正确（Vite 变量确实是构建期烘焙的）。
- 健康检查使用 `wget -q -O /dev/null http://127.0.0.1/`（busybox 自带 wget，nginx:alpine 镜像自带），无需额外安装。
- `.dockerignore` 排除了 `node_modules/`、`dist/`、`.vite/`、`.env` / `.env.*`（保留 `.env.example`）、`npm-debug.log*`。
- nginx 配置：`root /usr/share/nginx/html` + `index index.html`；`location /api/` 反代到 `http://backend:8000`；`proxy_pass` **不带 URI 部分**，因此原始请求 URI（含 `/api` 前缀）被完整保留到后端 —— 这是与后端 `/api/v1` 路由匹配的关键，实测语义正确；`try_files $uri $uri/ /index.html` 实现 SPA history 路由回退。

**发现的问题**

1. **【P1】Dockerfile 使用 `npm install` 而非 `npm ci`。** 已提交 `package-lock.json`，但 `npm install` 允许在安装时改写锁文件并按 semver 浮动解析，构建不可复现（同一份源码在不同时间可能装出不同依赖树）。实测 `npm ci --dry-run` 可以成功执行，说明锁文件与 `package.json` 当前是同步的，切换到 `npm ci` 无额外成本。
2. **【P2】nginx 未设置 `client_max_body_size`**，默认 1 MB。后续一旦支持文件上传（如知识库、模型文件），超大请求会在 nginx 层直接 413，且报错对前端不友好。
3. **【P2】nginx 未开启 gzip / `gzip_static`**，1.27 MB 的主包以未压缩形式传输，直接放大了首屏流量成本（压缩后约 413 KB）。
4. **【P3】`location /api/` 匹配不到恰好为 `/api` 的路径**（缺尾斜杠），该请求会落到 SPA 回退并返回 `index.html`。
5. **【P3】缺少安全响应头**（`X-Content-Type-Options`、`X-Frame-Options`、CSP 等）与 `server_tokens off`。
6. **【P3】未配置 `proxy_set_header X-Request-ID`**：虽然 nginx 默认会透传客户端的 `X-Request-ID`，但未显式声明，后端生成的 ID 也无法由前端回传链路上游（当前影响很小）。
7. **【P3】Docker 构建未使用 `npm ci --omit=dev` 分层或缓存挂载**，每次构建都要完整安装依赖。

**问题影响**

- 1：构建不可复现，是供应链治理红线级别的问题。
- 2：未来上传功能直接被 1 MB 卡死。
- 3：首屏流量成本约多传 862 KB。
- 4~7：健壮性与规范性问题。

**修复建议**

- `RUN npm ci`（并保留 `package-lock.json` 提交），构建失败即锁文件不同步，问题立刻暴露。
- nginx 增加 `client_max_body_size 20m;`（按业务实际调整）、`gzip on;` + `gzip_types text/css application/javascript application/json image/svg+xml;`、安全响应头与 `server_tokens off;`。
- 补充 `location = /api { ... }` 或统一改为 `location /api`（配合 `proxy_pass http://backend:8000;`）。
- 显式补 `proxy_set_header X-Request-ID $http_x_request_id;`。

---

# 三、前后端部署检查

## 1. 根目录 `docker-compose.yml`

**检查文件**
`docker-compose.yml`（另比对 `README.md` 启动命令、`.env.example`）

**检查结果**

- 4 个服务：`db`（postgres:16-alpine）、`migrate`（一次性执行 `alembic upgrade head`）、`backend`、`frontend`。
- 依赖链完整且语义正确：`backend` → `migrate`（`condition: service_completed_successfully`）→ `db`（`condition: service_healthy`）；`frontend` → `backend`（`condition: service_healthy`）。**迁移成功后才拉起应用、前端等后端健康后才启动**，时序设计正确。
- `db` 健康检查用 `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`，`interval 10s / timeout 5s / retries 10`，符合 postgres 官方推荐。
- `backend` 健康检查 `curl -fsS http://127.0.0.1:8000/api/v1/health` —— 命中的是**不依赖数据库**的存活探针，因此数据库故障不会导致后端容器被误判为不健康，设计合理。
- 端口映射与 README 完全一致：前端 `${FRONTEND_PORT:-80}:80`、后端 `${BACKEND_PORT:-8000}:8000`、数据库 `${POSTGRES_PORT:-5432}:5432`；README 的 `docker compose up -d --build` / `down` / `down -v` 与文件匹配，**compose 放在根目录与 README 命令一致，无需调整**。
- `restart` 策略合理：`db`/`backend`/`frontend` 为 `unless-stopped`，`migrate` 为 `"no"`。
- `${VAR:-default}` 语法覆盖了 compose 变量占位，且 compose 会自动读取根目录 `.env` 做插值（与 README 中 `cp .env.example .env` 的步骤吻合）。

**发现的问题**

1. **【P1】`migrate` 与 `backend` 各自写了一份完全相同的 `build:` 块**（`context: ./backend` + `dockerfile: Dockerfile`），Compose 会为两个服务分别构建、分别打标签，产出两个内容相同的镜像，浪费构建时间与磁盘。
2. **【P1】`migrate` 服务显式拼接了 `DATABASE_URL`，且密码未做 URL 编码**（详见 3.1）。
3. **【P2】`migrate` 服务同时设置了 `POSTGRES_*` 与 `DATABASE_URL`**，而 `Settings.sqlalchemy_database_uri` 中 `DATABASE_URL` 优先级更高 —— `POSTGRES_*` 实际是死配置，容易误导维护者。
4. **【P2】`db` 的 `POSTGRES_PASSWORD` 默认值是 `postgres`**（`${POSTGRES_PASSWORD:-postgres}`），若用户忘记创建 `.env`，容器会以弱口令启动且没有任何告警。
5. **【P3】没有为服务声明 `networks:`**，依赖默认网络；虽然默认网络已能满足 `db` / `backend` 的服务名解析，但显式声明更利于后续接入反向代理或外部网络。
6. **【P3】`container_name` 硬编码**（`ai-dev-platform-*`），会导致同一台机器上无法并行启动多套实例（项目名冲突即报错）。
7. **【P3】`backend` 服务未注入 `APP_VERSION` / `DOCS_URL` / `REDOC_URL` / `OPENAPI_URL` / `DB_*` / `CORS_ALLOW_*` 等 Settings 字段**，容器内只能用默认值；目前默认值与 `.env.example` 一致所以无差异，但用户改 `.env` 里的 `DB_POOL_SIZE` 之类不会生效，容易误判。

**问题影响**

- 1：构建耗时与镜像占用翻倍。
- 2：见 3.1，属于会导致迁移失败的实质缺陷。
- 4：安全默认值风险。
- 7：配置“看起来改了但没生效”的常见困惑来源。

**修复建议**

- 抽公共构建定义（YAML anchor 或 `x-backend-build: &backend-build`），并给两个服务设置同一个 `image: ai-dev-platform-backend:local`，只构建一次。
- 删掉 `migrate` 的 `DATABASE_URL`（见 3.1），只保留 `POSTGRES_*`，让后端与迁移共用同一套 DSN 组装逻辑。
- 对 `POSTGRES_PASSWORD` 去掉弱默认值或改用 `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}` 强制显式提供。
- 显式声明 `networks:`；去掉 `container_name` 或参数化；为 `backend` 补齐需要透传的环境变量。

---

## 2. 前后端服务之间的网络配置

**检查文件**
`docker-compose.yml`、`frontend/nginx.conf`

**检查结果**

- 所有服务默认加入同一个 Compose 默认网络，服务名即 DNS 名：`backend` 内访问 `db:5432`、`migrate` 内访问 `db:5432`、nginx 内访问 `backend:8000`。nginx 的 `proxy_pass http://backend:8000;` 正是依赖这一 DNS 解析，配置正确。
- 后端容器内 `POSTGRES_HOST: db`、`POSTGRES_PORT: 5432` 均为服务名/容器内端口，**未误用宿主机映射端口**（宿主机端口可自由改动而容器内链路不受影响），这是常见易错点，此处正确。
- 前端 `nginx.conf` 的 `proxy_pass` **不带路径后缀**，`/api/v1/health` 原样透传到后端，路径与后端 `/api/v1` 前缀匹配。
- `proxy_set_header` 覆盖了 `Host` / `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto`，后端可拿到真实客户端 IP；`proxy_http_version 1.1` 与 `proxy_read_timeout 60s` 设置合理。
- Compose 中未使用 `links`/`network_mode: host` 等过时写法，也没有硬编码 IP。

**发现的问题**

1. **【P3】nginx 反代未把 `X-Request-ID` 显式纳入 `proxy_set_header`**，虽然默认透传，但缺少显式声明；配合后端 P0-1，跨服务链路 ID 的传递在 500 场景下会断链。
2. **【P3】未配置 `proxy_buffering off` 或流式响应支持**，未来若接入 SSE / 流式 LLM 输出，nginx 会缓冲导致前端“看不到实时输出”。这是 AI 平台类项目的常见后续需求。
3. **【P3】`proxy_read_timeout 60s` 对长耗时的 Agent 调用偏短**，且未设置 `proxy_send_timeout`。
4. **【P3】未显式声明 `networks`**（见 1.5）。

**问题影响**：均为演进型风险，当前功能正常。

**修复建议**：显式补 `proxy_set_header X-Request-ID $http_x_request_id;`；为后续流式场景预留 `proxy_buffering off;`（可放在 `/api/` 之外的独立 location，或通过 map 控制）；按 Agent 场景上调 `proxy_read_timeout` 至 300s 并补 `proxy_send_timeout`。

---

## 3. PostgreSQL 环境变量与数据持久化配置

**检查文件**
`docker-compose.yml`、`backend/app/core/config.py`、`.env.example`

**检查结果**

- 持久化正确：命名卷 `postgres_data` 挂载到 `/var/lib/postgresql/data`（PostgreSQL 官方数据目录），`docker compose down` 保留、`down -v` 删除，与 README 说明一致。
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` 三件套齐备，且**同时下发给了 `db`（决定库内角色与库名）和 `backend` / `migrate`（决定客户端连接身份）**，不存在“服务端建了用户但客户端用别的身份连接”的错配。
- 密码不进代码：compose 只做变量插值，真实值来自根 `.env`（已被 `.gitignore` 忽略、`.env.example` 仅含占位值 `change-me-before-use`）。
- 后端通过 `POSTGRES_*` 拼装 DSN 时使用 `quote_plus` 编码，**应用层编码是正确的**（实测见后端检查 3）。

**发现的问题**

1. **【P1】`migrate` 服务手工拼接的 `DATABASE_URL` 未做 URL 编码，与后端应用层的编码规则不一致。**
   `docker-compose.yml:38-39`：
   ```yaml
   DATABASE_URL: >-
     postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@db:5432/${POSTGRES_DB:-ai_dev_platform}
   ```
   由于 `DATABASE_URL` 在 `Settings.sqlalchemy_database_uri` 中**优先级高于** `POSTGRES_*`，迁移容器会使用这条未编码的裸 DSN；而 `backend` 服务没有设置 `DATABASE_URL`，会走 `quote_plus` 编码路径。**同一个密码在两个容器里得到两种 DSN。**
   实测佐证（SQLAlchemy `make_url` 解析）：
   ```
   pw='postgres'  -> user='postgres' password='postgres' host=db db=ai_dev_platform   ✅
   pw='p@ss'      -> user='postgres' password='p'        host=ss@db  db=ai_dev_platform ❌
   ```
   即密码含 `@` 时，裸 DSN 会被解析成“密码=p、主机=ss@db”，迁移直接连不上或连到错误目标；含 `:` `/` `#` 也存在歧义风险。
2. **【P2】弱默认口令**（见 1.4）：`.env` 缺失时 `db` 使用 `postgres/postgres`。
3. **【P3】`db` 未声明 `stop_grace_period`**，快速重启时 PostgreSQL 有被 SIGKILL 的可能，理论上存在数据恢复风险。
4. **【P3】未固定 `postgres:16-alpine` 的具体补丁版本**，长期运行会有漂移（对基础工程阶段可接受）。

**问题影响**

- 1：**这是本轮最容易被真实触发的部署级故障** —— 用户按 README 把密码改成 `P@ssw0rd!` 这类常见强口令后，`migrate` 容器会因 DSN 解析错误而失败，后端因 `service_completed_successfully` 条件永不满足而**永远无法启动**，且报错信息是数据库连接失败，排查方向容易被误导。
- 2：安全风险。
- 3、4：运维稳健性。

**修复建议**

- **首选**：删除 `migrate` 服务中的 `DATABASE_URL`，只保留 `POSTGRES_*`，让迁移与后端共用 `config.py` 的 `quote_plus` 编码路径（推荐本轮修复）。
- 备选：在 compose 中对密码做 URL 编码（Compose 变量插值无法直接调用 URL 编码函数，需借助 `.env` 中已编码的变量，或改用 `env_file` + 显式 `DATABASE_URL`），但维护成本高。
- 去掉 `POSTGRES_PASSWORD` 的弱默认值，改为 `${POSTGRES_PASSWORD:?must be set}` 强制提供。
- 为 `db` 增加 `stop_grace_period: 30s`。

---

## 4. 前端访问后端 API 的跨域与代理配置

**检查文件**
`frontend/nginx.conf`、`frontend/vite.config.ts`、`backend/app/main.py`、`backend/app/core/config.py`、`docker-compose.yml`

**检查结果**

- **生产链路（Docker）**：浏览器 → nginx（`http://localhost/`）→ 同源请求 `/api/v1/*` → nginx 反代到 `backend:8000`。因为浏览器视角下是**同源**，实际上根本不会触发 CORS 预检，跨域问题在容器化链路中天然不存在。这是最省事也最稳的设计。
- **开发链路**：Vite `server.proxy` 与 `preview.proxy` 都把 `/api` 代理到 `http://localhost:8000`，浏览器同样只与 `localhost:5173` 通信，同源，无 CORS 问题。
- **直连后端端口（浏览器 → `http://localhost:8000`）**这一路径下 CORS 生效：后端 `CORSMiddleware` 允许 `settings.cors_origin_list`，默认 `http://localhost:5173,http://127.0.0.1:5173`；compose 中额外注入了 `http://localhost,http://127.0.0.1`（覆盖 nginx 的 80 端口直连场景）。`allow_credentials=True` 且未使用通配符 `*` 搭配 `allow_origins`，**不存在“凭证 + 通配符”的安全反模式**。实测预检：
  ```
  OPTIONS /api/v1/health  Origin: http://localhost:5173  →  200
  access-control-allow-origin: http://localhost:5173
  ```
- `expose_headers=["X-Request-ID"]` 已配置，前端可读取链路 ID（前提是后端确实返回该头 —— 见后端 P0-1）。

**发现的问题**

1. **【P1】`CORS_ORIGINS` 的默认值与 compose 注入值不一致。** `config.py` 默认是 `http://localhost:5173,http://127.0.0.1:5173`，compose 中是 `http://localhost:5173,http://127.0.0.1:5173,http://localhost,http://127.0.0.1`。本地裸跑 uvicorn（不经 compose）与容器内行为不同，容易误判。
2. **【P1】用户修改根 `.env` 中的 `CORS_ORIGINS` 后，若前端以非默认端口暴露（如 `FRONTEND_PORT=8080`），CORS 允许列表不会自动跟随**。虽然同源反代场景不需要 CORS，但一旦前端改为直连后端端口就会 403。
3. **【P2】`allow_credentials=True` 且允许明文 HTTP 源**，在多机部署场景下需注意把生产域名加入白名单，否则前端直连会被拒。
4. **【P3】前端 axios 未配置 `withCredentials`**，与后端 `allow_credentials=True` 不对称；当前接口不需要 Cookie，属可接受的不对称，但建议在文档中说明。
5. **【P3】CORS 预检响应缺少 `X-Request-ID`**（见后端 1.2）。

**问题影响**

- 1、2：跨环境行为不一致，属于“换个端口就坏”的典型来源。
- 3：多机部署时的安全与可用性边界。
- 4、5：轻微。

**修复建议**

- 统一 `CORS_ORIGINS` 的默认值来源（推荐让 compose 不注入该项、只由 `.env` 提供，或在 `.env.example` 中把两套地址都列全）。
- 在 README 中补一段“前端直连后端端口时的 CORS 白名单说明”，并明确同源反代场景无需 CORS。
- 生产环境用 `https` 源并收紧 `CORS_ALLOW_CREDENTIALS`。

---

## 5. `.env.example` 配置覆盖完整性

**检查文件**
`.env.example`、`frontend/.env.example`、`backend/app/core/config.py`

**检查结果**

- **做了逐键比对（大小写不敏感，因为 `case_sensitive=False`）**：`.env.example` 覆盖了 `Settings` 的 **28/28** 个可配置字段，唯一未以“生效键”形式出现的是 `DATABASE_URL` —— 它以注释形式给出（第 31-32 行）并说明了“设置后覆盖 `POSTGRES_*`”，属有意设计而非遗漏。
- `.env.example` 中另有 3 个键（`BACKEND_PORT`、`FRONTEND_PORT`、`VITE_API_BASE_URL`）不属于 `Settings`，但分别被 `docker-compose.yml` 的端口映射与前端构建参数消费 —— 属于**跨进程配置**，放在同一个文件里合理。
- `frontend/.env.example` 覆盖了全部 5 个 `VITE_` 变量（`VITE_APP_TITLE` / `VITE_API_BASE_URL` / `VITE_DEV_API_PROXY_TARGET` / `VITE_PORT` / `VITE_PREVIEW_PORT`），与 `env.d.ts` 的声明一一对应，无遗漏、无多余。
- 安全实践到位：`.env`、`.env.*` 被忽略、`.env.example` 通过 `!.env.example` 反向保留。实测 `git check-ignore -v`：`backend/.env` 与 `.env` 均被忽略，`.env.example` 与 `frontend/.env.example` 均未被忽略；`frontend/dist/` 亦被忽略。
- 注释说明了每个分组的用途，密码项明确标注 “Never commit a real password”。
- `DB_ECHO` / `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE` / `DB_POOL_PRE_PING` 与 `config.py` 字段一一对应。

**发现的问题**

1. **【P1】`.env.example` 位于仓库根，而 `config.py` 的 `env_file = (".env", "backend/.env")` 是相对当前工作目录解析的** —— 后端从 `backend/` 启动时实际读取 `backend/.env` 与 `backend/backend/.env`（均不存在），**根目录的 `.env` 永远不会被后端读到**。而 README 恰恰指导用户在 `backend/` 目录下执行 `Copy-Item ..\.env.example ..\.env`，即把 `.env` 放到**仓库根**。
   实测（在临时目录构造“根有 `.env`、CWD=backend”的同构场景）：
   ```
   cwd: .../backend
   password read: ''            ← 根 .env 的值未被读取
   app_name: 'AI Dev Platform' ← 回落到默认值
   => root .env NOT loaded
   ```
   进一步实测 pydantic-settings 的多文件语义：**后一个文件优先级更高**（`_env_file=(root, backend)` → 取 backend 的值；`_env_file=(backend, root)` → 取 root 的值）。
   **影响**：本地开发时 `POSTGRES_PASSWORD` 恒为空 → DSN 变成 `postgresql+asyncpg://postgres:@localhost:5432/...`；`alembic upgrade head` 会以空密码连接而失败；`ENVIRONMENT=production` 时会因缺密码直接拒绝启动。这是本轮**最影响日常开发体验**的问题。
2. **【P2】`.env.example` 中的 `SERVER_HOST` / `SERVER_PORT` 未被任何代码消费**（`settings.server_host/server_port` 定义了但 uvicorn 启动命令写死 `--host 0.0.0.0 --port 8000`），属于“看起来可配、实际无效”的配置项。
3. **【P2】`.env.example` 未标注 `DATABASE_URL` 与 `POSTGRES_*` 的互斥/优先级在 compose 中的差异**（compose 的 `migrate` 服务强制使用 `DATABASE_URL`，`backend` 服务不用）——文档与实际行为不一致，见 3.1。
4. **【P3】缺少 `POSTGRES_PASSWORD` 的强度提示**，示例值 `change-me-before-use` 虽然合理，但可再加一行“建议 ≥16 位且包含特殊字符（注意 compose 中的 URL 编码，见部署检查 3.1）”。
5. **【P3】`.env.example` 中缺少 `LANGGRAPH` 相关开关**（若按建议 2.2 将 langgraph 移出运行期依赖，可加 `INSTALL_WORKFLOW_EXTRA=false` 之类的开关）。

**问题影响**

- 1：**直接破坏本地开发与本地迁移流程**，且失败现象是“数据库认证失败”，与真实原因（配置文件没被读到）关联性弱，排查成本高。
- 2：误导性配置项。
- 3：文档与实现不一致。
- 4、5：文档完善度。

**修复建议**

- **首选修复 P0-1**：把 `env_file` 改为基于**项目根绝对路径**解析（不依赖 CWD）。已实测可行：`Path(__file__).resolve().parents[2] / ".env"`（`config.py` 位于 `backend/app/core/config.py`，`parents[2]` 即 `backend/`，再取父级即仓库根）能正确读到根 `.env`。建议实现为：
  ```python
  _BACKEND_DIR = Path(__file__).resolve().parents[2]      # backend/
  _PROJECT_ROOT = _BACKEND_DIR.parent                      # 仓库根
  env_file = (str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env"))
  ```
  顺序保持“后者优先”（实测语义），使 `backend/.env` 可覆盖根 `.env`，满足本地私有配置的常见需求。
- 或者：保持现有实现但修改 README，改为在 `backend/` 下执行 `Copy-Item .env.example .env`（同时把 `.env.example` 复制到 `backend/` 一份）—— 改动更小但与“根目录统一配置”的初衷冲突，且 compose 仍只读根 `.env`，会出现两处配置源。
- 删除或接线 `SERVER_HOST` / `SERVER_PORT`（推荐接线到 uvicorn 启动参数）。
- 在 `.env.example` 中补充说明 `DATABASE_URL` 与 compose 的关系，并补充密码特殊字符的注意事项。

---

# 四、问题汇总（按优先级）

| # | 级别 | 位置 | 问题 | 建议动作 |
| --- | --- | --- | --- | --- |
| 1 | P0 | `backend/app/core/config.py:23` | `env_file` 相对 CWD 解析，根 `.env` 永不被读取；本地开发密码恒为空 | 改为基于 `__file__` 的绝对路径 |
| 2 | P0 | `backend/app/core/exceptions.py` + `middleware.py` | 500 响应 `request_id="-"` 且无 `X-Request-ID` 头 | 从 `request.state` 取 ID；补响应头 |
| 3 | P1 | `docker-compose.yml:38-39` | `migrate` 裸拼 `DATABASE_URL`，密码含 `@` 等字符时解析错误，迁移容器失败并连锁阻断 backend 启动 | 删除该行，统一走 `POSTGRES_*` + `quote_plus` |
| 4 | P1 | `frontend/Dockerfile:10` | `npm install` 导致构建不可复现 | 改 `npm ci` |
| 5 | P1 | `frontend/src/main.ts:3-21` | Element Plus 全量引入 + 全量图标注册 → 主包 1,275 KB | 按需引入 + `manualChunks` |
| 6 | P1 | `backend/app/core/database.py` | 连接无超时，就绪探针可能长时间挂起 | `connect_args` + `asyncio.wait_for` |
| 7 | P1 | `backend/tests/test_exceptions.py` | `assert payload["request_id"]` 断言过弱，未拦截 P0-2 | 严格比对请求 ID 与响应头 |
| 8 | P1 | `backend/app/core/config.py:46` vs `docker-compose.yml:57` | `CORS_ORIGINS` 默认值两处不一致 | 统一来源 |
| 9 | P1 | `.env.example`（无 `backend/.env.example`） | 配置样例位置与实际读取位置不匹配 | 随 #1 一并修复或补样例文件 |
| 10 | P2 | `frontend/nginx.conf` | 无 `client_max_body_size`（1 MB 上限）、无 gzip | 补齐 |
| 11 | P2 | `docker-compose.yml:24-47` | `migrate` 与 `backend` 重复 `build` 块 → 构建两个相同镜像 | 共享 `image:` + YAML anchor |
| 12 | P2 | `backend/pyproject.toml:18` | `langgraph` 置于运行期依赖，牵入 langchain/langsmith/httpx2 | 移入 optional extra |
| 13 | P2 | `backend/Dockerfile:18` | 生产镜像携带 `tests/` | 移除或独立 stage |
| 14 | P2 | `backend/pyproject.toml` | `python-dotenv` 冗余依赖 | 移除 |
| 15 | P2 | `backend/tests/test_exceptions.py` | 独立 app 实例 + 测试路由未 `include_in_schema=False` | 复用 fixture |
| 16 | P2 | `backend/tests/` | 缺少 config/DSN/脱敏/生产校验的单测 | 新增 `test_config.py` |
| 17 | P2 | `frontend/src/api/client.ts:41` | `extractErrorMessage` 死代码；未提取后端 `request_id` | 删除或接入并扩展 |
| 18 | P3 | `backend/app/core/config.py:35-36`、`.env.example:7-8` | `SERVER_HOST`/`SERVER_PORT` 未接线 | 接线或删除 |
| 19 | P3 | `frontend/vite.config.ts:27` | `host: true` 暴露局域网；无 `strictPort`；`process.cwd()` 依赖启动目录 | 收敛配置 |
| 20 | P3 | `backend/alembic.ini` | `script_location` 相对 CWD，从根执行报晦涩错误 | 补文档或包装脚本 |
| 21 | P3 | `backend/app/core/middleware.py` + `main.py:69` | 预检响应缺 `X-Request-ID`；注释未说明 `ServerErrorMiddleware` 位置 | 补注释与头 |
| 22 | P3 | `frontend/src/components/layout/*.vue` | 图标依赖全局注册的隐式约定；`$route` 与 `useRoute()` 混用 | 显式 import + 统一写法 |

---

# 五、已执行的验证命令与真实结果

| 命令 | 结果 |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest -q` | **11 passed in 0.18s** |
| `backend/.venv/Scripts/ruff.exe check .` | **All checks passed!** |
| `backend/.venv/Scripts/python.exe -m pip wheel . --no-deps` | 成功产出 `ai_dev_platform_backend-0.1.0-py3-none-any.whl`（17,302 B） |
| `python -m alembic --version` / `alembic history`（cwd=backend） | `alembic 1.20.1` / `<base> -> 0001_baseline (head)` |
| `import alembic`（cwd=backend） | 解析到 `site-packages/alembic/__init__.py`，**无本地目录遮蔽** |
| DSN 编码实测（特殊字符密码） | `p@ss:w/rd #x` → `p%40ss%3Aw%2Frd+%23x`，反解一致 |
| `masked_database_uri` 实测 | 密码位替换为 `***` |
| 500 响应实测 | `request_id:"-"`，响应头无 `X-Request-ID`（已复现 P0-2） |
| CORS 预检实测 | 200，`access-control-allow-origin: http://localhost:5173`，无 `X-Request-ID` |
| `.env` 解析实测（根 `.env` + cwd=backend） | **根 `.env` 未被读取**（已复现 P0-1）；并确认多文件“后者优先”语义 |
| `make_url` 解析裸 DSN 实测 | 密码 `p@ss` → 解析出 host=`ss@db`（已复现部署 P1-3） |
| `npm ls --depth=0` | 全部声明依赖已安装，无 missing / extraneous |
| `npm run type-check` | 通过（`vue-tsc` + `tsc` 均无输出） |
| `npm run build` | 成功（6.61s，1696 modules），**主包 1,275.43 kB（gzip 412.93 kB），Vite 触发 >500 kB 告警** |
| `npm ci --dry-run` | 成功（锁文件与 `package.json` 同步，可安全切换） |
| `git check-ignore -v` | `.env` / `backend/.env` / `frontend/dist/` 被忽略；`.env.example` / `frontend/.env.example` 保留 |

---

# 六、本轮未验证项（如实标注）

1. **Docker 运行时未验证**：本机未安装 Docker Desktop（安装被环境安全策略拦截），因此 `docker compose up -d --build`、四个服务的实际启动顺序、nginx 反代、PostgreSQL 真实往返、`migrate` 容器在真实库上的执行，**均未实际运行过**。所有关于 compose 的结论均来自文件解析与语义推理，其中 #3 已通过 DSN 解析实测间接证实。
2. **真实 PostgreSQL 16 往返未验证**：仅用 SQLite 替身完成迁移冒烟与就绪探针测试；`asyncpg` 在真实 PG 上的连接池、字符集、`alembic upgrade head` 落库未实测。
3. **Python 3.11 运行时未验证**：本机 venv 为 3.13.14，Dockerfile 用 3.11-slim，3.11 下的行为差异未实测。
4. **生产构建产物未在浏览器中回归**：本次只验证了 `npm run build` 成功，未重新启动 dev server 做页面级回归（上一轮迭代已验证过渲染正常，本轮未改动前端源码）。
5. **`pip install .` 的完整依赖解析未在干净环境执行**：`pip wheel --no-deps` 验证了打包链路，但未验证全量依赖在纯净镜像中的可解析性（尤其是 `langgraph` 相关的传递依赖与 cp311 平台的 wheel 可用性）。

---

*本报告仅做检查，未修改任何工程代码；唯一新增文件为本报告 `docs/iteration1_code_review.md`。*
