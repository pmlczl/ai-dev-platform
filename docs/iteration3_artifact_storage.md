# 任务 3：中间文件管理模块 — 设计与实施计划

> 状态：**已实施**（设计评审通过后按本文档实现，验证结果见第 13 节）
> 基线：任务 2「数据库设计与项目管理」已完成（`develop` @ `0a89d77`）
> 约定来源：`AGENTS.md`（依赖方向 `api → services → models → core`）

---

## 1. 目标与边界

### 1.1 本次要做

- 真实文件上传与下载（multipart），文件落盘到**独立 storage 根目录**，数据库只保存元数据与相对路径。
- 5 张业务表中的 `artifacts` 表扩展为真正的文件元数据表：所属项目/任务、阶段、版本、SHA256、大小、类型、审核状态、创建时间。
- 版本管理：同一逻辑路径再次上传即生成新版本，旧版本自动置为 `superseded`，**任何历史版本都不会被覆盖**。
- 文件状态管理：审核状态机（上传 → `pending`，产生新版本 → 旧版 `superseded`，人工审核 → `approved` / `rejected`）。
- 安全防护：文件类型白名单（含内容嗅探）、大小上限、路径穿越防护、文件名冲突处理、禁止覆盖历史版本。
- 5 个 REST 端点（见第 6 节）+ pytest 覆盖上传、下载、版本变更。

### 1.2 本次不做（避免越界）

- 不接对象存储（S3 / OSS / MinIO），只做本地磁盘；抽象层留接口，但本次不实现云后端。
- 不做在线预览、在线编辑、文件重命名、文件删除 API（不在端点清单内）。
- 不做病毒扫描（依赖外部引擎，本机无法安装）；只做扩展名白名单 + 魔数嗅探这一层。
- 不做鉴权（当前平台无用户体系，`created_by` / `reviewed_by` 仍是客户端自述的审计字段）。
- 不做前端上传页面。

---

## 2. 现状盘点

上一轮已经存在的部分（可直接复用，不重复造）：

| 已有 | 位置 | 说明 |
| --- | --- | --- |
| `artifacts` 表 | `app/models/artifact.py` | 已有 `project_id` / `task_id` / `relative_path` / `version` / `sha256` / `file_type` / `size_bytes` / `review_status` / `reviewed_by` / `reviewed_at` / `created_by`；唯一约束 `(project_id, relative_path, version)` |
| 元数据服务 | `app/services/artifacts.py` | `register_artifact`（登记元数据 + 旧版 superseded）、`list_artifacts`（按项目列全部版本） |
| Schema | `app/schemas/artifact.py` | `ArtifactRegister` / `ArtifactRead` |
| 枚举 | `app/models/enums.py` | `ArtifactReviewStatus`（pending / approved / rejected / superseded） |

**缺口**：没有真实文件、没有磁盘存储、没有 HTTP 端点、没有上传时的内容校验、`file_type` 语义未定、没有「阶段」字段、没有版本号之外的文件名信息、没有审核动作入口。

因此本次**扩展 `artifacts` 表**而不是新建 `files` 表——字段语义完全吻合（路径 + 版本 + 哈希 + 类型 + 审核状态 + 创建时间正是需求原文），且 `approval_records.target_type = 'artifact'` 能继续指向真实文件。

---

## 3. 存储模型与路径设计

### 3.1 两个路径概念（必须区分）

| 概念 | 字段 | 含义 | 示例 |
| --- | --- | --- | --- |
| 逻辑路径 | `relative_path`（已有） | 调用方给出的、**项目内**的相对路径，是「同一个文件」的身份标识 | `docs/prd.md` |
| 物理路径 | `storage_path`（新增） | 文件在 storage 根目录下的**相对**路径，定位磁盘文件 | `projects/<pid>/tasks/<tid>/v2/prd.md` |

为什么要两个：版本唯一性由逻辑路径决定（`(project_id, relative_path, version)` 唯一约束已存在），而磁盘定位需要物理路径。两者分离后，同一逻辑路径的 v1/v2 落在不同目录，历史版本天然不可能被覆盖。

数据库**不存绝对路径**，只存相对路径；storage 根目录由环境变量配置，根目录变了历史数据依然可用。

