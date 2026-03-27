# FoodGuard Backend Codebase Deep Dive

## 1. 文档定位

本文档面向代码阅读、论文写作、项目汇报和答辩准备，基于当前仓库中 `food-label-analyzer/` 的真实代码整理，而不是仅根据设计文档推断。

阅读范围包括：

- `food-label-analyzer/app/` 全部真实业务代码
- `food-label-analyzer/tests/` 全部测试代码
- `food-label-analyzer/scripts/` 调试与数据重建脚本
- `food-label-analyzer/.env.example`、`requirements*.txt`、`pytest.ini`
- 仓库根目录 `提示词/` 中与后端链路有关的设计文档标题和上下文

截至本次梳理时的验证结果：

- 后端测试：`conda activate foodguard-env; python -m pytest`
- 结果：`116 passed, 1 skipped`

这说明本文描述的主流程、接口约束、模型关系和 AI 推理链路与当前测试期望是一致的。

---

## 2. 后端项目的总体职责

`food-label-analyzer` 是整个系统的后端核心，职责不是单一的“提供接口”，而是把食品标签图片从上传到分析报告生成的完整链路串起来。它同时承担了以下角色：

1. Web API 服务端  
   基于 FastAPI 提供认证、图片上传、任务查询、报告查询、用户信息、偏好设置等接口。

2. 业务编排层  
   通过 `services/` 目录把数据库、Redis、MinIO、AI Worker、邮件服务等能力组织成完整业务流程。

3. 异步任务调度层  
   通过 Celery 把图片分析工作放到后台执行，避免 HTTP 请求阻塞。

4. AI 分析流水线入口  
   使用 YOLO、OCR、规则提取、RAG、LLM 等模块完成“食品标签图片 -> 结构化健康报告”的转换。

5. 数据持久化层  
   使用 SQLAlchemy ORM 把用户、分析任务、报告、刷新令牌、邮箱验证码、偏好设置等数据持久化到 PostgreSQL。

6. 基础设施边界层  
   管理数据库连接、Redis、MinIO、ChromaDB、Ollama、DeepSeek、PaddleOCR、SMTP 等外部依赖。

从架构分层上看，这个项目不是传统三层 CRUD 系统，而是“API + 任务队列 + 多模型推理 + 报告持久化”的混合型后端。

---

## 3. 目录结构与代码组织方式

当前后端的主要结构如下：

```text
food-label-analyzer/
├─ app/
│  ├─ api/                 FastAPI 路由层
│  ├─ core/                配置、日志、安全、错误处理、邮件底层
│  ├─ db/                  SQLAlchemy/Redis 连接封装
│  ├─ models/              ORM 模型
│  ├─ schemas/             Pydantic 请求/响应模型
│  ├─ services/            业务服务层
│  ├─ tasks/               Celery 任务与 worker 初始化
│  ├─ workers/             YOLO/OCR/RAG/LLM/提取器
│  ├─ dependencies.py      登录态依赖注入
│  └─ main.py              FastAPI 应用入口
├─ scripts/                调试与数据重建脚本
├─ tests/                  pytest 测试
├─ models_store/           YOLO 模型文件
├─ chroma_data/            ChromaDB 持久化数据
├─ .env.example            环境变量契约
├─ requirements.txt        运行依赖
└─ pytest.ini              测试配置
```

这个结构的优点是职责分离比较清晰：

- 路由层只负责 HTTP 协议编排，不直接塞复杂业务。
- `services/` 负责业务流程。
- `workers/` 负责“计算型”和“外部 AI 能力调用型”工作。
- `schemas/` 负责输入输出契约，避免前后端字段漂移。
- `models/` 负责数据库结构表达。

这也是论文或答辩中比较容易讲清楚的一种工程化组织方式。

---

## 4. 启动流程与应用入口

### 4.1 `app/main.py` 的作用

`app/main.py` 是整个后端的装配中心，主要完成以下工作：

