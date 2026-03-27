# FoodGuard 前端接口文档

本文档详细描述了 FoodGuard 前端应用所需调用的所有后端接口。所有的接口均使用统一的响应结构，并在需要认证的接口中使用 Bearer Token 进行鉴权。

## 1. 基础约定

### 1.1 Base URL
- 基础路径：`/api/v1`

### 1.2 统一响应结构
所有接口的返回数据都遵循以下 JSON 格式：
```json
{
  "code": 0,           // 0 表示成功，非 0 表示业务或系统级错误
  "message": "ok",     // 给用户看的提示信息或错误原因
  "data": {}           // 具体的业务数据（失败时通常为 null）
}
```

### 1.3 统一分页响应结构
列表类型的接口返回的 `data` 字段结构如下：
```json
{
  "items": [],         // 当前页的数据列表
  "total": 100,        // 数据总条数
  "page": 1,           // 当前页码（从 1 开始）
  "page_size": 10,     // 每页条数
  "total_pages": 10    // 总页数
}
```

### 1.4 鉴权机制
- **认证方式**：需要在 HTTP 请求头中添加 `Authorization: Bearer <access_token>`。
- **Token 获取**：通过“登录”或“刷新 Token”接口获取。
- **无感刷新**：前端在收到 `401 Unauthorized` 状态码时，会自动调用 `/auth/refresh` 接口尝试刷新 Token 并重试请求。

---

## 2. 认证模块 (Auth)

### 2.1 发送注册验证码
- **路径**：`POST /auth/register/send-code`
- **用途**：在用户注册前，向目标邮箱发送包含 6 位验证码的邮件。
- **是否需要认证**：否
- **请求 Body**:
  ```json
  {
    "email": "user@example.com"
  }
  ```
- **响应 Data**:
  ```json
  {
    "cooldown_seconds": 60  // 提示前端下一次可以发送验证码的冷却时间（秒）
  }
  ```

### 2.2 用户注册
- **路径**：`POST /auth/register`
- **用途**：校验验证码并创建新用户账号。
- **是否需要认证**：否
- **请求 Body**:
  ```json
  {
    "email": "user@example.com",
    "code": "123456",
    "password": "S3cureP@ssw0rd"
  }
  ```
- **响应 Data**: `null`