### 3.2 物理布局

```
<STORAGE_ROOT>/
├── projects/<project_id>/tasks/<task_id>/v<version>/<安全文件名>
└── .tmp/                      # 上传过程中的临时文件（同一文件系统，便于原子改名）
```

- 文件名入库前经过净化：只取 basename、剥离路径分隔符、拒绝 `..` / 空字节 / 控制字符 / Windows 保留名、长度截断。
- 落盘使用 `open(path, "xb")` **独占创建**：文件已存在会直接失败，从机制上杜绝覆盖。
- `storage_path` 加唯一约束，作为最后一道防线。

### 3.3 阶段（stage）

需求要求「记录文件所属阶段」。`workflow_instances.current_step` 是运行时状态，不适合作为文件属性，因此在 `artifacts` 上新增 `stage` 字段：

| 值 | 含义 |
| --- | --- |
| `design` | 设计阶段（PRD、架构、接口稿） |
| `development` | 开发阶段（代码、脚本、配置） |
| `testing` | 测试阶段（用例、测试报告） |
| `delivery` | 交付阶段（部署手册、验收报告） |
| `other` | 其他 / 未分类 |

与既有枚举风格一致：`StrEnum` + `VARCHAR(32)` + `CHECK` 约束（不用原生 enum，新增值只需改约束）。

---

## 4. 表结构变更（迁移 `0003_artifact_storage`）

在 `artifacts` 表上：

| 变更 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| 新增 | `stage` | `VARCHAR(32) NOT NULL DEFAULT 'development'` | 所属阶段，`CHECK` 限定取值 |
| 新增 | `original_filename` | `VARCHAR(255) NOT NULL` | 上传时的原始文件名，用于展示与下载时的 `Content-Disposition` |
| 新增 | `storage_path` | `VARCHAR(500) NOT NULL` | 相对 storage 根目录的物理路径，**唯一** |
| 修改语义 | `file_type` | `VARCHAR(100) NOT NULL` | 由「调用方自述」改为**服务端根据扩展名推导**的规范 MIME（如 `application/pdf`）；不信任客户端的 `Content-Type` 头 |
| 保持 | `size_bytes` | `BigInteger NULL` | 保持可空：改成 `NOT NULL` 需要数据迁移，而既有表可能已有行；上传接口保证一定有值 |
| 保持 | `sha256` / `version` / `review_status` / `reviewed_by` / `reviewed_at` / `created_by` / `created_at` / `updated_at` | | 与需求一一对应，无需改动 |

约束与索引新增：

- `CHECK (stage IN ('design','development','testing','delivery','other'))`
- `UNIQUE (storage_path)` —— 物理路径唯一
- `INDEX (project_id, task_id)` —— 任务级列表查询
- `INDEX (project_id, relative_path, version)` —— 版本查询（现有唯一约束已隐含前两列，可复用）
- `INDEX (stage)` —— 按阶段过滤

迁移流程遵守 `AGENTS.md`：先改 `app/models/artifact.py`，再 `python -m alembic revision --autogenerate -m "..."`，最后**人工逐行检查**生成的 `upgrade()` / `downgrade()`。

实施时对自动生成的脚本做了四处人工修正（详见第 13 节）：`stage` 需要 server default、`stage` 的 CHECK 约束与 `storage_path` 的唯一约束在 SQLite 上必须走 batch 模式、约束名要用 `op.f()` 固定下来。

---

## 5. 安全设计

### 5.1 类型白名单 + 内容嗅探

**双保险**：扩展名决定「允许的类型」，文件内容决定「是不是真的这种类型」。只信扩展名等于没防伪装（把 `evil.exe` 改名成 `spec.pdf` 就能混进来）。

| 扩展名 | 规范 MIME | 内容校验 |
| --- | --- | --- |
| `.pdf` | `application/pdf` | 文件头为 `%PDF-` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | ZIP 头 `PK\x03\x04`，且压缩包内含 `word/document.xml` |
| `.md` / `.markdown` | `text/markdown` | UTF-8 可解码，且不含 NUL 字节 |
| `.txt` | `text/plain` | UTF-8 可解码，且不含 NUL 字节 |
| `.json` | `application/json` | UTF-8 可解码，且能被 `json.loads` 解析 |
| `.yaml` / `.yml` | `application/yaml` | UTF-8 可解码，且不含 NUL 字节 |

