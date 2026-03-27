# FoodGuard 本地启动说明

这份文档覆盖当前仓库的完整本地启动方式，包括：

- 前端 `food-label-frontend/`
- 后端 `food-label-analyzer/`
- PostgreSQL
- Redis
- MinIO
- Celery worker
- OCR / LLM / RAG 相关外部依赖

## 1. 先回答最常见的问题

### 1.1 前端要不要单独启动

要。

前端是一个独立的 Vite 开发服务器，目录是 `food-label-frontend/`，命令是：

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm install
npm run dev
```

默认地址：

- `http://127.0.0.1:5173`

### 1.2 后端 API 要不要单独启动

要。

后端是一个独立的 FastAPI 进程，目录是 `food-label-analyzer/`，命令是：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
uvicorn app.main:app --reload
```

默认地址：

- `http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`

### 1.3 Celery worker 要不要单独启动

要。

上传图片分析不是在 FastAPI 进程里同步执行，而是会投递到 Celery 队列。当前上传接口里直接调用：

- `app/api/v1/analysis.py`
- `celery_app.send_task(..., queue="analysis")`

所以如果你要跑“上传图片 -> 排队 -> 分析 -> 出报告”整条链路，必须再单独开一个终端启动 Celery worker。

命令：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
python -m celery -A app.tasks.celery_app:celery_app worker -Q analysis -l info
```

如果你的环境里 `celery` 命令可直接执行，也可以写成：

```powershell
celery -A app.tasks.celery_app:celery_app worker -Q analysis -l info
```

### 1.4 `app/workers/` 要不要一个个单独启动

不要。

`app/workers/` 里面的 `ocr_worker.py`、`yolo_worker.py`、`rag_worker.py`、`llm_worker.py` 都只是 Python 模块，不是单独的服务进程。

真正需要单独启动的是：

- FastAPI API 进程
- Celery worker 进程

也就是说：

- `worker` 指的是 `Celery worker`
- 不是指 `app/workers/` 目录里的每个文件

### 1.5 还要不要启动 Celery beat

当前项目不用。

现在仓库里只需要：

- Celery worker

不需要再额外起：

- Celery beat
- Flower

## 2. 完整链路到底要起哪些东西

如果你的目标是完整使用系统，建议把下面这些全部准备好：

| 组件 | 是否单独启动 | 用途 |
| --- | --- | --- |
| 前端 Vite | 是 | 页面访问与交互 |
| FastAPI API | 是 | 登录、上传、任务查询、报告查询 |
| Celery worker | 是 | 异步执行图片分析任务 |
| PostgreSQL | 是 | 用户、任务、报告数据 |
| Redis | 是 | Celery broker/result backend，验证码缓存 |
| MinIO | 是 | 图片与中间产物对象存储 |
| PaddleOCR 在线服务 | 否，本地只需可访问 | OCR 与表格识别 |
| DeepSeek API | 否，本地只需可访问 | 大模型营养解析与分析建议 |
| Ollama | 是 | 本地向量 embedding |
| ChromaDB 数据目录 | 否 | 本地 RAG 检索数据 |
| SMTP | 否，本地只需可访问 | 注册验证码、重置密码邮件 |

补充说明：

- `models_store/yolo/yolo26s.onnx` 已经在仓库里，不需要额外下载启动一个 YOLO 服务。
- `chroma_data/` 已经在仓库里，不需要单独再起一个 Chroma 服务。
- 但 `Ollama` 仍然要启动，因为向量检索时需要调用 embedding 模型。

## 3. 不同场景下最少要启动什么

### 3.1 只看前端静态页面

只启动前端：

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm install
npm run dev
```

说明：

- 只能看纯页面壳子。
- 登录、上传、历史记录、报告页真实数据都跑不通。

### 3.2 只看后端 Swagger / OpenAPI

只启动后端 API，并跳过启动检查：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
Copy-Item .env.example .env
$env:SKIP_STARTUP_CHECKS="true"
uvicorn app.main:app --reload
```

说明：

- 适合先看 `/docs`。
- 不代表上传分析链路可用。

### 3.3 跑登录、用户资料、历史记录这类基础功能

建议至少准备：

- 前端
- 后端 API
- PostgreSQL

如果你要跑：

