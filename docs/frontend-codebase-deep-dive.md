# FoodGuard Frontend Codebase Deep Dive

## 1. 文档定位

本文档用于系统梳理 `food-label-frontend/` 的真实前端实现，目的是让你在不重新逐个翻源码的情况下，也能回答下面这些问题：

- 前端页面有哪些，分别做什么
- 路由怎么组织
- 登录态怎么管理
- 页面如何调用后端接口
- 每个页面的状态、交互、跳转关系是什么
- 页面 UI 是如何围绕后端数据结构设计的
- 当前前端实现有哪些完成度高的地方、哪些地方仍然是后续优化点

阅读范围包括：

- `food-label-frontend/src/` 全部源码
- `package.json`、`vite.config.ts`、`tsconfig*.json`、`eslint.config.js`
- `index.html`
- `food-label-frontend-prototype/` 中的原型 HTML 页面

截至本次梳理时的验证结果：

- 前端构建：`npm run build`
- 结果：构建成功

---

## 2. 前端项目的总体职责

`food-label-frontend` 是用户直接交互的正式 Web 前端，核心职责包括：

1. 用户认证入口
   - 登录
   - 注册
   - 注册验证码发送

2. 用户首次使用引导
   - 填写昵称
   - 选择关注人群
   - 选择健康状况
   - 填写过敏源

3. 图片上传与分析任务跟踪
   - 选择图片
   - 本地预览
   - 调用上传接口
   - 轮询任务状态

4. 报告展示
   - 历史记录列表
   - 报告详情页
   - 按标签页展示配料、营养、人群建议

5. 用户资料与偏好管理
   - 修改昵称
   - 修改偏好
   - 修改密码
   - 退出登录

它不是静态展示页，而是围绕后端 API 运转的业务前端。

---

## 3. 技术栈与工程配置

### 3.1 基础技术栈

前端采用：

- React 19
- TypeScript
- React Router 7
- Zustand
- Axios
- Tailwind CSS 4
- Vite 8
- Lucide React

这套技术栈的特点是：

- 工程结构轻量
- 类型系统完整
- 与后端 REST API 配合自然
- 足够支撑当前产品复杂度

### 3.2 Vite 配置

`vite.config.ts` 主要做了四件事：

- React 插件
- Tailwind 插件
- 路径别名 `@ -> src`
- 开发代理 `/api -> http://localhost:8000`

这样前端开发时无需跨域配置额外域名。

### 3.3 TypeScript 配置

`tsconfig.app.json` 开启了：

- `strict: true`
- `noUnusedLocals`
- `noUnusedParameters`
- `moduleResolution: bundler`
- `jsx: react-jsx`

说明该项目不是随意写 JS，而是比较认真地使用了类型约束。

### 3.4 ESLint 配置

当前启用了：

- `@eslint/js`
- `typescript-eslint`
- `react-hooks`
- `react-refresh`

整体属于“轻量但够用”的 lint 方案。

---

## 4. 目录结构与代码组织方式

正式前端主要结构如下：

```text
food-label-frontend/
├─ public/                     公共静态资源
├─ src/
│  ├─ api/                     Axios 客户端
│  ├─ assets/                  图片资源
│  ├─ components/
│  │  ├─ layout/               布局组件
│  │  └─ ui/                   基础 UI 组件
│  ├─ lib/                     工具函数与业务辅助函数
│  ├─ pages/                   页面组件
│  │  └─ auth/                 登录、注册页
│  ├─ store/                   Zustand 状态仓库
│  ├─ types/                   TS 类型定义
│  ├─ App.tsx                  路由总装配
│  ├─ main.tsx                 React 入口
│  └─ index.css                全局样式与 Tailwind 主题
├─ package.json
├─ vite.config.ts
└─ tsconfig*.json
```

组织方式非常典型：