不在白名单 → **422**；内容与扩展名不符 → **422**。

### 5.2 大小限制

- 双重检查：先读 `UploadFile.size`（客户端声明，仅作快速失败），再在**流式写入过程中累计真实字节数**，超限立刻中止并删除临时文件。
- 上限值来自环境变量，默认 50 MB。
- 超限 → **413**（新增 `ErrorCode.PAYLOAD_TOO_LARGE`）。

### 5.3 路径穿越防护

| 攻击面 | 处理 |
| --- | --- |
| 上传文件名 `../../etc/passwd.md` | **直接拒绝（422）**：文件名中只要出现路径分隔符或 `..` 段就报错，而不是静默截断——合法上传不需要这种名字，静默修复会掩盖越界尝试。控制字符、Windows 保留名同样拒绝 |
| 调用方传入的 `relative_path` | 拒绝绝对路径、拒绝含 `..` 的路径段、拒绝反斜杠；规范化后仍须落在项目内 |
| 下载时读取磁盘 | 由 `storage_path` 定位文件，`resolve()` 后**校验仍在 `STORAGE_ROOT` 之内**，否则拒绝服务 |
| 逻辑路径超长 | 上限 500 字符，超出 → 422 |

### 5.4 文件名冲突与「禁止覆盖历史版本」

四道防线：

1. 物理路径带 `v<version>` 目录段，不同版本天然不同目录。
2. `UNIQUE (project_id, relative_path, version)`：同一逻辑路径不能有两个相同版本号。
3. `UNIQUE (storage_path)`：物理路径不能重复。
4. 落盘用 `open(..., "xb")` 独占创建：目标文件存在就失败。
5. 文件从临时目录就位时用**硬链接**：`os.link` 在目标已存在时直接失败，检查与改名是同一个原子步骤，不存在检查与写入之间的竞态窗口（文件系统不支持硬链接时退化为「先检查再移动」）。

上传同名文件 → 自动生成下一个版本号，旧版本 `review_status` 置 `superseded`，**旧文件在磁盘上原样保留**。

并发上传同一逻辑路径时，两个请求可能算出同一个版本号 → 靠唯一约束拦截，其中一个自动重试下一个版本；仍冲突则 **409**。

---

## 6. API 设计

统一前缀 `/api/v1`，错误沿用现有信封 `{code, message, detail, request_id, timestamp}`。

