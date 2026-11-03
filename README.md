# AI Dev Platform

前后端分离、模块化单体架构的基础工程。当前版本完成工程骨架与通用能力（配置、日志、异常、跨域、API 文档、健康检查、数据库迁移链路、容器化），**AI Agent 业务功能尚未实现**。

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
│   │   │   ├── deps.py             # 共享依赖
│   │   │   └── v1/
│   │   │       ├── router.py       # v1 路由聚合
│   │   │       └── endpoints/      # health.py 等端点模块
│   │   ├── core/                   # config / logging / exceptions / database / middleware
│   │   ├── models/                 # SQLAlchemy 声明式模型与 Base
│   │   ├── schemas/                # Pydantic 请求响应模型
│   │   ├── services/               # 业务服务层
│   │   ├── workflows/              # LangGraph 工作流抽象与注册表
│   │   └── agents/                 # Agent 目录（仅占位）
│   ├── alembic/                    # 迁移脚本与 versions/
│   ├── alembic.ini
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
python -m alembic upgrade head
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

## 数据库迁移

```powershell
cd backend
python -m alembic upgrade head                 # 应用迁移
python -m alembic downgrade -1                 # 回退一版
python -m alembic revision --autogenerate -m "add xxx table"   # 生成迁移
python -m alembic history                       # 查看版本链
python -m alembic upgrade head --sql            # 离线渲染 SQL，不连库
```

迁移的 DSN 始终从环境变量读取，`alembic.ini` 中不保存任何凭据。

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

## 当前阶段与后续

已完成：工程骨架、配置与日志、统一异常、跨域、API 文档、健康检查、Alembic 迁移链路、前端基础布局、容器化。

未实现（后续阶段）：领域模型与数据表、AI Agent 与工作流实现、认证与权限、CI/CD。