- 读取配置 `get_settings()`
- 初始化 structlog 日志
- 执行启动检查
- 创建 FastAPI 应用
- 注入 CORS 中间件
- 注入请求 ID 中间件
- 注入安全响应头中间件
- 注册全局异常处理器
- 注册 `/api/v1` 路由
- 提供 `/health` 健康检查接口

### 4.2 启动检查逻辑

如果 `.env` 中 `SKIP_STARTUP_CHECKS=false`，启动时会执行以下检查：

- 数据库连通性：`SELECT 1`
- Redis 连通性：`ping`
- MinIO 桶存在性，不存在时自动创建
- YOLO 模型文件是否存在
- ChromaDB 路径是否存在

这说明系统设计上默认把“依赖可用性”前置到启动阶段，而不是等到第一次请求才失败。

### 4.3 健康检查逻辑

`/health` 接口会分别探测：

- database
- redis
- minio
- yolo_model
- chromadb
- ollama_embedding
- ocr_runtime

并汇总成 `healthy` 或 `degraded` 两级状态。  
其中 `ollama_embedding` 和 `ocr_runtime` 是否实际访问外部接口，受 `HEALTH_CHECK_EXTERNAL` 控制。

### 4.4 中间件

后端当前有两个很重要的中间件：

1. `request_id_middleware`
   - 为每次请求绑定 `X-Request-ID`
   - 写入 `request.state.request_id`
   - 同步绑定到 structlog 的 contextvars
   - 便于链路追踪和日志排障

2. `security_headers_middleware`
   - 注入 `X-Content-Type-Options`
   - 注入 `X-Frame-Options`
   - 注入 `X-XSS-Protection`
   - 在 HTTPS 请求场景下注入 HSTS

这部分非常适合在答辩时解释“非功能性设计”，说明系统不仅关注业务功能，也考虑了安全和可运维性。

---

## 5. 配置系统设计

### 5.1 配置入口

配置集中在 `app/core/config.py` 的 `Settings` 类中，基于 Pydantic Settings。

核心特点：

- 从 `.env` 加载
- `@lru_cache` 保证进程级单例
- 带字段校验
- 带派生属性

### 5.2 配置分类

当前配置基本覆盖完整运行链路：

- 应用配置：环境、调试、前端地址、API 前缀
- 数据库配置：异步/同步 URL
- Redis/Celery 配置
- MinIO 配置
- PaddleOCR 在线任务 API 配置
- DeepSeek LLM 配置
- Ollama Embedding 配置
- ChromaDB 配置
- YOLO 配置
- 评分权重配置
- 提取器/RAG 参数
- JWT 配置
- SMTP 配置
- 上传限制配置
- CORS 配置
- 日志配置

### 5.3 重要派生属性

几个派生属性在代码里非常常用：

- `jwt_access_expire_timedelta`
- `jwt_refresh_expire_timedelta`
- `max_upload_size_bytes`
- `allowed_image_types_list`
- `minio_client_endpoint`
- `cors_origins_list`

### 5.4 字段校验规则

配置系统做了若干关键校验：

- `APP_SECRET_KEY` 长度至少 32
- `DATABASE_URL` 必须是 `postgresql+asyncpg://`
- `DATABASE_SYNC_URL` 必须是 `postgresql+psycopg://`
- `REDIS_URL` 必须以 `redis://` 开头
- `YOLO_CONFIDENCE_THRESHOLD` 必须在 0 到 1 之间
- `SMTP_PORT` 必须在 `{25, 465, 587, 2525}` 中
- `MAX_UPLOAD_SIZE_MB` 必须在 1 到 50 之间

这部分体现了“环境契约化”思想：把运行失败尽量前置到配置加载阶段。

---

## 6. 基础设施与共享核心模块

### 6.1 日志模块 `app/core/logging.py`

日志方案使用 `structlog + stdlib logging`。

特点：

- 支持 console / json 两种格式
- 能与 uvicorn/fastapi 日志桥接
- 支持上下文 request_id 合并
- 捕获 warnings

### 6.2 安全模块 `app/core/security.py`

