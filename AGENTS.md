# AGENTS.md

本文件是本仓库中 AI 助手与人类协作者的共同工作约定。修改代码前请先阅读本文件与 [README.md](./README.md)。

## 项目定位

`ai-dev-platform` 是前后端分离、模块化单体架构的基础工程。当前阶段只包含工程骨架与通用能力（配置、日志、异常、跨域、文档、健康检查、迁移链路、容器化），**不包含 AI Agent 业务功能**。

未经明确需求，不要提前实现 Agent、工作流图、Prompt 或任何领域业务逻辑。

## 目录职责与依赖方向

```
api  →  services  →  models  →  core
```

| 目录 | 职责 | 约束 |
| --- | --- | --- |
| `backend/app/api` | 路由、参数校验、HTTP 语义 | 只做编排，不写业务逻辑；不得直接写 SQL |
| `backend/app/core` | 配置、日志、异常、数据库引擎、中间件 | 不得依赖业务模块，不引入领域概念 |
| `backend/app/models` | SQLAlchemy 2.x 声明式模型 | 统一继承 `app/models/base.py` 的 `Base` |
| `backend/app/schemas` | Pydantic 2 请求/响应模型 | 与 ORM 模型分离，不直接返回 ORM 实例 |
| `backend/app/services` | 业务逻辑 | 不依赖 FastAPI 的 `Request` 对象 |
| `backend/app/workflows` | LangGraph 工作流抽象与注册表 | 通过注册表暴露，不在 API 层直接构图 |
| `backend/app/agents` | Agent 目录（占位） | 当前为空，不放业务实现 |
| `frontend/src/api` | HTTP 客户端与接口封装 | 只做请求，不含 UI 逻辑 |
| `frontend/src/stores` | Pinia 状态 | 只放跨页面共享状态 |
| `frontend/src/views` | 路由级页面 | 不直接写 axios 调用，走 `api/` |
| `frontend/src/components` | 可复用组件 | 具名组件按目录组织 |

## 代码风格

- Python：Ruff（行宽 100，`py311` 目标版本），双引号字符串，完整类型注解，模块与函数写 docstring。
- TypeScript：`strict: true`，`@/` 别名指向 `src/`，`<script setup lang="ts">`，2 空格缩进，单引号字符串。
- 提交前必须通过：`python -m ruff check .`（后端）、`npm run type-check`（前端）。

## 配置与环境变量

- 所有可变配置来自环境变量，代码中**不得硬编码数据库密码、令牌或任何密钥**。
- 新增配置项时，同步更新：`.env.example`、`docker-compose.yml`（容器需要时）、`README.md` 的环境变量表。
- `.env` 已在 `.gitignore` 中，只提交 `.env.example`。
- 数据库 DSN 由 `POSTGRES_*` 拼装，`DATABASE_URL` 可整体覆盖；日志中只允许出现脱敏后的 DSN（`settings.masked_database_uri`）。

## 数据库与迁移

- 表结构变更必须通过 Alembic 迁移提交：先改 `app/models/`，再执行 `python -m alembic revision --autogenerate -m "..."`，最后人工检查生成的迁移脚本。
- 不要手写 `alembic/versions/` 中的迁移来绕过模型定义。
- 迁移脚本必须同时实现 `upgrade()` 与 `downgrade()`。

## 接口约定

- 路由统一挂载在 `/api/v1` 前缀下，新模块在 `app/api/v1/router.py` 注册。
- 新增接口需同步提供：Pydantic schema（`app/schemas/`）、业务逻辑（`app/services/`）、pytest 测试（`backend/tests/`）。
- 错误统一走 `app/core/exceptions.py` 的异常体系，禁止在端点里直接返回裸 `dict` 错误。
- 所有响应带 `X-Request-ID`，日志与错误响应体都包含 `request_id`。

## 测试要求

- 后端：`python -m pytest -q` 必须全绿；新增接口至少覆盖成功路径与错误路径。
- 前端：改动后至少通过 `npm run type-check`；涉及构建配置时还需 `npm run build`。
- 不得在未真实运行命令的情况下声称测试通过；无法执行的检查要在交付说明中如实标注为“未验证”。

## 跨平台约定

- 仓库需同时支持 Windows 开发环境与 Linux Docker 环境。
- 文档中的命令优先写成跨平台形式（`python -m pytest`、`python -m alembic`、`python -m uvicorn`），避免裸命令依赖 shell PATH。
- 不要引入只在单一平台可用的脚本；需要时提供 PowerShell 与 Bash 两种写法。

## 禁止事项

- 禁止提交 `.env`、真实凭据或含密钥的配置文件。
- 禁止在没有明确需求时实现 AI Agent、工作流编排或领域业务表。
- 禁止在 `core` 层引入业务概念，或在 `api` 层直接访问数据库表。
- 禁止删除或改写既有异常响应格式与健康检查契约（`/api/v1/health`）。
