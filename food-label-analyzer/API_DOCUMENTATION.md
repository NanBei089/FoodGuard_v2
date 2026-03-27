# Food Label Analyzer API 文档

## 概述

- **基础路径**: `/api/v1`
- **认证方式**: Bearer Token (JWT)
- **统一响应格式**:

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

### 响应状态码

| code | 说明 |
|------|------|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 / 认证失败 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
| 503 | 外部服务不可用 |

---

## 认证接口 `/auth`

### POST `/auth/register/send-code` - 发送注册验证码

发送六位数字验证码到邮箱，用于注册账号。

**请求体**:
```json
{
  "email": "user@example.com"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "验证码已发送",
  "data": {
    "cooldown_seconds": 60
  }
}
```

**错误码**:
- 409: 邮箱已注册
- 429: 请求过于频繁

---

### POST `/auth/register` - 注册账号

使用邮箱、验证码和密码完成注册。

**请求体**:
```json
{
  "email": "user@example.com",
  "code": "123456",
  "password": "StrongPass123"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "注册成功",
  "data": null
}
```

**错误码**:
- 400: 验证码或密码不合法
- 409: 邮箱已注册

**密码规则**: 8-32位，需包含大小写字母和数字

---

### POST `/auth/login` - 用户登录

使用邮箱和密码登录，返回访问令牌和刷新令牌。

**请求体**:
```json
{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 1800
  }
}
```

**令牌说明**:
- `access_token`: 访问令牌，有效期30分钟
- `refresh_token`: 刷新令牌，有效期7天
- `token_type`: 令牌类型，固定为 "Bearer"

**错误码**:
- 401: 邮箱或密码错误
- 403: 邮箱未验证

---

### POST `/auth/refresh` - 刷新令牌

使用刷新令牌换取新的访问令牌和刷新令牌。

**请求体**:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 1800
  }
}
```

**错误码**:
- 401: 刷新令牌无效

---

### POST `/auth/logout` - 用户登出

将当前 refresh token 标记为失效。

**请求体**:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

**错误码**:
- 401: 刷新令牌无效

---

### POST `/auth/forgot-password` - 发送重置密码邮件

如果账号存在，则发送重置密码邮件。接口不会暴露邮箱是否存在。

**请求体**:
```json
{
  "email": "user@example.com"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "如果账号存在，重置邮件已发送",
  "data": null
}
```

**错误码**:
- 429: 请求过于频繁
- 503: 外部服务暂时不可用

---

### POST `/auth/reset-password` - 重置密码

使用密码重置令牌和新密码完成密码重置。

**请求体**:
```json
{
  "token": "reset-token-value",
  "new_password": "NewStrongPass123"
}
```

**响应**:
```json
{
  "code": 0,
  "message": "密码已重置",
  "data": null
}
```

**错误码**:
- 400: 重置链接无效或已过期

**说明**:
- 重置令牌有效期15分钟
- 重置成功后，所有refresh token会被撤销

---

## 分析接口 `/analysis`

### POST `/analysis/upload` - 上传待分析图片

上传食品标签图片，创建分析任务并返回任务基础信息。

**请求**: `multipart/form-data`
- `file`: 图片文件 (JPEG/PNG/WEBP，最大10MB)

**响应**:
```json
{
  "code": 0,
  "message": "图片上传成功",
  "data": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "created_at": "2026-03-25T12:30:00Z"
  }
}
```

**响应字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | UUID | 任务唯一标识 |
| status | string | 固定为 "queued" |
| created_at | datetime | 任务创建时间 |

**错误码**:
- 400: 文件校验失败（格式、大小不符）
- 401: 未认证
- 429: 并发任务超限（最多3个）
- 503: 任务入队或外部服务失败

---

### GET `/analysis/tasks/{task_id}` - 查询任务状态

根据任务 ID 查询当前分析任务状态、报告 ID 和可见错误信息。

**路径参数**:
- `task_id`: UUID 任务ID

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "progress_message": "分析完成",
    "created_at": "2026-03-25T12:30:00Z",
    "completed_at": "2026-03-25T12:32:00Z",
    "report_id": "660e8400-e29b-41d4-a716-446655440001",
    "error_message": null,
    "nutrition_parse_source": "table_recognition"
  }
}
```

**status 状态说明**:

| 状态 | 说明 |
|------|------|
| queued | 任务排队中 |
| processing | 正在分析 |
| completed | 分析完成 |
| failed | 分析失败 |

**nutrition_parse_source 来源说明**:

| 来源 | 说明 |
|------|------|
| table_recognition | 表格识别解析 |
| ocr_text | OCR文本解析 |
| llm_fallback | LLM补全 |
| empty | 无营养数据 |
| failed | 解析失败 |