- `pages/` 放页面
- `components/` 放复用组件
- `store/` 放全局状态
- `lib/` 放业务辅助逻辑
- `types/` 放契约类型

---

## 5. 应用入口与路由结构

### 5.1 React 入口

`src/main.tsx` 的职责很简单：

- 引入 `index.css`
- 将 `<App />` 渲染到 `#root`
- 使用 `StrictMode`

### 5.2 路由总入口 `src/App.tsx`

路由被拆成两套布局：

1. `AuthLayout`
   - `/login`
   - `/register`

2. `AppLayout`
   - `/`
   - `/onboarding`
   - `/analyzing/:taskId`
   - `/history`
   - `/profile`
   - `/reports/:id`

未命中的路由统一跳到 `/`。

### 5.3 这种拆法的意义

好处有两个：

- 认证页和业务页的视觉框架分离
- 鉴权逻辑集中在 layout，而不是散在每个页面

---

## 6. 登录态与会话管理

前端登录态采用了一个比较轻量的组合：

- `axios` 拦截器
- `localStorage`
- `zustand`

### 6.1 Zustand 仓库 `src/store/auth.ts`

核心状态：

- `user`
- `preferences`
- `isAuthenticated`
- `needsOnboarding`

核心动作：

- `setSession`
- `setUser`
- `setPreferences`
- `logout`

### 6.2 本地存储策略

前端将以下数据持久化到 `localStorage`：

- `access_token`
- `refresh_token`
- `foodguard_user`
- `foodguard_preferences`

优点：

- 刷新页面不丢失登录态
- 页面加载时可快速恢复用户上下文

代价：

- 相比 httpOnly cookie，安全性略弱，存在典型 XSS 风险

### 6.3 `src/lib/auth-session.ts`

封装了以下关键逻辑：

- 构造空偏好对象
- 判断是否需要 onboarding
- 持久化 token
- 清理 token
- 并发获取 `/users/me` 和 `/preferences/me`

当前 `needsOnboarding()` 的判定规则是：

- 用户没有 `display_name`
- 或偏好中 `focus_groups` 为空

### 6.4 Axios 客户端 `src/api/client.ts`

#### 请求阶段

- 自动从 `localStorage` 读取 `access_token`
- 自动写入 `Authorization: Bearer ...`

#### 响应阶段

- 所有成功请求默认返回 `response.data`
- 如果遇到 `401`：
  - 读取 `refresh_token`
  - 调用 `/auth/refresh`
  - 刷新成功后重放原请求
  - 刷新失败则清 token 并跳 `/login`

这意味着前端已经实现了标准的 token 自动续期体验。

---

## 7. 布局层设计

### 7.1 `AuthLayout`

功能：

- 已登录用户禁止停留在登录/注册页
- 未登录用户渲染统一认证页面外壳

视觉特征：

- 居中布局
- 渐变光斑背景
- 单列卡片型认证界面

### 7.2 `AppLayout`

功能：

1. 鉴权守卫
   - 未登录跳 `/login`
   - 未完成 onboarding 时强制跳 `/onboarding`
   - 已完成 onboarding 时禁止继续停留 `/onboarding`

2. 首次 hydration
   - 如果只有 token，没有用户信息和偏好
   - 则自动请求 `/users/me` 和 `/preferences/me`
   - 再写入 store

3. 全局导航
   - Logo
   - 首页
   - 历史记录
   - 头像入口到 `/profile`

这是正式业务前端最关键的壳层。

---

## 8. 公共 UI 组件

### 8.1 Button

支持：

- `primary`
- `secondary`
- `outline`
- `ghost`
- `danger`

以及：

- `sm`
- `md`
- `lg`
- `isLoading`

### 8.2 Input

支持：

- 标准输入框
- 通过 `error` 直接渲染字段错误

### 8.3 Card

提供：

- `Card`
- `CardHeader`
- `CardTitle`
- `CardContent`

虽然使用频率不算最高，但为统一容器风格预留了基础抽象。