### 2.3 用户登录
- **路径**：`POST /auth/login`
- **用途**：验证邮箱和密码，成功后返回访问令牌和刷新令牌。
- **是否需要认证**：否
- **请求 Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "S3cureP@ssw0rd"
  }
  ```
- **响应 Data**:
  ```json
  {
    "access_token": "eyJhbG...",
    "refresh_token": "eyJhbG...",
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```

### 2.4 刷新 Token
- **路径**：`POST /auth/refresh`
- **用途**：当 access_token 过期时，使用 refresh_token 换取新的 token 组。
- **是否需要认证**：否
- **请求 Body**:
  ```json
  {
    "refresh_token": "eyJhbG..."
  }
  ```
- **响应 Data**: 与【用户登录】接口返回一致。

### 2.5 退出登录
- **路径**：`POST /auth/logout`
- **用途**：使当前设备的 refresh_token 失效。
- **是否需要认证**：是
- **请求 Body**:
  ```json
  {
    "refresh_token": "eyJhbG..."
  }
  ```
- **响应 Data**: `null`

---

## 3. 用户与偏好设置模块 (User & Preferences)

### 3.1 获取当前用户信息
- **路径**：`GET /users/me`
- **用途**：获取当前登录用户的基本信息，用于前端状态初始化和个人主页展示。
- **是否需要认证**：是
- **请求参数**：无
- **响应 Data**:
  ```json
  {
    "user_id": "uuid-string",
    "email": "user@example.com",
    "display_name": "用户昵称",
    "avatar_url": "https://...",  // 可以为 null
    "is_verified": true,
    "created_at": "2026-03-26T00:00:00Z"
  }
  ```

### 3.2 获取当前用户健康偏好
- **路径**：`GET /preferences/me`
- **用途**：获取用户设置的健康关注点、特殊疾病和过敏源，以便在标签分析时进行个性化加粗和预警。
- **是否需要认证**：是
- **请求参数**：无
- **响应 Data**:
  ```json
  {
    "focus_groups": ["adult", "elder"],            // 关注人群枚举
    "health_conditions": ["hypertension"],         // 特殊健康状况枚举（含 "allergy"）
    "allergies": ["花生", "牛奶"],                  // 具体的过敏源文本列表
    "updated_at": "2026-03-26T00:00:00Z"
  }
  ```

### 3.3 更新当前用户健康偏好
- **路径**：`PUT /preferences/me`
- **用途**：保存用户在个人设置页面修改的健康偏好。
- **是否需要认证**：是
- **请求 Body**:
  ```json
  {
    "focus_groups": ["adult", "elder"],
    "health_conditions": ["hypertension", "allergy"],
    "allergies": ["花生", "牛奶", "麸质"]
  }
  ```
- **响应 Data**: 与【获取当前用户健康偏好】接口返回一致。

---

## 4. 标签分析流程模块 (Analysis)

### 4.1 上传图片并创建任务
- **路径**：`POST /analysis/upload`
- **用途**：上传食品标签图片（配料表或营养成分表），触发后端的异步分析流程。
- **是否需要认证**：是
- **请求类型**：`multipart/form-data`
- **请求字段**：
  - `file`: (File) 图片文件对象，支持 JPG/PNG/WEBP。
- **响应 Data**:
  ```json
  {
    "task_id": "uuid-string",
    "status": "queued",
    "created_at": "2026-03-26T00:00:00Z"
  }
  ```

### 4.2 轮询查询任务状态
- **路径**：`GET /analysis/tasks/{task_id}`
- **用途**：前端根据上一步返回的 task_id 定时轮询此接口，以获取图片 OCR 和 AI 分析的实时进度。
- **是否需要认证**：是
- **请求参数**：路径参数 `task_id`
- **响应 Data**:
  ```json
  {
    "task_id": "uuid-string",
    "status": "processing",                  // 状态枚举：queued, processing, completed, failed
    "progress_message": "正在执行 OCR 识别",   // 用于前端 UI 展示的具体进度文案
    "created_at": "2026-03-26T00:00:00Z",
    "completed_at": null,
    "report_id": null,                       // 当 status 变为 completed 时，此字段会带有结果报告的 ID
    "error_message": null,                   // 当 status 变为 failed 时，此字段带有错误原因
    "nutrition_parse_source": "llm"
  }
  ```

---

## 5. 分析报告与历史模块 (Reports)

### 5.1 获取报告列表（历史记录）
- **路径**：`GET /reports`
- **用途**：分页获取用户历史上进行过的所有食品标签分析报告摘要。
- **是否需要认证**：是
- **请求参数 (Query)**：
  - `page`: (Number) 页码，默认 1
  - `page_size`: (Number) 每页条数，默认 10
- **响应 Data**: 统一分页响应结构，其中 `items` 数组的元素结构如下：
  ```json
  {
    "report_id": "uuid-string",
    "task_id": "uuid-string",
    "score": 85,                         // 综合健康评分 (0-100)
    "summary": "总体较健康，但需注意钠含量...", // AI 总结的一句话摘要
    "image_url": "https://...",          // 对应的标签缩略图
    "created_at": "2026-03-26T00:00:00Z"
  }
  ```

### 5.2 获取报告详情
- **路径**：`GET /reports/{report_id}`
- **用途**：获取某次分析任务的完整诊断详情，包括识别的配料、营养成分表和 AI 给出的健康评估。
- **是否需要认证**：是
- **请求参数**：路径参数 `report_id`
- **响应 Data**:
  ```json
  {
    "report_id": "uuid-string",
    "task_id": "uuid-string",
    "image_url": "https://...",
    "ingredients_text": "配料：水，白砂糖，魔芋粉...",  // OCR 识别出的原始配料文本
    "nutrition": {                               // 提取出的营养成分键值对
      "能量": "100kJ",
      "蛋白质": "0g",
      "钠": "2000mg"
    },
    "nutrition_parse_source": "llm",
    "analysis": {
      "score": 35,
      "summary": "该食品钠含量严重超标，且含有对痛风不利的成分。",
      "hazards": [                               // 风险点列表
        { "level": "high", "desc": "钠含量达到每日建议摄入量的 100%" },
        { "level": "medium", "desc": "含有防腐剂山梨酸钾" }
      ],
      "benefits": []                             // 营养价值列表
    },
    "created_at": "2026-03-26T00:00:00Z"
  }
  ```

### 5.3 删除历史报告
- **路径**：`DELETE /reports/{report_id}`
- **用途**：从历史记录中彻底删除某条分析报告。
- **是否需要认证**：是
- **请求参数**：路径参数 `report_id`
- **响应 Data**: `null`

---

## 6. 常见错误码参考

在响应的 `code` 字段中，非 `0` 的值代表异常：

- `0`：成功
- `4001`：参数错误或表单校验失败（如邮箱格式错误）
- `4010`：未登录、Token 无效或 Token 已过期
- `4030`：无权限访问该资源
- `4040`：资源不存在（如查询不存在的报告 ID）
- `4290`：请求过于频繁（如频繁发送验证码或上传文件）
- `5000`：服务器内部异常或 AI 推理引擎崩溃