主要提供：

- 密码哈希：`passlib` + `bcrypt`
- 密码校验
- JWT Access Token 生成
- JWT Refresh Token 生成
- Token 解码与过期校验

当前 JWT 设计要点：

- 算法：`HS256`
- `sub` 保存 user_id
- `type` 区分 `access` / `refresh`
- `exp`、`iat` 写入 token
- refresh token 额外带 `jti`

### 6.3 错误体系 `app/core/errors.py`

后端定义了比较完整的业务异常层级：

- `AppBaseException` 基类
- 认证相关：`InvalidCredentialsError`、`TokenInvalidError`、`TokenExpiredError`
- 注册/验证码相关：`EmailAlreadyExistsError`、`InvalidVerifyCodeError`、`CooldownError`
- 上传相关：`FileTooLargeError`、`InvalidFileTypeError`
- 资源不存在相关：`TaskNotFoundError`、`ReportNotFoundError`
- 外部服务相关：`OCRServiceError`、`LLMServiceError`、`StorageServiceError`、`EmbeddingServiceError`

每个异常都内置：

- HTTP 状态码
- 业务错误码
- 默认错误消息
- 可选 detail

### 6.4 全局异常处理 `app/core/error_handlers.py`

异常处理器统一把错误转换成：

```json
{
  "code": 4001,
  "message": "具体错误信息",
  "data": {...}
}
```

它覆盖三类情况：

- 自定义业务异常
- FastAPI/Pydantic 请求校验异常
- 未处理异常

其中请求参数错误会额外格式化成字段级错误列表，这一点直接支撑了前端注册页和修改密码页的字段错误提示。

### 6.5 数据库会话 `app/db/session.py`

数据库模块同时维护两套引擎：

- 异步引擎：用于 FastAPI 路由和异步服务
- 同步引擎：用于 Celery 任务

这是因为 Celery 任务 `process_image_task` 是同步任务函数，不能直接复用异步 session。

关键封装：

- `get_db()`：异步依赖，自动 commit/rollback
- `get_sync_db()`：同步上下文管理器，供 Celery 使用

### 6.6 Redis 模块 `app/db/redis.py`

Redis 采用模块级单例连接，主要提供：

- `get_redis()`
- `close_redis()`
- `set_with_ttl()`
- `get_value()`
- `get_ttl()`
- `exists()`

当前 Redis 主要用于：

- 邮箱验证码发送冷却
- 重置密码冷却
- Celery broker / backend

### 6.7 登录态依赖 `app/dependencies.py`

`get_current_user()` 的流程是：

1. 从 OAuth2 Bearer Token 中取出 JWT
2. 解码并检查是否是 access token
3. 解析 user_id
4. 查询数据库用户
5. 校验用户是否存在且仍处于 active 状态

因此，前端即使持有旧 token，只要用户已停用，也会被视为无效。

---

## 7. 数据模型设计

### 7.1 通用基类

`app/db/base.py` 定义了三个可复用 mixin：

- `UUIDPrimaryKeyMixin`
- `TimeStampMixin`
- `CreatedAtMixin`

统一使用 PostgreSQL UUID 主键和带时区时间戳字段。

### 7.2 用户模型 `User`

关键字段：

- `email`
- `password_hash`
- `display_name`
- `avatar_url`
- `is_verified`
- `is_active`
- `deleted_at`

关键关系：

- 一个用户有多个 `AnalysisTask`
- 一个用户有多个 `Report`
- 一个用户有多个 `RefreshToken`
- 一个用户有多个 `PasswordResetToken`
- 一个用户有一个 `UserPreference`

### 7.3 邮箱验证码模型 `EmailVerification`

用于注册验证码场景，字段包括：

- `email`
- `code`
- `type`
- `is_used`
- `expired_at`

### 7.4 密码重置模型 `PasswordResetToken`

字段包括：

- `user_id`
- `token`
- `is_used`
- `expired_at`

### 7.5 刷新令牌模型 `RefreshToken`

字段包括：