---

## 9. 工具函数与显示层辅助

### 9.1 `src/lib/foodguard.ts`

这是整个前端很重要的“显示语义中心”，负责：

- 人群标签文案
- 健康状态文案
- 头像首字母
- 分数颜色与徽标
- 环形分数 offset
- 风险等级展示文案
- 配料风险卡片样式
- 时间格式化
- 营养解析来源显示文案
- 营养项等级样式
- 偏好摘要整理

这说明很多 UI 规则不是散落在页面中的。

### 9.2 `src/lib/api-errors.ts`

用于解析后端统一错误结构，输出：

- 主错误消息
- 字段级错误映射

它直接支撑：

- 注册页字段提示
- 修改密码页字段提示

### 9.3 `src/lib/utils.ts`

提供 `cn()`，用于 className 合并。

---

## 10. 页面级详细拆解

### 10.1 登录页 `src/pages/auth/Login.tsx`

#### 主要状态

- `email`
- `password`
- `loading`
- `error`

#### 核心流程

1. 调用 `/auth/login`
2. 保存 access/refresh token
3. 调用 `fetchSessionContext()`
4. 调用 `setSession()`
5. 根据 `needsOnboarding()` 跳转到 `/onboarding` 或 `/`

#### 页面特征

- 错误提示在表单顶部
- 登录失败时主动清空残留会话
- 表单结构简洁，逻辑清晰

### 10.2 注册页 `src/pages/auth/Register.tsx`

#### 主要状态

- `email`
- `code`
- `password`
- `confirmPassword`
- `cooldown`
- `fieldErrors`
- `loading`
- `error`

#### 核心能力

1. 发送验证码
   - 调用 `/auth/register/send-code`
   - 成功后进入冷却倒计时

2. 注册
   - 调用 `/auth/register`
   - 成功后自动再调用 `/auth/login`
   - 登录成功后加载用户上下文并跳转

3. 字段级错误展示
   - 借助 `extractApiErrorDetails()` 把后端错误映射到对应输入框

这是完整的业务注册页，而不是单纯表单展示页。

### 10.3 首页上传页 `src/pages/Home.tsx`

这是前端业务价值最高的页面之一。

#### 主要状态

- `dragActive`
- `file`
- `previewUrl`
- `loading`
- `error`
- `pickerHintVisible`

#### 页面模式

1. 未选文件模式
   - Hero 文案
   - 拖拽上传区
   - 点击打开系统文件选择器

2. 已选文件模式
   - 图片预览
   - 文件名和大小
   - 用户默认偏好摘要
   - 开始分析按钮

#### 上传流程

1. 本地选图
2. 生成本地 `blob:` 预览 URL
3. 点击“开始智能分析”时才真正请求 `/analysis/upload`
4. 把预览 URL 暂存到 `sessionStorage.latest_upload_preview`
5. 上传成功后跳到 `/analyzing/:taskId`

这个设计非常合理，因为分析页可以继续展示刚才的本地图像，而不用等后端返回图片地址。

### 10.4 分析中页面 `src/pages/Analyzing.tsx`

#### 作用

- 轮询任务状态
- 展示阶段性进度
- 成功后跳转报告详情
- 失败后给出返回入口

#### 核心逻辑

- 调用 `/analysis/tasks/{taskId}`
- 若 `completed && report_id`，跳 `/reports/{report_id}`
- 若 `failed`，显示错误
- 否则继续 `setTimeout` 轮询

#### 进度条逻辑

注意：当前前端没有后端精确百分比。  
它是根据：

- `status`
- `progress_message` 是否包含 `LLM`

来估算 12%、42%、82%、100%。

因此分析进度属于“启发式 UI”，而不是真实后端进度同步。

### 10.5 历史记录页 `src/pages/History.tsx`

#### 功能

- 调 `/reports?page=x&page_size=10`
- 展示报告表格
- 删除报告
- 分页切换
- 当前页前端搜索

