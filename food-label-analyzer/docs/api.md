# Food Label Analyzer 后端接口文档（前端对接）

## 1. 基本信息

- **API 前缀**：`/api/v1`（可配置，默认值见 [config.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/config.py#L18-L25)）
- **Swagger**：开发环境可用 `/docs`（生产环境默认关闭）
- **ReDoc**：开发环境可用 `/redoc`（生产环境默认关闭）

## 2. 通用约定

### 2.1 请求头

- **Authorization**（需要登录的接口）：`Bearer <access_token>`
- **X-Request-ID**（可选）：客户端传入用于链路追踪；后端会在响应头回传

### 2.2 统一响应格式

绝大多数接口返回结构为：

```json
{
  "code": 0,
  "message": "成功",
  "data": {}
}
```

定义见 [common.py:ApiResponse](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/common.py#L28-L41)。

### 2.3 错误响应格式

业务异常统一返回：

```json
{
  "code": 4014,
  "message": "令牌无效",
  "data": null
}
```

参数校验错误（HTTP 422）统一返回：

```json
{
  "code": 4220,
  "message": "请求参数错误",
  "data": {
    "errors": [
      { "field": "email", "message": "value is not a valid email address", "type": "value_error" }
    ]
  }
}
```

处理逻辑见 [error_handlers.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/error_handlers.py)。

### 2.4 常用业务错误码（节选）

来源：[errors.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/core/errors.py)

- `4010` 邮箱或密码错误
- `4011` 邮箱尚未完成验证（未验证）
- `4013` 令牌已过期
- `4014` 令牌无效
- `4001` 邮箱已注册
- `4002` 请求过于频繁（带 retry_after_seconds）
- `4003` 验证码无效或已过期
- `4012` 密码重置链接无效或已过期
- `4021` 上传文件类型不支持
- `4022` 上传文件过大
- `4024` 并发任务超限
- `4041` 分析任务不存在
- `4042` 报告不存在
- `5000` 外部服务暂时不可用

## 3. 认证模块（Auth）

路由前缀：`/api/v1/auth`，实现见 [auth.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/auth.py)

### 3.1 发送注册验证码

**POST** `/api/v1/auth/register/send-code`

请求体：

```json
{ "email": "user@example.com" }
```

响应 `data`：

```json
{ "cooldown_seconds": 60 }
```

说明：

- 接口会返回当前冷却时间（秒），避免频繁发送

### 3.2 注册账号

**POST** `/api/v1/auth/register`

请求体：

```json
{
  "email": "user@example.com",
  "code": "123456",
  "password": "StrongPass123"
}
```

密码规则（后端校验）：

- 至少包含：大写字母 + 小写字母 + 数字
- 长度 8-32

响应 `data`：`null`

### 3.3 登录

**POST** `/api/v1/auth/login`

请求体：

```json
{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```

响应 `data`：

```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "Bearer",
  "expires_in": 1800
}
```

### 3.4 刷新令牌

**POST** `/api/v1/auth/refresh`

请求体：

```json
{ "refresh_token": "eyJhbGciOi..." }
```

响应 `data`：同登录

### 3.5 发送重置密码邮件（不暴露邮箱是否存在）

**POST** `/api/v1/auth/forgot-password`

请求体：

```json
{ "email": "user@example.com" }
```

响应：永远返回 200，`message` 为“如果账号存在，重置邮件已发送”

### 3.6 重置密码

**POST** `/api/v1/auth/reset-password`

请求体：

```json
{
  "token": "reset-token-value",
  "new_password": "NewStrongPass123"
}
```

响应 `data`：`null`

## 4. 分析模块（Analysis）

路由前缀：`/api/v1/analysis`，实现见 [analysis.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/analysis.py)

### 4.1 上传图片并创建分析任务

**POST** `/api/v1/analysis/upload`

- 需要登录：`Authorization: Bearer <access_token>`
- `Content-Type`: `multipart/form-data`
- 表单字段：`file`

文件限制（后端校验）：

- 最大：`MAX_UPLOAD_SIZE_MB`（默认 10MB）
- 类型：`image/jpeg,image/png,image/webp`

响应 `data`：

```json
{
  "task_id": "2b9bdc9e-4b3c-4a1f-9f09-1c7f18c8c2f4",
  "status": "pending",
  "created_at": "2026-03-25T12:30:00Z"
}
```

### 4.2 查询任务状态（轮询）

**GET** `/api/v1/analysis/tasks/{task_id}`

- 需要登录：`Authorization: Bearer <access_token>`

响应 `data`：

```json
{
  "task_id": "2b9bdc9e-4b3c-4a1f-9f09-1c7f18c8c2f4",
  "status": "processing",
  "progress_message": "系统正在分析上传图片",
  "created_at": "2026-03-25T12:30:00Z",
  "completed_at": null,
  "report_id": null,
  "error_message": null,
  "nutrition_parse_source": null
}
```

`status` 可能值：

- `pending`
- `processing`
- `completed`
- `failed`

前端推荐流程：

1. 上传返回 `task_id`
2. 每 1~2 秒轮询一次状态
3. 当 `status=completed` 且 `report_id` 非空 → 拉取报告详情
4. 当 `status=failed` → 展示 `error_message`

## 5. 报告模块（Reports）

路由前缀：`/api/v1/reports`，实现见 [reports.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/reports.py)

### 5.1 分页查询报告列表

**GET** `/api/v1/reports?page=1&page_size=10`

- 需要登录：`Authorization: Bearer <access_token>`

响应 `data`：

```json
{
  "items": [
    {
      "report_id": "9d4d8f6a-8b2c-4bd4-a1d1-0d5c2cbd7c0a",
      "task_id": "2b9bdc9e-4b3c-4a1f-9f09-1c7f18c8c2f4",
      "score": 85,
      "summary": "Moderate risk",
      "image_url": "https://minio.example.com/report.png",
      "created_at": "2026-03-25T12:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10,
  "total_pages": 1
}
```

### 5.2 查询报告详情

**GET** `/api/v1/reports/{report_id}`

- 需要登录：`Authorization: Bearer <access_token>`

响应 `data`（字段较多，示意）：

```json
{
  "report_id": "9d4d8f6a-8b2c-4bd4-a1d1-0d5c2cbd7c0a",
  "task_id": "2b9bdc9e-4b3c-4a1f-9f09-1c7f18c8c2f4",
  "image_url": "https://minio.example.com/report.png",
  "ingredients_text": "配料：...",
  "nutrition": { "items": [], "serving_size": null, "parse_method": "empty" },
  "nutrition_parse_source": "table_recognition",
  "analysis": {
    "score": 85,
    "summary": "...",
    "top_risks": [],
    "ingredients": [],
    "health_advice": []
  },
  "rag_summary": {
    "total_ingredients": 6,
    "retrieved_count": 4,
    "high_match_count": 3,
    "weak_match_count": 1,
    "empty_count": 2
  },
  "artifact_urls": {
    "ocr_full_json_url": "https://minio.example.com/ocr.json"
  },
  "created_at": "2026-03-25T12:30:00Z"
}
```

Schema 定义见：

- [report.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/report.py)
- [analysis_data.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/analysis_data.py)

## 6. 健康检查（Health）

**GET** `/health`

- 不需要登录
- 返回应用状态与依赖服务探针状态（数据库、Redis、MinIO、YOLO、Chroma、Ollama、OCR runtime）

实现见 [main.py:health](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/main.py#L281-L289)

## 7. 前端对接建议

- 统一处理 `ApiResponse`：`code!=0` 视为业务错误，展示 `message`
- 401/403：清空本地 token 并引导重新登录
- 任务轮询：建议使用指数退避或固定间隔（1~2 秒），避免频率过高
- 保留 `X-Request-ID`：前端可为每次请求生成 UUID，便于后端排查