- `user_id`
- `jti`
- `expires_at`
- `revoked_at`

### 7.6 分析任务模型 `AnalysisTask`

关键字段：

- `user_id`
- `image_url`
- `image_key`
- `status`
- `error_message`
- `celery_task_id`
- `completed_at`

任务状态枚举包括：

- `pending`
- `processing`
- `completed`
- `failed`

### 7.7 报告模型 `Report`

核心字段：

- `task_id`
- `user_id`
- `ingredients_text`
- `nutrition_json`
- `nutrition_parse_source`
- `rag_results_json`
- `llm_output_json`
- `score`
- `artifact_urls`
- `deleted_at`

报告大量使用 JSONB 持久化 AI 结果，这对快速迭代 AI 输出字段非常友好。

### 7.8 用户偏好模型 `UserPreference`

字段：

- `focus_groups`
- `health_conditions`
- `allergies`

三者都使用 JSONB 列。

---

## 8. Schema 层设计

### 8.1 通用响应 Schema

`app/schemas/common.py` 定义：

- `ApiResponse[T]`
- `success_response()`
- `PageRequest`
- `PageResponse[T]`

### 8.2 认证相关 Schema

包括：

- `SendCodeRequest`
- `RegisterRequest`
- `LoginRequest`
- `RefreshTokenRequest`
- `LogoutRequest`
- `ForgotPasswordRequest`
- `ResetPasswordRequest`
- `TokenResponse`
- `CooldownResponse`

### 8.3 用户与偏好 Schema

包括：

- `UserProfileResponse`
- `UpdateUserProfileRequest`
- `ChangePasswordRequest`
- `UserPreferenceUpsertRequest`
- `UserPreferenceResponse`

### 8.4 分析任务 Schema

`app/schemas/analysis.py` 负责把内部状态转换成前端状态，并清洗错误消息。

### 8.5 AI 结构化输出 Schema

`app/schemas/analysis_data.py` 定义：

- `NutritionItem`
- `NutritionData`
- `RAGMatch`
- `RAGRetrievalItem`
- `RAGResults`
- `IngredientItem`
- `HealthAdviceItem`
- `HazardItem`
- `FoodHealthAnalysisOutput`

其中 `health_advice` 被强制要求覆盖固定 5 个人群。

### 8.6 报告响应 Schema

后端额外把数据库 JSON 整形成前端友好的：

- `AnalysisSchema`
- `RagSummarySchema`
- `NutritionTableRowSchema`
- `NutritionTableSchema`
- `ReportListItemSchema`
- `ReportDetailResponseSchema`

---

## 9. API 路由层设计

### 9.1 总路由

`app/api/router.py` 注册了：

- `/auth`
- `/analysis`
- `/reports`
- `/users`
- `/preferences`

### 9.2 认证接口

`app/api/v1/auth.py` 提供：

- `POST /auth/register/send-code`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

### 9.3 分析接口

`app/api/v1/analysis.py` 提供：

- `POST /analysis/upload`
- `GET /analysis/tasks/{task_id}`

### 9.4 报告接口

`app/api/v1/reports.py` 提供：

- `GET /reports`
- `GET /reports/{report_id}`
- `DELETE /reports/{report_id}`

### 9.5 用户接口

`app/api/v1/users.py` 提供：

- `GET /users/me`
- `PATCH /users/me`
- `POST /users/change-password`
- `DELETE /users/me`

### 9.6 偏好接口

`app/api/v1/preferences.py` 提供：

- `GET /preferences/me`
- `PUT /preferences/me`

---

## 10. 服务层设计

### 10.1 `auth_service.py`

它实现了完整认证链路：

- 发送注册验证码
- 注册用户
- 登录
- 注销
- 刷新 token
- 发送重置邮件
- 重置密码

关键实现要点：

- 验证码冷却放在 Redis 中
- refresh token 落库
- 刷新时旧 refresh token 立即吊销
- 修改密码和重置密码都会吊销全部 refresh token

### 10.2 `email_service.py`

