# AI Dev Platform

前后端分离、模块化单体架构的基础工程。当前版本完成工程骨架与通用能力（配置、日志、异常、跨域、API 文档、健康检查、数据库迁移链路、容器化），并实现了**数据库设计与项目管理模块**（项目 / 任务 / 工作流实例 / 产物 / 审批记录五张业务表与对应 REST API），**AI Agent 业务功能尚未实现**。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11、FastAPI、SQLAlchemy 2.x（异步）、Alembic、Pydantic 2、Uvicorn |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Axios |
| 数据库 | PostgreSQL 16 |
| 工作流 | LangGraph（仅保留目录与抽象，尚未接入实际 Agent） |
| 部署 | Docker Compose（后端 + 前端 + PostgreSQL） |

## 目录结构

```
ai-dev-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                 # 应用工厂、生命周期、中间件与路由装配
│   │   ├── api/
│   │   │   ├── deps.py             # 共享依赖（分页参数等）
│   │   │   └── v1/
│   │   │       ├── router.py       # v1 路由聚合
│   │   │       └── endpoints/      # health.py / projects.py / tasks.py
│   │   ├── core/                   # config / logging / exceptions / database / middleware
│   │   ├── models/                 # SQLAlchemy 声明式模型与 Base（enums / project / task / workflow / artifact / approval）
│   │   ├── schemas/                # Pydantic 请求响应模型（common 分页信封 / project / task / workflow / artifact / approval）
│   │   ├── services/               # 业务服务层（projects / tasks / artifacts / approvals）
│   │   ├── workflows/              # LangGraph 工作流抽象与注册表
│   │   └── agents/                 # Agent 目录（仅占位）
│   ├── alembic/                    # 迁移脚本与 versions/
│   ├── alembic.ini
│   ├── scripts/                    # 跨平台数据库初始化脚本（init_db.py / .sh / .ps1）
│   ├── tests/                      # pytest 测试
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/                    # axios 客户端与接口封装
│   │   ├── components/layout/      # 侧边导航、顶部导航
│   │   ├── views/                  # 首页 / 工作台 / 404
│   │   ├── router/                 # Vue Router
│   │   ├── stores/                 # Pinia
│   │   ├── App.vue
│   │   └── main.ts
│   ├── nginx.conf
│   ├── vite.config.ts
│   └── Dockerfile
├── docs/
│   └── iteration2_db_design.md     # 数据库设计与实施计划（第二轮）
├── docker-compose.yml
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

## 快速开始

### 方式一：Docker Compose（推荐，Linux / Windows 均可）

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
# 务必修改 .env 中的 POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps
```

启动后：

- 前端首页：http://localhost/ （默认端口 80，可用 `FRONTEND_PORT` 修改）
- 后端健康检查：http://localhost:8000/api/v1/health
- API 文档：http://localhost:8000/docs ，ReDoc：http://localhost:8000/redoc

`migrate` 服务会在后端启动前自动执行 `alembic upgrade head`。停止并清理：

```bash
docker compose down          # 保留数据卷
docker compose down -v       # 同时删除 PostgreSQL 数据卷
```

### 方式二：本地开发（Windows）

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item ..\.env.example ..\.env     # 按需修改 POSTGRES_PASSWORD 等
python -m alembic upgrade head        # 或 .\scripts\init_db.ps1（建库 + 迁移一步到位）
python -m uvicorn app.main:app --reload --port 8000
```

> 后端按固定顺序读取两个 dotenv 文件：仓库根目录的 `.env`，然后是 `backend/.env`（后者覆盖前者）。两者的路径都是绝对路径，因此从任意工作目录启动都能生效，上面把 `.env` 复制到仓库根即可。

前端（另开一个终端）：

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

- 前端开发服务器：http://localhost:5173
- `/api` 请求由 Vite 代理到 `http://localhost:8000`（见 `frontend/.env.local` 的 `VITE_DEV_API_PROXY_TARGET`）

> Windows 下若 PowerShell 禁止执行脚本，可用 `.\.venv\Scripts\activate.bat` 激活虚拟环境，或直接调用 `.\.venv\Scripts\python.exe -m uvicorn ...`。

## 环境变量

所有配置来自环境变量，代码中不硬编码任何密码。完整清单见 [.env.example](./.env.example)。