#### 展示字段

- 缩略图
- 报告 ID 片段
- 健康评分
- 摘要
- 创建时间

#### 需要说明的细节

- 搜索只过滤当前页数据，不是全量搜索
- 删除成功后立即本地同步列表和总数

### 10.6 首次引导页 `src/pages/Onboarding.tsx`

#### 作用

用于第一次登录后补充个性化分析所需信息。

#### 收集内容

- 昵称
- 关注人群
- 健康状况
- 过敏源

#### 提交流程

并发调用：

- `PATCH /users/me`
- `PUT /preferences/me`

成功后用返回结果更新 store，再跳首页。

#### 页面特点

- 步骤式布局
- 卡片式多选
- 过敏选项会动态展开详细输入区

### 10.7 个人资料页 `src/pages/Profile.tsx`

这是最复杂的页面之一。

#### 页面职责

1. 资料与偏好管理
2. 修改密码
3. 退出登录
4. 展示分析统计信息

#### 首次进入时会并发请求

- `/users/me`
- `/preferences/me`
- `/reports?page=1&page_size=1`

最后一个接口只是为了拿报告总数。

#### 修改密码流程

- 调用 `/users/change-password`
- 用 `extractApiErrorDetails()` 映射字段错误

#### 一个重要现状

页面明确把“注销账号”按钮做成禁用态，说明：

- 后端虽有 `DELETE /users/me`
- 但前端产品层面暂未开放此危险操作

### 10.8 报告详情页 `src/pages/ReportDetail.tsx`

这是用户最关注、也是答辩最适合展示的页面。

#### 数据来源

调用 `/reports/{id}`，后端返回：

- 图片 URL
- OCR 配料文本
- 简易 nutrition
- 结构化 `nutrition_table`
- `analysis`
- `rag_summary`

#### 页面结构

1. 顶部 Hero
   - 原图
   - 环形分数
   - 四个指标卡
   - 风险徽标

2. 核心洞察
   - 主风险
   - 总结文案
   - 行动建议

3. 三个标签页
   - 配料分析
   - 营养成分
   - 人群建议

#### 配料分析页签

展示：

- 风险分布
- OCR 原始配料文本
- 结构化配料风险卡片

#### 营养成分页签

展示：

- 结构化营养表行
- amount / NRV / recommendation
- 营养解析来源
- 整体营养建议摘要

#### 人群建议页签

展示：

- 五个人群建议
- 营养亮点

这说明后端的 `nutrition_table` 与 `analysis.health_advice` 设计就是为这个页面服务的。

---

## 11. 页面之间的跳转关系

### 11.1 认证链路

- 未登录访问业务页 -> 跳 `/login`
- 登录成功 -> `/onboarding` 或 `/`
- 已登录访问 `/login` / `/register` -> 自动跳业务页

### 11.2 分析链路

- 首页选图 -> 分析中页
- 分析中页完成 -> 报告详情页
- 报告详情页可回历史记录页

### 11.3 用户管理链路

- 顶部头像 -> `/profile`
- 历史记录页 -> 报告详情页

---

## 12. 前后端数据契约如何对应

### 12.1 通用响应

前端统一按：

```ts
interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
```

消费后端。

### 12.2 用户与偏好

`types/auth.ts` 中的：

- `User`
- `UserPreferences`
- `TokenResponse`

直接映射后端 schema。

### 12.3 任务状态

分析中页使用：

- `queued`
- `processing`
- `completed`
- `failed`

对应后端对外任务状态，而不是数据库内部 `pending`。

### 12.4 报告详情

报告详情页在组件内部自定义了 `ReportDetailData`，与后端 `ReportDetailResponseSchema` 高度对应。

---

## 13. 样式系统与视觉语言

### 13.1 主题定义

`src/index.css` 定义了：