- 注册验证码
- 忘记密码

还需要：

- Redis
- SMTP

### 3.4 跑完整“上传图片分析”

必须准备：

- 前端
- 后端 API
- PostgreSQL
- Redis
- MinIO
- Celery worker
- PaddleOCR 在线服务
- DeepSeek API Key
- Ollama
- 本地 `chroma_data/`

如果少了 Celery worker，最常见现象就是：

- 上传成功
- 任务状态一直停在 `queued`

## 4. 后端环境准备

在 PowerShell 中执行：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

至少要确认下面这些配置正确：

- `APP_SECRET_KEY`
- `DATABASE_URL`
- `DATABASE_SYNC_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `PADDLEOCR_TOKEN`
- `DEEPSEEK_API_KEY`
- `OLLAMA_BASE_URL`
- `CHROMADB_PATH`
- `YOLO_MODEL_PATH`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`

本地开发建议特别注意：

- `FRONTEND_URL=http://localhost:5173`
- `CORS_ORIGINS=http://localhost:3000,http://localhost:5173`
- Redis 建议优先写 `127.0.0.1`，不要写 `localhost`

原因：

- Windows 下某些客户端会优先走 IPv6 的 `::1`
- Docker 端口映射常常只监听 IPv4
- 最后表现出来就是 Redis 端口明明开着，但应用还是超时

推荐 Redis 配置：

```powershell
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
```

## 5. 前端环境准备

在另一个 PowerShell 中执行：

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm install
npm run dev
```

当前前端开发服务器配置：

- 端口：`5173`
- Vite 代理：`/api -> http://localhost:8000`

也就是说，本地默认不需要额外写前端 `.env` 去指定 API 地址，只要后端跑在 `8000` 即可。

## 6. 数据库迁移

如果数据库还没同步到当前代码的最新 schema，先执行：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
alembic upgrade head
```

这个步骤建议放在第一次启动前，或者每次更新后端数据库结构之后执行。

## 7. 推荐启动顺序

建议按下面顺序启动：

```text
1. PostgreSQL
2. Redis
3. MinIO
4. Ollama
5. 确认 PaddleOCR / DeepSeek / SMTP 配置可用
6. conda activate foodguard-env
7. cd food-label-analyzer
8. pip install -r requirements-dev.txt
9. Copy-Item .env.example .env
10. alembic upgrade head
11. uvicorn app.main:app --reload
12. 另开一个终端启动 celery worker
13. cd food-label-frontend
14. npm install
15. npm run dev
```

## 8. 直接可复制的启动命令

### 8.1 终端 1：后端 API

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
uvicorn app.main:app --reload
```

### 8.2 终端 2：Celery worker

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
python -m celery -A app.tasks.celery_app:celery_app worker -Q analysis -l info
```

### 8.3 终端 3：前端

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm run dev
```

## 9. 快速排查

### 9.1 上传成功，但任务一直 `queued`

优先排查：

- Redis 没启动
- Celery worker 没启动
- worker 没监听 `analysis` 队列

### 9.2 API 启动时报依赖检查失败

如果你只是想先把 API 起起来看文档，可以先临时跳过：

```powershell
$env:SKIP_STARTUP_CHECKS="true"
```

但这只是跳过启动检查，不等于业务链路真的可用。

### 9.3 注册收不到验证码

优先排查：

- `SMTP_*` 配置不对
- 邮箱服务本身不可达
- Redis 没启动

### 9.4 登录没问题，但上传时报对象存储错误

优先排查：

- MinIO 没启动
- `MINIO_ENDPOINT` 配置不对
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` 不对

### 9.5 上传后 worker 报 OCR 或 LLM 错

优先排查：

- `PADDLEOCR_TOKEN` 是否有效
- `DEEPSEEK_API_KEY` 是否有效
- `OLLAMA_BASE_URL` 是否可访问
- `CHROMADB_PATH` 是否指向当前仓库里的 `./chroma_data`

## 10. 一句话结论

如果你问的是：

- “worker 要不要单独启动？”
- “Celery 要不要单独启动？”

答案是：

- 要，Celery worker 必须单独开一个终端启动。
- `app/workers/` 目录里的模块不用一个个单独启动。
- 当前项目不需要 Celery beat。