dotenv 加载顺序（后端）：`<仓库根>/.env` → `<仓库根>/backend/.env`，后者覆盖前者；路径按绝对路径解析，与启动目录无关。`docker compose` 则以项目根目录的 `.env` 作为变量替换来源。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` / `APP_VERSION` | AI Dev Platform / 0.1.0 | 服务标识 |
| `ENVIRONMENT` | development | `development` / `production` |
| `DEBUG` | false | 生产环境必须为 false |
| `API_V1_PREFIX` | /api/v1 | API 版本前缀 |
| `LOG_LEVEL` / `LOG_JSON` | INFO / false | 日志级别与 JSON 输出 |
| `CORS_ORIGINS` | 本地前端地址 | 逗号分隔的允许来源 |
| `POSTGRES_HOST` / `POSTGRES_PORT` | localhost / 5432 | 数据库地址 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | postgres / 空 / ai_dev_platform | 数据库凭据 |
| `DATABASE_URL` | 空 | 完整 DSN，设置后覆盖上面的 `POSTGRES_*` |
| `DB_ECHO` / `DB_POOL_*` | false / 5 / 10 / … | 连接池与 SQL 打印 |

后端容器通过 `DATABASE_URL` 或 `POSTGRES_*` 指向 Compose 内的 `db` 服务；本地开发时 `POSTGRES_HOST=localhost` 指向本机或容器映射出的 5432 端口。

## 数据库初始化与迁移

### 一键初始化（推荐）

脚本负责「建库（若不存在）+ 升级到最新版本」，DSN 全部来自环境变量，脚本里不含任何凭据。

```bash
# Linux / macOS / Git Bash
cd backend
./scripts/init_db.sh

# Windows PowerShell
cd backend
.\scripts\init_db.ps1
```

常用参数：

```bash
./scripts/init_db.sh --create-db        # 只建库，不执行迁移
./scripts/init_db.sh --reset            # 先 downgrade base 再 upgrade head（会清空表）
./scripts/init_db.sh --revision 0001    # 升级到指定版本
```

对应的跨平台入口是 `python scripts/init_db.py`（参数与上面一致），脚本会自动优先使用 `backend/.venv` 中的解释器，也可用环境变量 `PYTHON` 指定其他解释器。

### 直接使用 Alembic

```powershell
cd backend
python -m alembic upgrade head                 # 应用迁移
python -m alembic downgrade -1                 # 回退一版
python -m alembic downgrade base               # 回退到初始版本（删除全部业务表）
python -m alembic revision --autogenerate -m "add xxx table"   # 生成迁移
python -m alembic history                       # 查看版本链
python -m alembic current                       # 查看当前版本
python -m alembic check                         # 检查模型与迁移是否漂移
python -m alembic upgrade head --sql            # 离线渲染 SQL，不连库
```

迁移的 DSN 始终从环境变量读取，`alembic.ini` 中不保存任何凭据。

当前版本链：

| 版本 | 说明 |
| --- | --- |
| `0001_baseline` | 仅锚定版本链，不建表 |
| `0002_project_management` | 创建 `projects` / `development_tasks` / `workflow_instances` / `artifacts` / `approval_records` |

表结构与索引设计详见 [docs/iteration2_db_design.md](./docs/iteration2_db_design.md)。

## 测试与检查

```powershell
# 后端
cd backend
python -m pytest -q
python -m ruff check .

# 前端
cd frontend
npm run type-check
npm run build
```

后端测试默认跑在一次性 SQLite 文件上（用真实的 Alembic 迁移建表，而不是 `create_all`），不会碰到开发者自己的数据库。想用真实 PostgreSQL 跑同一套用例时，指定 `TEST_DATABASE_URL`：

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_dev_platform_test \
    python -m pytest -q
```

## API 约定

- 版本前缀：`/api/v1`
- 健康检查：`GET /api/v1/health`（不依赖数据库）
- 就绪检查：`GET /api/v1/health/ready`（探测数据库，不可用时返回 503）
- 错误响应统一格式：

```json
{
  "code": "NOT_FOUND",
  "message": "human readable message",
  "detail": null,
  "request_id": "c1f3...",
  "timestamp": "2026-11-03T10:00:00+00:00"
}
```

每个响应都带 `X-Request-ID` 头，可用该值在日志中定位完整请求链路。

### 项目管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/projects` | 创建项目，201 |
| `GET` | `/api/v1/projects` | 分页查询，支持 `status`、`keyword` 过滤 |
| `GET` | `/api/v1/projects/{project_id}` | 项目详情（含任务数） |
| `PUT` | `/api/v1/projects/{project_id}` | 局部更新（仅提交需要变更的字段） |
| `DELETE` | `/api/v1/projects/{project_id}` | 软删除项目及其任务，204 |
| `GET` | `/api/v1/projects/{project_id}/tasks` | 项目下的任务列表 |
| `POST` | `/api/v1/tasks` | 创建任务，必须给出 `project_id`，201 |
| `GET` | `/api/v1/tasks` | 分页查询，支持 `project_id`、`status`、`priority`、`keyword` |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情 |
| `PUT` | `/api/v1/tasks/{task_id}` | 局部更新 |

分页参数为 `page`（从 1 开始）与 `page_size`（1–100，默认 20），列表响应统一为：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0
}
```

## 当前阶段与后续

已完成：工程骨架、配置与日志、统一异常、跨域、API 文档、健康检查、Alembic 迁移链路、前端基础布局、容器化；数据库设计与项目管理模块（5 张业务表、迁移脚本、项目/任务 REST API、分页与参数校验、pytest 用例）。

未实现（后续阶段）：`workflow_instances` / `artifacts` / `approval_records` 的对外 HTTP 接口（表与服务层已就绪）、前端项目管理页面、AI Agent 与工作流实现、认证与权限、CI/CD。