- 主色：绿色系
- 背景：浅灰白
- 文字：深色 slate
- 字体：Inter + 中文字体回退

### 13.2 全局视觉工具类

全局样式中抽出了若干业务专用类：

- `glass-panel`
- `soft-panel`
- `file-drop-zone`
- `scanner-line`
- `report-score-ring`
- `tab-active`
- `bg-pattern`
- `animate-blob`
- `animate-scan`

### 13.3 视觉风格总结

当前前端的风格特点很统一：

- 绿色健康科技感
- 明亮背景
- 大圆角
- 柔和阴影
- 卡片式结构
- 轻动效

这很适合毕业设计展示。

---

## 14. `food-label-frontend-prototype` 的定位

仓库里还有一个 `food-label-frontend-prototype/` 目录。

它不是正式 React 项目，而是一组静态 HTML 原型，用于：

- 前期界面草图
- 视觉参考
- 页面结构试验

当前正式前端明显继承了原型中的若干设计方向，例如：

- 首页布局
- 上传预览页思路
- 报告详情页的评分 Hero 和标签页结构

因此在论文和答辩中可以这样表述：

- `food-label-frontend-prototype` 是原型验证产物
- `food-label-frontend` 是最终正式实现

---

## 15. 当前实现中的优点

### 15.1 用户流程完整

从注册、登录、引导、上传、轮询到报告查看，主链路已经形成完整闭环。

### 15.2 与后端契约贴合度高

字段级错误、任务状态、报告详情结构都与后端设计高度一致。

### 15.3 状态管理克制

只把真正跨页面共享的数据放到 Zustand：

- 用户
- 偏好
- 登录态

### 15.4 展示效果较成熟

重点页面如首页、分析中页、报告详情页、引导页都有比较明确的视觉设计，已经能支撑正式演示。

---

## 16. 当前实现中的局限与改进点

### 16.1 没有前端自动化测试

目前没有 Vitest、RTL 或 Playwright，用例验证主要依赖构建通过和人工体验。

### 16.2 `App.css` 仍保留模板遗留内容

`src/App.css` 基本还是 Vite 初始模板风格，对正式页面贡献不大，可后续清理。

### 16.3 部分页面内接口类型没有抽到 `types/`

例如报告详情页直接在页面内部定义接口，后续如果字段增长，维护成本会增加。

### 16.4 历史记录搜索不是全量搜索

只对当前页结果做过滤，不是后端搜索。

### 16.5 分析进度不是精确进度

它是基于任务状态和文案做的阶段性猜测。

### 16.6 token 使用 localStorage

使用方便，但安全性不如 httpOnly cookie。

### 16.7 页面标题仍未产品化

`index.html` 的标题还是 `food-label-frontend`，演示时最好改成正式产品名。

---

## 17. 论文/答辩中如何讲前端

建议从三个层次讲：

### 17.1 用户旅程

- 注册并验证邮箱
- 完成个性化引导
- 上传食品标签图片
- 等待 AI 分析
- 查看健康报告
- 管理个人资料和默认偏好

### 17.2 前端架构

- 认证区和业务区分布局
- Zustand 只管全局用户态
- Axios 拦截器管 token 刷新
- 页面各自负责本地状态和请求时机

### 17.3 前后端协作

- 注册页消费字段级错误
- 分析页轮询任务状态
- 报告页消费结构化 `nutrition_table`、`analysis`、`rag_summary`

这样可以体现整个系统不是“页面拼接”，而是契约驱动的前后端协同。

---

## 18. 一句话总结

当前 `food-label-frontend` 已经完成从认证、引导、上传分析到报告展示的完整用户链路，工程上采用“React Router + Zustand + Axios + Tailwind”的轻量组合，重点页面围绕后端结构化数据做了较深的 UI 适配，是一个可以直接支撑项目演示和毕业答辩的正式业务前端，而 `food-label-frontend-prototype` 则更多承担原型参考角色。