负责拼装重置密码链接并调用底层邮件服务，发送异常只打日志，不阻塞主流程。

### 10.3 `user_service.py`

负责：

- 获取用户资料
- 更新资料
- 修改密码
- 停用账号

### 10.4 `preference_service.py`

负责：

- 获取偏好
- 新增或更新偏好

并自动把 `allergy` 与 `allergies` 字段联动。

### 10.5 `task_service.py`

负责：

- 上传文件校验
- 并发任务限制
- 创建任务
- 更新 Celery task id
- 任务权限校验
- 任务状态响应组装

### 10.6 `storage_service.py`

负责 MinIO：

- 建桶
- 上传图片
- 上传 artifact
- 生成预签名 URL
- 删除图片

### 10.7 `report_service.py`

这是最重要的前端适配服务之一，负责：

- 报告分页
- 报告详情
- 软删除
- 营养表重组
- RAG 结果汇总
- LLM 输出整形

### 10.8 `score_calculator.py`

它实现了规则评分体系，但当前主任务落库链路仍以 LLM 输出得分为准，规则评分更多被脚本和测试使用。

---

## 11. AI 分析流水线

主任务入口：`app/tasks/analysis_task.py -> process_image_task`

整体流程如下：

1. 从 MinIO 下载原图
2. 用 YOLO 定位营养成分表区域
3. 若检测到 bbox：
   - 裁剪营养表
   - 对原图做营养表区域遮罩
   - 并行执行全文 OCR 与营养表 OCR
4. 若未检测到 bbox：
   - 对整图做全文 OCR
   - 再做整图营养表识别
5. 调用 `nutrition_extractor.parse()` 生成营养结构
6. 调用 `ingredient_extractor.extract()` 提取配料
7. 调用 `rag_worker.retrieve_all()` 做配料知识检索
8. 调用 `llm_worker.analyze()` 生成健康分析 JSON
9. 校验并落库 `Report`
10. 将任务状态标记为 completed

### 11.1 Celery 层

`app/tasks/celery_app.py` 使用 Redis 作为 broker/backend，支持 Windows 下 `solo` worker，并在 worker 启动时 warmup YOLO/OCR/RAG/LLM。

### 11.2 YOLO Worker

`app/workers/yolo_worker.py` 负责：

- 模型单例加载
- bbox 检测
- 图片裁剪
- 图片遮罩

### 11.3 OCR Worker

`app/workers/ocr_worker.py` 负责：

- 封装 PaddleOCR 在线任务 API
- 标准化 OCR 返回结构
- 全文 OCR
- 营养表 OCR
- 并行 OCR

关键类型：

- `OCRConfig`
- `OCRTextResult`
- `TableRecognitionResult`
- `OCRParallelResult`

### 11.4 提取器

#### `nutrition_extractor.py`

把表格 OCR 结果或 OCR 文本交给 LLM 标准化成 `NutritionData`。

#### `ingredient_extractor.py`

优先规则提取配料，失败时再调用 LLM。

#### `topic_cleaner.py / topic_splitter.py / ingredients_only.py / rule_config.py`

负责 OCR 文本清洗、主题定位、配料分裂、规则集合管理，是规则提取链路的底层。

### 11.5 RAG Worker

`app/workers/rag_worker.py` 负责：

- 调用 Ollama embedding
- 查询 ChromaDB 配料集合
- 查询 ChromaDB 标准集合
- 生成统一 `retrieval_results`

### 11.6 LLM Worker

`app/workers/llm_worker.py` 负责：

- 通过 OpenAI SDK 调用 DeepSeek
- 强制模型返回 JSON
- 校验 JSON 是否符合 `FoodHealthAnalysisOutput`
- 若失败则进入 repair 链路

### 11.7 Prompt 设计

Prompt 放在 `app/workers/extractor/prompts/` 下，强调：

- 输出固定 JSON
- 限制字段长度和枚举值
- 限制模型只做结构化输出，不做开放式发挥

---

## 12. 端到端业务流程说明

