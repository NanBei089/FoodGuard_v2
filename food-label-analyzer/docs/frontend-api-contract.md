# FoodGuard 前后端对接契约（v0.1）

本文档用于前端（React+TypeScript）与后端（FastAPI）对接时的接口与数据结构约定，作为实现与联调的单一事实来源（SSOT）。

## 1. 基本约定

### 1.1 Base URL
- API 前缀：`/api/v1`

### 1.2 统一响应结构
所有成功/失败响应均使用统一结构（HTTP 状态码仍保留语义，但前端以 `code`/`message` 为主）。

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code`: `0` 表示成功；非 `0` 表示业务失败
- `message`: 给人看的错误/提示
- `data`: 业务载荷；失败时可为 `null`

### 1.3 认证（Bearer Token）
- 需要登录的接口：请求头必须包含
  - `Authorization: Bearer <access_token>`
- token 来源：`POST /api/v1/auth/login` 或 `POST /api/v1/auth/refresh`

### 1.4 时间与 ID
- `created_at`/`completed_at`：ISO 8601 字符串（UTC 或带时区偏移）
- `task_id`/`report_id`/`user_id`：字符串（UUID 形式）

### 1.5 分页
列表接口统一采用：
- `page`（从 1 开始）
- `page_size`（默认 10）

统一分页响应：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 10,
  "total_pages": 0
}
```

## 2. 认证 Auth（现有）

> 路由实现参考：[auth.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/auth.py)  
> Schema 参考：[auth.py（schema）](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/auth.py)

### 2.1 发送注册验证码
`POST /api/v1/auth/register/send-code`

请求：
```json
{ "email": "user@example.com" }
```

响应：
```json
{ "code": 0, "message": "ok", "data": { "cooldown_seconds": 60 } }
```

### 2.2 注册
`POST /api/v1/auth/register`

请求：
```json
{ "email": "user@example.com", "code": "123456", "password": "S3cureP@ssw0rd" }
```

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

### 2.3 登录
`POST /api/v1/auth/login`

请求：
```json
{ "email": "user@example.com", "password": "S3cureP@ssw0rd" }
```

响应（TokenResponse）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "xxx",
    "refresh_token": "yyy",
    "token_type": "bearer",
    "expires_in": 3600
  }
}
```

### 2.4 刷新 Token
`POST /api/v1/auth/refresh`

请求：
```json
{ "refresh_token": "yyy" }
```

响应：同登录

### 2.5 忘记密码（发邮件/发码）
`POST /api/v1/auth/forgot-password`

请求：
```json
{ "email": "user@example.com" }
```

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

### 2.6 重置密码
`POST /api/v1/auth/reset-password`

请求：
```json
{ "token": "reset_token", "new_password": "N3wP@ssw0rd" }
```

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

### 2.7 登出（缺口，建议新增）
`POST /api/v1/auth/logout`

用途：
- 前端点击“退出登录”时让 refresh_token 失效（可选：access_token 黑名单）

请求（两种二选一）：
1) Bearer + body
```json
{ "refresh_token": "yyy" }
```
2) 若改为 Cookie 存储 refresh_token：无需 body，仅 Bearer/或仅 Cookie

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

## 3. 分析 Analysis（现有）

> 路由实现参考：[analysis.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/analysis.py)  
> Schema 参考：[analysis.py（schema）](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/analysis.py)

### 3.1 上传图片并创建分析任务
`POST /api/v1/analysis/upload`

- 认证：需要
- Content-Type：`multipart/form-data`
- 表单字段：
  - `file`: 图片文件

响应（TaskCreateResponse）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "uuid",
    "status": "queued",
    "created_at": "2026-03-26T00:00:00Z"
  }
}
```

### 3.2 查询任务状态（轮询）
`GET /api/v1/analysis/tasks/{task_id}`

响应（TaskStatusResponse）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "task_id": "uuid",
    "status": "processing",
    "progress_message": "OCR 识别中",
    "created_at": "2026-03-26T00:00:00Z",
    "completed_at": null,
    "report_id": null,
    "error_message": null,
    "nutrition_parse_source": "llm"
  }
}
```

#### status 枚举（前端必须兼容）
- `queued`
- `processing`
- `completed`
- `failed`

> 若后端还有更多状态，请在 schema 中固定并同步更新。

#### 前端建议轮询策略
- 间隔：`1.5s -> 2s -> 3s` 逐步退避
- 超时：建议 2-5 分钟（按模型推理时长调优）
- `completed` 时跳转：`/reports/{report_id}`
- `failed` 时展示：`error_message`

## 4. 报告 Reports（现有）

> 路由实现参考：[reports.py](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/api/v1/reports.py)  
> Schema 参考：[report.py（schema）](file:///e:/GraduationProject/foodguard/food-label-analyzer/app/schemas/report.py)

### 4.1 报告列表（历史记录）
`GET /api/v1/reports?page=1&page_size=10`

响应（PageResponse[ReportListItemSchema]）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "report_id": "uuid",
        "task_id": "uuid",
        "score": 85,
        "summary": "总体较健康，注意钠含量…",
        "image_url": "https://...",
        "created_at": "2026-03-26T00:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 10,
    "total_pages": 1
  }
}
```