**错误码**:
- 401: 未认证
- 404: 任务不存在

---

## 报告接口 `/reports`

### GET `/reports` - 分页查询报告列表

返回当前用户的报告列表，支持分页。

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码，从1开始 |
| page_size | int | 10 | 每页条数，最大50 |

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "report_id": "550e8400-e29b-41d4-a716-446655440001",
        "task_id": "660e8400-e29b-41d4-a716-446655440000",
        "score": 85,
        "summary": "Overall risk is moderate",
        "image_url": "https://minio.example.com/signed-url...",
        "created_at": "2026-03-25T12:30:00Z"
      }
    ],
    "total": 25,
    "page": 1,
    "page_size": 10,
    "total_pages": 3
  }
}
```

**响应字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| items | array | 报告列表 |
| total | int | 总记录数 |
| page | int | 当前页码 |
| page_size | int | 每页条数 |
| total_pages | int | 总页数 |

**错误码**:
- 401: 未认证

---

### GET `/reports/{report_id}` - 查询报告详情

返回报告详情，包括营养数据、结构化分析结果、RAG汇总和产物链接。

**路径参数**:
- `report_id`: UUID 报告ID

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "report_id": "550e8400-e29b-41d4-a716-446655440001",
    "task_id": "660e8400-e29b-41d4-a716-446655440000",
    "image_url": "https://minio.example.com/signed-url...",
    "ingredients_text": "水、糖、食品添加剂、营养强化剂",
    "nutrition": {
      "serving_size": "每100ml",
      "energy": 180,
      "protein": 2,
      "fat": 0,
      "carbohydrate": 45,
      "sodium": 50
    },
    "nutrition_parse_source": "table_recognition",
    "analysis": {
      "score": 85,
      "summary": "Overall risk is moderate, driven by sodium and added sugar.",
      "top_risks": ["高钠", "含有阿斯巴甜"],
      "ingredients": [
        {
          "name": "阿斯巴甜",
          "category": "甜味剂",
          "safety_status": "approved",
          "risk_level": "low"
        }
      ],
      "health_advice": [
        {
          "condition": "高血压",
          "advice": "建议限制食用"
        }
      ]
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
}
```

**analysis 对象字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| score | int | 健康评分 0-100 |
| summary | string | 分析总结 |
| top_risks | array | 主要风险列表 |
| ingredients | array | 配料分析列表 |
| health_advice | array | 健康建议列表 |

**ingredient 配料项字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 配料名称 |
| category | string | 配料分类 |
| safety_status | string | 安全状态 |
| risk_level | string | 风险等级 |

**错误码**:
- 401: 未认证
- 404: 报告不存在

---

### DELETE `/reports/{report_id}` - 删除报告

软删除当前用户自己的报告记录。

**路径参数**:
- `report_id`: UUID 报告ID

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

**错误码**:
- 401: 未认证
- 404: 报告不存在

**说明**: 软删除后报告仍存储在数据库中，但不会在列表中显示。

---

## 用户接口 `/users`

### GET `/users/me` - 获取当前用户资料

获取当前登录用户的基本信息。

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "display_name": "李雷",
    "avatar_url": "https://example.com/avatar.png",
    "is_verified": true,
    "created_at": "2026-03-26T00:00:00Z"
  }
}
```

**响应字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | UUID | 用户ID |
| email | string | 邮箱 |
| display_name | string/null | 显示名称 |
| avatar_url | string/null | 头像URL |
| is_verified | boolean | 邮箱是否已验证 |
| created_at | datetime | 账号创建时间 |

**错误码**:
- 401: 未认证

---

### PATCH `/users/me` - 更新当前用户资料

更新当前用户的显示名称和头像。

**请求体**:
```json
{
  "display_name": "新名称",
  "avatar_url": "https://example.com/new-avatar.png"
}
```

**所有字段均可选**:
- `display_name`: 1-64字符，显示名称
- `avatar_url`: 最大1024字符，头像地址

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "display_name": "新名称",
    "avatar_url": "https://example.com/new-avatar.png",
    "is_verified": true,
    "created_at": "2026-03-26T00:00:00Z"
  }
}
```

**错误码**:
- 401: 未认证

---

### POST `/users/change-password` - 修改当前用户密码

修改当前用户的登录密码。

**请求体**:
```json
{
  "current_password": "OldPass123",
  "new_password": "NewStrongPass123"
}
```

**密码规则**: 新密码8-32位，需包含大小写字母和数字

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

**说明**: 修改密码后，所有refresh token会被撤销，需要重新登录。

**错误码**:
- 401: 未认证 / 当前密码错误

---

### DELETE `/users/me` - 注销当前账号

注销当前账号，执行软删除。

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

