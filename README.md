# FoodGuard

FoodGuard 是一个面向预包装食品标签场景的智能分析系统。项目通过图像识别、OCR、配料提取、营养成分解析和大模型推理，对食品标签进行结构化分析，并生成更易理解的健康报告。

## 功能概览

- 上传食品标签图片并创建分析任务
- 自动识别配料表与营养成分表
- 提取关键配料、营养数据和潜在风险点
- 结合知识检索与大模型生成健康解读
- 输出健康评分、风险摘要和人群建议
- 支持历史报告查看、删除和用户偏好管理

## 项目结构

```text
FoodGuard/
├─ food-label-analyzer/    FastAPI 后端服务
├─ food-label-frontend/    React 前端应用
├─ images/                 样例图片
├─ docs/                   项目说明文档
└─ output/                 调试与自动化输出
```

## 技术栈

后端：

- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- MinIO
- ChromaDB
- YOLO / PaddleOCR / Ollama / DeepSeek

前端：

- React
- TypeScript
- Vite
- React Router
- Zustand
- Axios
- Tailwind CSS

## 快速开始

### 后端

```powershell
conda activate foodguard-env
cd food-label-analyzer
pip install -r requirements-dev.txt
Copy-Item .env.example .env
$env:SKIP_STARTUP_CHECKS="true"
uvicorn app.main:app --reload
```

默认地址：

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

### 前端

```powershell
cd food-label-frontend
npm install
npm run dev
```

默认地址：

- Web: `http://localhost:5173`

开发环境下，前端会将 `/api` 代理到本地后端。

## 常用命令

后端测试：

```powershell
cd food-label-analyzer
python -m pytest
```

后端聚焦测试：

```powershell
cd food-label-analyzer
python -m pytest tests/test_config.py tests/test_core_modules.py tests/test_infra_modules.py
```

前端构建：

```powershell
cd food-label-frontend
npm run build
```

前端静态检查：

```powershell
cd food-label-frontend
npm run lint
```

## 核心目录说明

### `food-label-analyzer/`

- `app/api/v1/`: API 路由
- `app/core/`: 配置、日志、安全、错误处理
- `app/db/`: 数据库与 Redis 封装
- `app/models/`: ORM 模型
- `app/schemas/`: 请求与响应模型
- `app/services/`: 服务层逻辑
- `app/tasks/`: 异步任务入口
- `app/workers/`: OCR、YOLO、提取器、RAG、LLM 等分析模块
- `tests/`: 后端测试

### `food-label-frontend/`

- `src/pages/`: 登录、注册、首页、历史记录、报告详情、个人资料等页面
- `src/components/`: 通用组件与布局组件
- `src/api/`: 前端接口封装
- `src/store/`: 状态管理
- `src/lib/`: 业务辅助函数

## 文档入口

- [后端 README](food-label-analyzer/README.md)
- [前端 README](food-label-frontend/README.md)
- [后端 API 文档](food-label-analyzer/API_DOCUMENTATION.md)
- [分析链路说明](food-label-analyzer/ANALYSIS_PIPELINE.md)
- [后端深度说明](docs/backend-codebase-deep-dive.md)
- [前端深度说明](docs/frontend-codebase-deep-dive.md)

## 说明

- `images/` 目录提供了适合本地联调和演示的食品标签样例图
- 完整分析链路依赖数据库、对象存储、缓存、模型文件和 OCR 相关服务
- 配置项请以 `food-label-analyzer/.env.example` 为准
