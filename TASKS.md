# Codex 开发任务清单 — MVP

按顺序执行，每完成一项打个 [x]。

## 前置准备

- WSL Ubuntu 22.04
- `python3.12 -m venv .venv && source .venv/bin/activate`
- `pip install fastapi uvicorn sqlalchemy jinja2 httpx python-multipart pytest`
- VS Code + Codex 插件

## Day 1: 骨架 + 数据库 + 基础 API

- [ ] **T1.1** 初始化 FastAPI 项目结构
  - `app/main.py`：FastAPI 入口
  - `app/config.py`：读取环境变量（DATABASE_URL、APP_PASSWORD、SECRET_KEY）
  - `app/database.py`：SQLite + SQLAlchemy 初始化
- [ ] **T1.2** 设计 SQLAlchemy 模型
  - `app/models.py`：6 张表 → items、creators、tags、item_tags、item_creators、user_item_states
  - 含外键、级联删除、唯一约束
- [ ] **T1.3** 实现 items CRUD API
  - `routers/items.py`：GET/POST/PUT/DELETE
  - 分页列表，按创建时间倒序
  - extra 字段存 JSON

## Day 2: 标签 + 创作者

- [ ] **T2.1** 标签管理 API
  - `routers/tags.py`：GET/POST/PUT/DELETE
- [ ] **T2.2** 创作者管理 API
  - `routers/creators.py`：GET/POST/GET{id}/DELETE

## Day 3: 登录 + 状态 + 搜索 + 统计

- [ ] **T3.1** 单用户登录保护
  - `app/auth.py`：密码从 `APP_PASSWORD` 环境变量读取，禁止默认空密码
  - `routers/auth.py`：POST /api/auth/login、POST /api/auth/logout
  - Session cookie 认证（`starlette.middleware.sessions`）
  - 所有页面和 API 默认需登录
  - 日志不得输出密码、cookie、token
  - `.env.example` 提供模板，`.env` 在 gitignore
- [ ] **T3.2** 状态标记 API
  - `POST /api/items/{id}/state`：设置 status/rating/review
  - `GET /api/items/{id}/state`：查状态
  - `DELETE /api/items/{id}/state`：取消
- [ ] **T3.3** 搜索 API
  - `routers/search.py`：标题模糊搜索 + 标签过滤 + 状态过滤 + 分页
- [ ] **T3.4** 统计 API
  - `routers/stats.py`：总数/各状态统计/时间线

## Day 4: 前端页面

- [ ] **T4.1** 基础模板 + 登录页
  - `templates/base.html`：导航栏 + 通用布局
  - `templates/login.html`：密码登录表单
- [ ] **T4.2** 首页
  - 最近添加 + 快捷操作入口
- [ ] **T4.3** 条目列表 + 详情页
  - 列表：卡片布局（封面、标题、标签、状态标记）
  - 详情：信息 + 标记按钮 + 标签 + 创作者
  - 新增/编辑表单
- [ ] **T4.4** 标签管理页 + 创作者管理页
- [ ] **T4.5** 统计页面

## Day 5: 导入 + 部署 + 测试

- [ ] **T5.1** CSV/JSON 导入
  - `services/importer.py`：解析 CSV，自动创建不存在的标签和创作者
  - `templates/import.html`：上传 + 预览 + 确认
- [ ] **T5.2** Dockerfile + docker-compose.yml
  - 多阶段构建
  - `data/` 目录持久化
  - `.env` 映射
- [ ] **T5.3** 基础测试
  - `tests/test_database.py`：建表 + 模型
  - `tests/test_items.py`：CRUD
  - `tests/test_states.py`：标记
  - `tests/test_search.py`：搜索
- [ ] **T5.4** 整体验收 + 修复
