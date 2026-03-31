# FoodGuard

FoodGuard 是一个面向预包装食品标签识别与健康分析的全栈项目。仓库同时包含：

- `food-label-analyzer/`: FastAPI 后端，负责认证、图片分析任务、报告查询，以及 YOLO、OCR、RAG、LLM 等分析链路。
- `food-label-frontend/`: React + TypeScript + Vite 前端，负责注册登录、上传图片、查看报告、历史记录和个人资料。
- `images/`: 用于手工调试和演示的食品标签样例图片。
- `docs/`: 面向代码阅读、项目汇报和论文整理的深度说明文档。

## 仓库结构

```text
foodguard/
|- food-label-analyzer/           后端主项目
|- food-label-frontend/           前端主项目
|- food-label-frontend-prototype/ 早期原型页面
|- images/                        样例图片
|- docs/                          深度说明文档
|- output/                        调试、截图、自动化输出
|- AGENTS.md                      仓库级协作约定
```

## 技术栈

后端：

- FastAPI
- SQLAlchemy + PostgreSQL
- Redis
- MinIO
- ChromaDB
- YOLO / PaddleOCR / Ollama / DeepSeek
- pytest

前端：

- React 19
- TypeScript
- React Router 7
- Zustand
- Axios
- Tailwind CSS 4
- Vite 8

## 快速开始

### 1. 启动后端

推荐使用仓库当前约定的 Conda 环境：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
pip install -r requirements-dev.txt
```

配置环境变量：

```powershell
Copy-Item .env.example .env
```

开发模式启动：

```powershell
$env:SKIP_STARTUP_CHECKS="true"
uvicorn app.main:app --reload
```

说明：

- 默认 API 地址是 `http://localhost:8000`
- FastAPI 文档默认可在 `http://localhost:8000/docs` 查看
- 如果你要验证完整分析链路，需要保证 Postgres、Redis、MinIO、YOLO 模型、ChromaDB 和 OCR 相关依赖可用

### 2. 启动前端

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm install
npm run dev
```

说明：

- 默认前端地址是 `http://localhost:5173`
- 开发环境下 Vite 已将 `/api` 代理到 `http://localhost:8000`
- 如果需要直连其它后端，可设置 `VITE_API_URL`

### 3. 本地联调

当后端运行在 `8000`、前端运行在 `5173` 时，直接打开：

```text
http://localhost:5173
```

典型业务流包括：

- 注册 / 登录
- 首次使用引导
- 上传食品标签图片
- 轮询分析任务状态
- 查看报告详情
- 查看历史记录
- 修改个人资料和偏好

## 常用命令

后端测试：

```powershell
conda activate foodguard-env
cd E:\GraduationProject\foodguard\food-label-analyzer
python -m pytest
```

后端聚焦测试：

```powershell
python -m pytest tests/test_config.py tests/test_core_modules.py tests/test_infra_modules.py
```

前端构建与检查：

```powershell
cd E:\GraduationProject\foodguard\food-label-frontend
npm run build
npm run lint
```

## 关键目录说明

### 后端 `food-label-analyzer/`

- `app/api/v1/`: 路由层，当前包含 `auth`、`analysis`、`reports`
- `app/core/`: 配置、日志、错误处理、安全、邮件等基础模块
- `app/db/`: SQLAlchemy 会话和 Redis 封装
- `app/models/`: ORM 模型
- `app/schemas/`: Pydantic 请求与响应模型
- `app/services/`: 服务层和业务编排
- `app/tasks/`: Celery 任务入口
- `app/workers/`: YOLO、OCR、RAG、LLM、提取器等工作模块
- `app/workers/extractor/prompts/`: 提示词和分析模板
- `tests/`: pytest 测试

### 前端 `food-label-frontend/`

- `src/pages/`: 登录、注册、首页、分析中、历史、报告详情、个人资料等页面
- `src/components/`: 通用 UI 和布局组件
- `src/api/`: Axios 客户端和接口调用
- `src/store/`: Zustand 状态管理
- `src/lib/`: 认证与业务辅助函数

## 当前状态

这个仓库不是单纯的脚手架，前后端主链路已经可以联调和做浏览器级验证。但它仍然依赖一组本地基础设施和模型资产，因此：

- 如果只做接口或业务层开发，建议先使用 `SKIP_STARTUP_CHECKS=true`
- 如果改动食材提取、OCR 语义或分析结果表达，优先查看 `提示词/` 与 `app/workers/`
- `images/` 目录里的样例图适合做人工回归和浏览器自动化验证

## 文档索引

- [后端深度说明](docs/backend-codebase-deep-dive.md)
- [前端深度说明](docs/frontend-codebase-deep-dive.md)
- [后端 README](food-label-analyzer/README.md)
- [前端 README](food-label-frontend/README.md)
- [后端 API 文档](food-label-analyzer/API_DOCUMENTATION.md)
- [分析链路说明](food-label-analyzer/ANALYSIS_PIPELINE.md)



