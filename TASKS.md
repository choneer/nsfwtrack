# Codex 开发任务清单 — MVP

按顺序执行，每完成一项打个 [x]。

## 前置准备

- WSL Ubuntu 22.04
- `python3.12 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements-dev.txt`
- VS Code + Codex 插件

## Day 1: 骨架 + 数据库 + 基础 API

- [x] **T1.1** 初始化 FastAPI 项目结构
  - `app/main.py`：FastAPI 入口
  - `app/config.py`：读取环境变量（DATABASE_URL、APP_PASSWORD、SECRET_KEY）
  - `app/database.py`：SQLite + SQLAlchemy 初始化
- [x] **T1.2** 设计 SQLAlchemy 模型
  - `app/models.py`：6 张表 → items、creators、tags、item_tags、item_creators、user_item_states
  - 含外键、级联删除、唯一约束
- [x] **T1.3** 实现 items CRUD API
  - `routers/items.py`：GET/POST/PUT/DELETE
  - 分页列表，按创建时间倒序
  - extra 字段存 JSON

## Day 2: 标签 + 创作者

- [x] **T2.1** 标签管理 API
  - `routers/tags.py`：GET/POST/PUT/DELETE
- [x] **T2.2** 创作者管理 API
  - `routers/creators.py`：GET/POST/GET{id}/DELETE

## Day 3: 登录 + 状态 + 搜索 + 统计

- [x] **T3.1** 单用户登录保护
  - `app/auth.py`：密码从 `APP_PASSWORD` 环境变量读取，禁止默认空密码
  - `routers/auth.py`：POST /api/auth/login、POST /api/auth/logout
  - Session cookie 认证（`starlette.middleware.sessions`）
  - 所有页面和 API 默认需登录
  - 日志不得输出密码、cookie、token
  - `.env.example` 提供模板，`.env` 在 gitignore
- [x] **T3.2** 状态标记 API
  - `POST /api/items/{id}/state`：设置 status/rating/review
  - `GET /api/items/{id}/state`：查状态
  - `DELETE /api/items/{id}/state`：取消
- [x] **T3.3** 搜索 API
  - `routers/search.py`：标题模糊搜索 + 标签过滤 + 状态过滤 + 分页
- [x] **T3.4** 统计 API
  - `routers/stats.py`：总数/各状态统计/时间线

## Day 4: 前端页面

- [x] **T4.1** 基础模板 + 登录页
  - `templates/base.html`：导航栏 + 通用布局
  - `templates/login.html`：密码登录表单
- [x] **T4.2** 首页
  - 最近添加 + 快捷操作入口
- [x] **T4.3** 条目列表 + 详情页
  - 列表：卡片布局（封面、标题、标签、状态标记）
  - 详情：信息 + 标记按钮 + 标签 + 创作者
  - 新增/编辑表单
- [x] **T4.4** 标签管理页 + 创作者管理页
- [x] **T4.5** 统计页面
- [x] **T4.6** 中文 / English 语言切换
  - `app/i18n.py`：中英翻译字典，默认中文
  - `/set-language?lang=zh|en`：切换语言
  - Session 保存语言偏好，刷新后不丢失
  - 所有 Jinja2 页面展示文本接入 `t("...")`

## Day 5: 导入 + 部署 + 测试

- [x] **T5.1** CSV/JSON 导入
  - `services/importer.py`：解析 CSV，自动创建不存在的标签和创作者
  - `templates/import.html`：上传 + 预览 + 确认
- [x] **T5.2** Dockerfile + docker-compose.yml
  - 多阶段构建
  - `data/` 目录持久化
  - `.env` 映射
- [x] **T5.3** 基础测试
  - `tests/test_database.py`：建表 + 模型
  - `tests/test_items.py`：CRUD
  - `tests/test_states.py`：标记
  - `tests/test_search.py`：搜索
- [x] **T5.4** 整体验收 + 修复

## 本地备份与恢复

- [x] **B1** 本地 JSON 导出
  - `GET /api/backup/export/json`
  - 导出 items、tags、creators、item_tags、item_creators、user_item_states
- [x] **B2** 本地 CSV 导出
  - `GET /api/backup/export/csv`
  - 导出 items 可读字段、标签、创作者和状态
- [x] **B3** 本地 JSON 备份恢复
  - `POST /api/backup/restore/json`
  - 只接受本项目导出的 JSON 文件，事务性追加 / 合并
- [x] **B4** 备份页面与 i18n
  - `/backup`
  - 导航入口、JSON/CSV 导出按钮、JSON 备份上传入口
- [x] **B5** 备份恢复测试
  - 未登录保护、JSON/CSV 导出、结构校验、合法恢复、非法恢复不破坏数据、中英文页面
- [x] **B6** 备份恢复体验增强
  - `MAX_BACKUP_UPLOAD_MB` 默认 5MB，可配置
  - `POST /api/backup/preview/json`：只预览校验，不写入数据库
  - `/backup` 页面明确合并恢复、非覆盖恢复、本地文件限制
  - 备份错误提示支持中文 / English
  - 覆盖缺文件、非 JSON、超限、非法 JSON、schema 不匹配、缺字段、恢复异常测试

## 本轮清理

- [x] 删除 `data/ehtag_version`
- [x] 删除 `docs/legacy/`
- [x] 确认当前代码不依赖 `docs/legacy/`
- [x] 确认未引入外部 HTTP 请求、爬虫、adapter、远程图片拉取、第三方 cookie/token 管理、自动同步、多源搜索或随机探索接口

## Phase 1 收尾体验修复

- [x] 增加轻量 session flash message，支持 success / error / info 与中英文文案
- [x] 登录、退出、条目、标签、创作者、状态等页面表单操作提供明确反馈
- [x] CSV / JSON 导入预览和确认失败路径提供页面错误提示
- [x] 备份预览 / 恢复成功失败提示复用统一样式，保留本地合并恢复边界
- [x] README 补充本地开发、Docker Compose、N100 局域网部署、`.env`、数据持久化、安全和测试说明
- [x] 确认 TestClient warning 来源，暂不引入不稳定依赖或大范围测试重写
- [x] 补充登录失败、导入失败和备份预览失败页面测试
