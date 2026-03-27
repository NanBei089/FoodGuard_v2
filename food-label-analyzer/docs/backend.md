# Food Label Analyzer 后端说明

详细分析链路文档见：[backend-analysis-pipeline.md](backend-analysis-pipeline.md)

## 1. 项目定位

Food Label Analyzer 是一个面向“食品标签图片上传 → 后台分析 → 生成健康报告”的后端服务。

它提供：

- 用户注册/登录/刷新令牌/找回密码
- 食品标签图片上传并创建异步分析任务
- 任务状态查询与报告查询
- 健康检查与依赖探针

核心入口：[main.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/main.py)

## 2. 技术栈与依赖

**Web/API**

- FastAPI（OpenAPI/Swagger）
- Starlette（FastAPI 底层）
- Pydantic v2（请求/响应 Schema）

**存储与基础设施**

- PostgreSQL（结构化数据：用户、任务、报告）
- Redis（验证码冷却、Celery broker/result backend）
- MinIO（图片与产物对象存储）
- ChromaDB（本地持久化向量库：`./chroma_data`）

**异步任务**

- Celery（队列：`analysis`）

**AI 能力适配**

- YOLO（ultralytics，食品标签/营养表区域检测）
- OCR（PaddleOCR 在线 API 形式）
- RAG（Chroma 检索 + Ollama embedding）
- LLM（DeepSeek OpenAI-compatible API）

## 3. 目录结构与职责

后端代码在 `food-label-analyzer/app/`，主要目录职责：

- `app/main.py`：应用启动、生命周期、CORS、健康检查、全局异常处理注册
- `app/api/v1/`：HTTP 路由（薄路由），仅做入参/依赖注入/响应封装
- `app/services/`：业务编排（任务创建、报告组装、认证流程）
- `app/tasks/`：Celery app 与任务编排（worker 链路入口）
- `app/workers/`：外部能力适配（YOLO/OCR/RAG/LLM 等）
- `app/models/`：SQLAlchemy ORM 模型（PostgreSQL 表）
- `app/schemas/`：Pydantic Schema（接口契约）
- `app/core/`：配置、日志、异常、安全（JWT）
- `app/db/`：数据库与 Redis 客户端、会话管理
- `alembic/`：迁移脚手架与初始迁移
- `tests/`：pytest 测试套件
- `scripts/`：本地调试脚本（用于手动跑 pipeline 或落库测试）

## 4. 运行与配置

### 4.1 配置文件

- 配置契约：`.env.example`
- 实际运行：`.env` 或环境变量
- Settings 定义：[config.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/config.py)

关键配置项（节选）：

- `APP_ENV`：`development`/`production`
- `API_V1_PREFIX`：默认 `/api/v1`
- `APP_SECRET_KEY`：至少 32 字符（JWT 密钥）
- `DATABASE_URL`：`postgresql+asyncpg://...`
- `DATABASE_SYNC_URL`：`postgresql+psycopg://...`（Celery 同步链路）
- `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
- `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET_NAME`
- `PADDLEOCR_JOB_URL` / `PADDLEOCR_TOKEN` / `PADDLEOCR_MODEL`
- `OLLAMA_BASE_URL` / `OLLAMA_EMBEDDING_MODEL`
- `CHROMADB_PATH` / `CHROMADB_COLLECTION_INGREDIENTS` / `CHROMADB_COLLECTION_STANDARDS`
- `YOLO_MODEL_PATH`
- `MAX_UPLOAD_SIZE_MB` / `ALLOWED_IMAGE_TYPES`
- `CORS_ORIGINS`

### 4.2 启动检查与开发体验

服务启动时会做依赖检查（数据库、Redis、MinIO bucket、YOLO 模型文件、Chroma 数据目录），逻辑在：

- [main.py:_run_startup_checks](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/main.py#L119-L125)

如果你只需要启动 API、但本地暂时没有完整依赖，可以设置：

- `SKIP_STARTUP_CHECKS=true`

并且在开发环境（`APP_ENV=development`）下会启用：

- Swagger UI：`/docs`
- ReDoc：`/redoc`

## 5. 请求/响应规范（后端全局约定）

### 5.1 统一响应包裹

所有业务接口使用统一响应结构：

- `code`：业务状态码（0 表示成功）
- `message`：消息
- `data`：数据载荷

Schema 定义：[common.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/common.py)

### 5.2 全局错误处理

统一异常处理在：

- [error_handlers.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/error_handlers.py)

特点：

- 业务异常（继承 `AppBaseException`）会以 `{code, message, data}` 返回
- 422 参数校验错误固定返回 `code=4220`，data 里带 `errors` 数组
- 500 未处理异常在非 debug 时隐藏细节，在 debug 时返回异常类型与 message

### 5.3 请求追踪

支持请求级 `X-Request-ID`：

- 客户端可传入 `X-Request-ID`，后端会原样回传
- 未传入则自动生成

实现位置：[main.py:request_id_middleware](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/main.py#L252-L263)

## 6. 认证与授权

- 登录后返回 `access_token` + `refresh_token`
- 需要登录的接口使用 `Authorization: Bearer <access_token>`
- 当前用户依赖：[dependencies.py:get_current_user](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/dependencies.py#L22-L48)

JWT 逻辑：[security.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/security.py)

## 7. 异步分析链路概览

前端侧交互流程：

1. 上传图片创建任务：`POST /api/v1/analysis/upload`
2. 轮询任务状态：`GET /api/v1/analysis/tasks/{task_id}`
3. 任务完成后拿到 `report_id`
4. 查询报告详情：`GET /api/v1/reports/{report_id}`

后端内部高层链路（简述）：

- 图片先上传到 MinIO，数据库保存 `image_key/image_url`
- 创建任务记录（PostgreSQL），然后通过 Celery 入队异步处理
- Worker 链路中执行 YOLO/OCR/抽取/RAG/LLM，最终落库到 `reports`

## 8. 数据存储策略

- PostgreSQL：结构化核心数据（任务/报告/用户/验证码与重置令牌）
- MinIO：图片原文件与产物文件（如 OCR 产物、裁剪图等）
- Redis：短期状态（验证码冷却、Celery 队列与结果）
- ChromaDB：本地向量索引（RAG 检索）

## 9. 测试与质量保障

- 测试框架：pytest
- 全量测试入口：`python -m pytest`
- OpenAPI 与关键模块存在回归用例：`tests/test_openapi_docs.py`、`tests/test_core_modules.py`、`tests/test_doc05_workers.py` 等

## 10. 给后端开发者的扩展建议

- 路由保持薄：尽量只做校验、依赖注入、调用 service、封装响应
- 业务逻辑放 service：跨模块编排放 `app/services/`
- 外部能力适配放 worker：OCR/YOLO/RAG/LLM 相关都集中到 `app/workers/`
- 统一从 `Settings` 取配置：避免散落读取环境变量