### 12.1 用户注册登录

1. 前端调 `/auth/register/send-code`
2. 后端写入验证码并触发邮件发送
3. 前端调 `/auth/register`
4. 后端创建用户
5. 前端调 `/auth/login`
6. 后端签发 access/refresh token
7. refresh token 落库

### 12.2 图片上传分析

1. 前端上传图片到 `/analysis/upload`
2. 后端校验文件
3. 上传原图到 MinIO
4. 创建 `AnalysisTask`
5. 投递 Celery 任务
6. Celery 跑完整 AI 流水线
7. 生成 `Report`
8. 前端轮询任务状态并在完成后跳报告页

### 12.3 报告查看

1. 前端请求 `/reports/{report_id}`
2. 后端读取 `Report + AnalysisTask`
3. 为图片生成预签名 URL
4. 重组营养表与风险摘要
5. 返回前端可直接渲染的数据

---

## 13. 脚本与测试体系

### 13.1 脚本

- `scripts/run_pipeline.py`：不落库跑全链路
- `scripts/run_db_pipeline.py`：含数据库和 MinIO 的调试落库链路
- `scripts/rebuild_chroma_ollama.py`：重建 Chroma 向量库

### 13.2 测试体系

当前测试覆盖：

- 配置系统
- 核心异常与安全模块
- DB/Redis/Celery/路由基础设施
- 认证业务与接口
- 上传与任务状态
- Worker 和 AI 链路
- 报告查询
- OpenAPI 文档
- 用户资料与偏好

本次实测结果为 `116 passed, 1 skipped`。

---

## 14. 当前实现中的真实优点

### 14.1 分层清晰

路由、服务、模型、Schema、Worker、任务编排边界明确，非常适合论文和答辩画架构图。

### 14.2 AI 流水线是多阶段方案

不是“图片直接扔给一个模型”，而是“检测 -> 识别 -> 提取 -> 检索 -> 生成”的组合链路，更具可解释性。

### 14.3 外部依赖边界清楚

MinIO、OCR、RAG、LLM、SMTP 都有相对独立封装。

### 14.4 测试覆盖较好

对后端来说，这已经不是单纯 demo，而是具备较高可验证性的工程实现。

---

## 15. 当前实现中的局限与可改进点

### 15.1 规则评分还没接入正式主链路

`score_calculator.py` 已经实现，但当前报告主得分仍来自 LLM。

### 15.2 artifact 能力预留多于实际产出

模型和 schema 里有 artifact 字段，但 OCR worker 当前没有真正产出很多 artifact URL。

### 15.3 邮件发送为异步 fire-and-forget

接口成功并不等于邮件一定送达。

### 15.4 Chroma 集合配置仍可继续细化

默认的 ingredients/standards collection 名称相同，后续更适合拆分。

### 15.5 部分配置和能力仍处于预留态

例如某些 OCR 配置、评分权重、artifact URL 等仍有进一步接入空间。

---

## 16. 论文/答辩建议如何讲这套后端

建议按以下逻辑讲：

1. 业务问题  
   食品标签内容复杂，用户难以快速识别营养和风险。

2. 技术路线  
   采用“检测 + OCR + 配料提取 + RAG + LLM”的多阶段分析。

3. 工程架构  
   FastAPI 负责接口，Celery 负责异步，PostgreSQL/MinIO/Redis/ChromaDB/Ollama/DeepSeek 共同完成整条链路。

4. 创新点  
   规则提取与模型修复结合；输出被限制为结构化 JSON；前后端围绕统一 schema 协作。

5. 局限与演进方向  
   规则评分待正式接入、artifact 产物待补全、知识库可继续扩展。

---

## 17. 一句话总结

当前 `food-label-analyzer` 后端已经具备完整的“用户认证 + 图片上传 + 异步分析 + 多阶段 AI 推理 + 报告持久化 + 报告查询”能力，最大的特点是把食品标签分析拆解成可解释、可维护的多模块流水线，而不是依赖单一模型黑盒输出。