### 4.2 报告详情
`GET /api/v1/reports/{report_id}`

响应（ReportDetailResponseSchema）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "report_id": "uuid",
    "task_id": "uuid",
    "image_url": "https://...",
    "ingredients_text": "配料：...",
    "nutrition": {},
    "nutrition_parse_source": "llm",
    "analysis": {},
    "rag_summary": {},
    "artifact_urls": {},
    "created_at": "2026-03-26T00:00:00Z"
  }
}
```

### 4.3 删除报告（缺口，建议新增）
`DELETE /api/v1/reports/{report_id}`

用途：
- 历史记录页“删除”操作

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

## 5. 用户与偏好（缺口，Profile / Onboarding 必需）

本节为前端重建后“个人中心、首次引导、健康偏好”的核心契约。当前后端未提供路由，建议按下述方式新增。

### 5.1 获取当前用户（Profile 顶部展示、表单初始化）
`GET /api/v1/users/me`

响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "display_name": "李雷",
    "avatar_url": null,
    "is_verified": true,
    "created_at": "2026-03-26T00:00:00Z"
  }
}
```

### 5.2 更新当前用户（昵称/头像等）
`PATCH /api/v1/users/me`

请求（可选字段）：
```json
{
  "display_name": "李雷",
  "avatar_url": "https://..."
}
```

响应：同 `GET /users/me`

### 5.3 修改密码（Profile）
`POST /api/v1/users/change-password`

请求：
```json
{ "current_password": "OldP@ss", "new_password": "NewP@ss" }
```

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

### 5.4 注销账号（Danger Zone）
`DELETE /api/v1/users/me`

响应：
```json
{ "code": 0, "message": "ok", "data": null }
```

### 5.5 偏好：获取（Profile / Onboarding 回显）
`GET /api/v1/preferences/me`

响应：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "focus_groups": ["adult", "elder"],
    "health_conditions": ["hypertension"],
    "allergies": ["花生", "牛奶"],
    "updated_at": "2026-03-26T00:00:00Z"
  }
}
```

### 5.6 偏好：更新（Profile / Onboarding 保存）
`PUT /api/v1/preferences/me`

请求：
```json
{
  "focus_groups": ["adult", "elder"],
  "health_conditions": ["hypertension"],
  "allergies": ["花生", "牛奶"]
}
```

响应：同 `GET /preferences/me`

#### focus_groups 枚举（建议）
- `adult`（自己/成年人）
- `child`（儿童）
- `elder`（老年人）
- `pregnant`（孕妇）
- `fitness`（健身/减脂）

#### health_conditions 枚举（建议）
- `diabetes`
- `hypertension`
- `hyperuricemia`
- `allergy`（仅表示有过敏；具体过敏源在 allergies）

> 备注：如果你希望“食物过敏”与“过敏源”强绑定：当 `allergies.length>0` 即认为 `health_conditions` 自动包含 `allergy`（后端可自动派生，不必由前端重复传）。

## 6. 错误码建议（可选）
- `0`：成功
- `4001`：参数错误（校验失败）
- `4010`：未登录/Token 无效
- `4030`：无权限
- `4040`：资源不存在
- `4290`：请求过频（验证码/上传限流）
- `5000`：服务端异常

## 7. 前端页面与接口映射（验收用）
- Login：`POST /auth/login`、`POST /auth/refresh`、（建议）`POST /auth/logout`
- Register：`POST /auth/register/send-code`、`POST /auth/register`
- Home：`GET /reports`（最近报告），（可选）`GET /dashboard/summary`
- Upload：`POST /analysis/upload`
- Analyzing：`GET /analysis/tasks/{task_id}`
- History：`GET /reports`、（建议）`DELETE /reports/{id}`
- Report Detail：`GET /reports/{id}`
- Profile：`GET /users/me`、`PATCH /users/me`、`POST /users/change-password`、`DELETE /users/me`、`GET/PUT /preferences/me`