| 方法 | 路径 | 请求体 | 成功码 | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/tasks/{task_id}/artifacts` | multipart：`file`（必填）、`relative_path`（可选）、`stage`（可选） | 201 | 上传文件；项目由任务推导，客户端无法伪造归属 |
| GET | `/api/v1/artifacts/{artifact_id}` | — | 200 | 元数据查询，返回全部元信息（含 sha256、版本、阶段、审核状态） |
| GET | `/api/v1/artifacts/{artifact_id}/download` | — | 200 | 下载文件流，`Content-Disposition` 用原始文件名（RFC 5987 编码） |
| GET | `/api/v1/tasks/{task_id}/artifacts` | query：`page` / `page_size` / `review_status` / `stage` / `keyword` | 200 | 任务下的文件列表，分页信封 |
| POST | `/api/v1/artifacts/{artifact_id}/revisions` | multipart：`file`（必填）、`stage`（可选） | 201 | 为已有文件创建新版本，旧版本转 `superseded` |

补充：`POST /api/v1/artifacts/{artifact_id}/review`，用于把文件状态推进到 `approved` / `rejected` 并记录 `reviewed_by` / `reviewed_at`（模型里已有这两个字段，不提供入口将永远为 NULL）。审核动作会**同时**向 `approval_records` 追加一条 `target_type = artifact` 的记录，`comment` 落在那里，审核轨迹因此可追溯。

### 错误语义

| 场景 | 状态码 | code |
| --- | --- | --- |
| 任务 / 文件不存在 | 404 | `NOT_FOUND` |
| 类型不在白名单、内容与类型不符、文件名非法、`relative_path` 非法 | 422 | `VALIDATION_ERROR` |
| 文件超过大小上限 | 413 | `PAYLOAD_TOO_LARGE`（新增） |
| 版本号冲突（并发） | 409 | `CONFLICT` |

---

## 7. 配置与依赖

### 7.1 新增环境变量（同步更新 `.env.example` / `docker-compose.yml` / `README.md`）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `STORAGE_ROOT` | `backend/storage` | 独立 storage 根目录，按绝对路径解析 |
| `STORAGE_MAX_UPLOAD_SIZE` | `52428800`（50 MB） | 单文件大小上限（字节） |
| `STORAGE_ALLOWED_EXTENSIONS` | `pdf,docx,md,txt,json,yaml,yml` | 允许的扩展名白名单 |

`storage/` 目录加入 `.gitignore`，不进版本库。

### 7.2 新增依赖

`python-multipart` —— FastAPI 的 `UploadFile` / `Form` 依赖它，**当前未安装**，必须补上（`pyproject.toml` + `pip install`）。

---

## 8. 代码结构

```
backend/app/
├── core/
│   └── storage.py               # 新增：通用文件存储原语（不含任何研发领域概念）
│       ├── storage_root()       #   解析并创建 STORAGE_ROOT
│       ├── sanitize_filename()  #   文件名净化
│       ├── normalize_relative_path()  # 逻辑路径规范化 + 穿越校验
│       ├── build_storage_path() #   由 (project, task, logical, version) 推导物理路径
│       ├── resolve_within_root()#   resolve 后校验仍在根目录内
│       ├── write_stream_exclusive() # 独占创建写入（xb），禁止覆盖
│       └── sha256_of_file()     #   流式 SHA256
├── services/
│   ├── artifact_types.py        # 新增：扩展名白名单 → MIME 映射 + 内容嗅探
│   └── artifacts.py             # 扩展：上传 / 下载 / 新版本 / 列表 / 审核状态机
├── schemas/artifact.py          # 扩展：ArtifactRead 增加 stage / original_filename / storage_path
├── models/
│   ├── enums.py                 # 扩展：ArtifactStage
│   └── artifact.py              # 扩展：stage / original_filename / storage_path + 约束索引
└── api/v1/endpoints/
    └── artifacts.py             # 新增：5 个端点