**说明**:
- 执行软删除，设置 `deleted_at` 时间戳
- 设置 `is_active` 为 false
- 所有refresh token会被撤销
- 账号数据仍保留在数据库中

**错误码**:
- 401: 未认证

---

## 偏好接口 `/preferences`

### GET `/preferences/me` - 获取当前用户偏好

获取当前用户的健康偏好设置。

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "focus_groups": ["adult", "fitness"],
    "health_conditions": ["hypertension"],
    "allergies": ["花生", "虾"],
    "updated_at": "2026-03-26T00:00:00Z"
  }
}
```

**响应字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| focus_groups | array | 关注人群 |
| health_conditions | array | 健康状况 |
| allergies | array | 过敏源 |
| updated_at | datetime | 最后更新时间 |

**focus_groups 可选值**:

| 值 | 说明 |
|----|------|
| adult | 成年人 |
| child | 儿童 |
| elder | 老年人 |
| pregnant | 孕妇 |
| fitness | 健身人群 |

**health_conditions 可选值**:

| 值 | 说明 |
|----|------|
| diabetes | 糖尿病 |
| hypertension | 高血压 |
| hyperuricemia | 高尿酸血症 |
| allergy | 过敏体质 |

**错误码**:
- 401: 未认证

---

### PUT `/preferences/me` - 保存当前用户偏好

保存当前用户的健康偏好设置。

**请求体**:
```json
{
  "focus_groups": ["adult", "pregnant"],
  "health_conditions": ["diabetes", "hypertension"],
  "allergies": ["花生", "虾", "牛奶"]
}
```

**所有字段均可选**:

| 字段 | 类型 | 说明 |
|------|------|------|
| focus_groups | array | 关注人群 |
| health_conditions | array | 健康状况 |
| allergies | array | 过敏源（会自动去重） |

**响应**:
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "focus_groups": ["adult", "pregnant"],
    "health_conditions": ["diabetes", "hypertension"],
    "allergies": ["花生", "虾", "牛奶"],
    "updated_at": "2026-03-26T00:00:00Z"
  }
}
```

**错误码**:
- 401: 未认证

---

## 健康检查接口 `/health`

### GET `/health` - 健康检查

返回应用及依赖服务的实时健康状态。

**响应**:
```json
{
  "code": 0,
  "message": "健康检查完成",
  "data": {
    "status": "healthy",
    "timestamp": "2026-03-26T00:00:00Z",
    "version": "1.0.0",
    "services": {
      "database": "up",
      "redis": "up",
      "minio": "up",
      "yolo_model": "up",
      "chromadb": "up",
      "ollama_embedding": "up",
      "ocr_runtime": "up"
    }
  }
}
```

**status 状态说明**:

| 状态 | 说明 |
|------|------|
| healthy | 所有服务正常 |
| degraded | 部分服务异常 |

**services 服务说明**:

| 服务 | 说明 |
|------|------|
| database | PostgreSQL 数据库 |
| redis | Redis 缓存 |
| minio | MinIO 对象存储 |
| yolo_model | YOLO 目标检测模型 |
| chromadb | ChromaDB 向量数据库 |
| ollama_embedding | Ollama Embedding 服务 |
| ocr_runtime | PaddleOCR 识别服务 |

---

## 错误响应格式

### 统一错误格式

```json
{
  "code": 401,
  "message": "Invalid credentials",
  "data": null
}
```

### 验证错误格式

```json
{
  "code": 400,
  "message": "Validation error",
  "data": {
    "field_name": ["error message"]
  }
}
```

### 错误码对照表

| HTTP状态码 | 业务错误码 | 说明 |
|------------|-----------|------|
| 400 | 0 | 请求参数错误 |
| 401 | 40101 | 令牌无效 |
| 401 | 40102 | 令牌过期 |
| 401 | 40103 | 邮箱未验证 |
| 401 | 40104 | 账号已被禁用 |
| 403 | 40301 | 禁止访问 |
| 404 | 40401 | 资源不存在 |
| 409 | 40901 | 邮箱已注册 |
| 429 | 42901 | 请求过于频繁 |
| 500 | 50001 | 服务器内部错误 |
| 503 | 50301 | 外部服务不可用 |

---

## 认证说明

### 获取令牌

1. **登录获取**:
```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "StrongPass123"
}
```

2. **使用令牌**: 在请求头中携带
```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 令牌刷新

当 `access_token` 过期时，使用 `refresh_token` 获取新令牌:

```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### 登出

```bash
POST /api/v1/auth/logout
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

---

## 分页格式

### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码，从1开始 |
| page_size | int | 10 | 每页条数，最大50 |

### 响应格式

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 10,
    "total_pages": 10
  }
}
```