```

**分层约束**：`core/storage.py` 只放通用文件能力，**不出现 pdf / docx 这类领域概念**；类型白名单与嗅探放在 `services/artifact_types.py`；端点只做编排，不直接碰数据库表。

---

## 9. 迁移与验证方案

- 迁移：`0003_artifact_storage`（`down_revision = "0002_project_management"`），autogenerate 后人工检查，SQLite 与 PostgreSQL 方言双验证（`--sql` 离线渲染 + `alembic check`）。
- 测试库沿用现有 `conftest.py`：**跑真实迁移脚本**建表，不碰开发者数据库。
- storage 根目录在测试会话内指向临时目录（与 `DATABASE_URL` 同样在导入应用前注入环境变量），测试结束删除，不留垃圾。

---

## 10. 测试方案

| 编号 | 用例 | 期望 |
| --- | --- | --- |
| U1 | 上传 `.md` 文件 | 201；返回 `sha256` 与本地计算一致、`size_bytes` 正确、`version=1`、`review_status=pending`、`stage` 取传入值 |
| U2 | 上传后检查磁盘 | 目标文件真实存在，内容与上传字节完全一致；数据库中无绝对路径 |
| U3 | 上传 `.exe` | 422（类型不在白名单） |
| U4 | 把二进制内容伪装成 `.pdf` | 422（魔数嗅探不通过） |
| U5 | 上传超过大小上限的文件 | 413，且磁盘上没有残留文件 |
| U6 | 文件名含 `../../` 路径穿越 | 422，且 storage 内没有越界文件 |
| U7 | `relative_path` 含 `..` | 422 |
| U8 | 向不存在的任务上传 | 404 |
| U9 | 下载已上传文件 | 200，字节与上传内容完全一致，`Content-Disposition` 含原始文件名 |
| U10 | 下载不存在的文件 / 元数据存在但磁盘文件被删 | 404 |
| U11 | 同一任务、同一逻辑路径上传两次 | `version` 为 1 和 2；旧版 `review_status` 变 `superseded`；两个版本文件都还在磁盘上，内容互不相同（**未覆盖**） |
| U12 | `POST /artifacts/{id}/revisions` | 201，生成 v2，v1 转 `superseded` |
| U13 | 任务文件列表 | 分页信封字段完整；可按 `review_status` / `stage` 过滤 |
| U14 | 审核状态流转（若确认新增 review 端点） | `approved` / `rejected` 写入，`reviewed_by` / `reviewed_at` 被填充 |

---

## 11. 实施步骤

1. 依赖（`python-multipart`）+ 配置项 + `.env.example` / `docker-compose.yml` / `README.md` / `.gitignore`
2. `app/core/storage.py`（通用存储原语）
3. `app/services/artifact_types.py`（白名单 + 嗅探）
4. `app/models/artifact.py` + `enums.py` 扩展，`app/schemas/artifact.py` 扩展
5. 生成 `0003_artifact_storage` 迁移并人工检查
6. `app/services/artifacts.py` 扩展（上传 / 下载 / 新版本 / 列表 / 审核）
7. `app/api/v1/endpoints/artifacts.py` + 注册路由
8. 测试基建（conftest 注入临时 storage 根目录）+ 14 组用例
9. 全量验证：ruff / pytest / 迁移往返 / `alembic check` / PG 方言 DDL / HTTP 冒烟
10. 文档更新（`README.md` + 本文档状态改为「已实施」）+ 提交推送

---

## 12. 已确认决策点

评审时确认的五个决策，实现与本文档保持一致：

1. **文件类型白名单**：定为 `pdf`、`docx`、`md`、`markdown`、`txt`、`json`、`yaml`、`yml` 七个扩展名（八个别名）。每种都配内容嗅探：PDF 看 `%PDF-` 文件头，DOCX 校验 ZIP 结构且内含 `word/document.xml`，JSON 必须能被解析，MD/TXT/YAML 必须能按 UTF-8 解码且不含 NUL 字节。不加入旧版 Office 格式，也不放开全类型。
2. **单文件大小上限**：默认 **50 MB**，通过 `STORAGE_MAX_UPLOAD_SIZE` 可调；流式写入过程中累计真实字节数，超限立即中止并清理临时文件。
3. **`relative_path` 语义**：**由调用方可选传入**（如 `docs/prd.md`），不传则默认取上传时的文件名。同一逻辑路径再次上传即生成新版本。
4. **人工审核动作**：**额外提供** `POST /api/v1/artifacts/{artifact_id}/review`，把状态推进到 `approved` / `rejected`，并写入 `reviewed_by` / `reviewed_at`（模型里这两个字段已有该入口才不会被浪费）。
5. **项目级上传**：本期**只做任务级上传**（5 个端点中上传类都挂在任务下）。模型层的 `task_id` 仍允许为空，以兼容上一轮已存在的「纯元数据登记」用法；将来若要开项目级上传，只需新增一个项目级端点，表结构无需改动。

---

## 13. 实施结果与验证记录

### 13.1 落地文件

| 类别 | 文件 | 说明 |
| --- | --- | --- |
| 新增 | `backend/app/core/storage.py` | 通用存储原语：路径净化、独占写入、SHA256、原子就位 |
| 新增 | `backend/app/services/artifact_types.py` | 扩展名白名单 → MIME 映射与内容嗅探 |
| 新增 | `backend/app/api/v1/endpoints/artifacts.py` | 6 个端点（5 个必需 + 审核） |
| 新增 | `backend/alembic/versions/0003_artifact_storage.py` | 迁移脚本 |
| 新增 | `backend/tests/test_artifact_storage.py` | 18 个用例 |
| 修改 | `backend/app/models/artifact.py`、`models/enums.py` | `stage` / `original_filename` / `storage_path` 与约束索引 |
| 修改 | `backend/app/schemas/artifact.py` | `ArtifactRead` 扩展、`ArtifactReviewRequest` |
| 修改 | `backend/app/services/artifacts.py` | 上传 / 下载 / 新版本 / 列表 / 审核 |
| 修改 | `backend/app/core/config.py`、`core/exceptions.py` | 存储配置项与 `PAYLOAD_TOO_LARGE` |
| 修改 | `backend/tests/conftest.py` | 注入临时 `STORAGE_ROOT`、`storage_root` / `task_id` fixture |
| 修改 | `README.md`、`.env.example`、`docker-compose.yml`、`.gitignore` | 文档与环境变量 |

### 13.2 对自动生成迁移脚本的人工修正

| 问题 | 原因 | 处理 |
| --- | --- | --- |
| `stage` 以 `NOT NULL` 且无默认值新增 | 已有数据的表不能直接加非空列 | `server_default="development"` |
| 没有 `stage` 的 CHECK 约束 | autogenerate 不生成 CHECK | 手工在 batch 块内补 |
| `create_unique_constraint` 在 SQLite 上报 `NotImplementedError` | SQLite 不能 ALTER 约束 | 整段改动放进 `op.batch_alter_table(...)`；SQLite 上重建表并保留原有 CHECK 与外键，PostgreSQL 上仍是普通 `ALTER TABLE` |
| 约束名变成 `ck_artifacts_ck_artifacts_stage_valid` | SQLAlchemy 2.x 会对**已命名**的 CHECK 约束再套一次命名约定 `ck_%(table_name)s_%(constraint_name)s` | 约束名用 `op.f(...)` 固定；否则 SQLite 上的降级脚本会 `DROP CONSTRAINT ck_artifacts_ck_artifacts_stage_valid`，而 PostgreSQL 上真实名字是 `ck_artifacts_stage_valid`，降级必然失败 |

### 13.3 已执行的验证

| 验证项 | 命令 / 方式 | 结果 |
| --- | --- | --- |
| 代码风格 | `python -m ruff check .` | All checks passed |
| 后端测试 | `python -m pytest -q` | 72 passed（新增 18 个文件管理用例） |
| 迁移往返（SQLite） | `alembic upgrade head` → `downgrade base` → `upgrade head` | 通过；重建后的表保留 4 个 CHECK、3 个外键、8 个显式索引与全部 18 列 |
| 迁移漂移 | `alembic check` | No new upgrade operations detected |
| 约束名一致性 | 直接读 `sqlite_master` | `ck_artifacts_stage_valid`、`uq_artifacts_storage_path` 与模型元数据完全一致 |
| CHECK 生效 | 写入非法 `stage` | `CHECK constraint failed: ck_artifacts_stage_valid` |
| PostgreSQL 方言 DDL | `alembic upgrade head --sql` / `downgrade --sql`（postgresql DSN） | 升级生成 `ADD CONSTRAINT ck_artifacts_stage_valid CHECK (...)` 与 `ADD CONSTRAINT uq_artifacts_storage_path UNIQUE (...)`；降级生成对应的 `DROP CONSTRAINT` |
| 实时 HTTP 冒烟 | `python scripts/smoke_http.py http://127.0.0.1:8125/api/v1` | 55 项检查全部通过（含上传、下载、版本、审核、列表、错误路径） |

### 13.4 未执行的验证

| 项目 | 原因 |
| --- | --- |
| PostgreSQL 实例上的真实迁移与查询 | 本机没有 PostgreSQL，也没有 Docker（按上一轮的决定暂不补） |
| `docker compose up` 整栈验收 | 同上 |
| 病毒扫描 / 对象存储后端 | 不在本次范围（见 1.2） |

### 13.5 与设计文档的差异

1. **文件名策略**：设计稿写的是「只取 basename」，实现改为「含路径分隔符或 `..` 段的文件名直接 422」。静默截断会掩盖越界尝试，接口语义也更明确。
2. **文件类型判定依据**：以**最终落盘的文件名**（逻辑路径最后一段）的扩展名为准，不信任请求里的 `Content-Type`；内容仍按该扩展名做嗅探校验。
3. **审核动作会写审批轨迹**：`review` 端点在更新文件状态的同时向 `approval_records` 追加一条记录，`comment` 落在审批轨迹里。
4. **就位方式**：临时文件校验通过后用硬链接原子就位（`os.link`），而不是「检查后移动」，消除了检查与移动之间的竞态窗口。
