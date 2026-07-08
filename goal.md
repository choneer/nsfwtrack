# NSFWTrack Phase 1 Goal

在启动 `/goal` 时，只需写：

`按照 goal.md 执行`

## 目标

完成 `/home/nsfwtrack` 的 Phase 1 全部开发，交付一个可本地运行、可登录、可录入、可搜索、可统计、可导入、可 Docker 部署的单用户 MVP。

## 必读文件

开始前先阅读并严格遵循：

- `PLAN.md`
- `TASKS.md`
- `REVIEW.md`
- `.env.example`
- `.gitignore`
- `requirements.txt`

## Phase 1 范围

必须实现：

- FastAPI 项目骨架
- SQLite + SQLAlchemy 数据库
- items / tags / creators / states / search / stats / import API
- Session 登录保护
- Jinja2 页面
- CSV / JSON 导入
- Dockerfile 和 docker-compose.yml
- 基础测试

严格禁止：

- 外部 HTTP 拉取
- 爬虫
- 站点 adapter
- 远程图片拉取
- cookie / token 管理（登录 session 除外）
- 自动同步
- 多源搜索
- 随机探索接口
- 推荐系统
- AI 助手
- 任何 Phase 2 / Phase 3 功能

## 实施顺序

1. 检查现有仓库状态和文件结构
2. 搭建 `app/`、`tests/`、模板、服务层骨架
3. 实现配置、数据库、模型、schemas
4. 实现认证和基础中间件
5. 实现 CRUD、状态、搜索、统计、导入 API
6. 实现页面模板和基础交互
7. 添加 Dockerfile、docker-compose.yml、启动说明
8. 编写并运行测试
9. 修复问题直到验收通过

## 开发要求

- 严格遵循 `PLAN.md` 的结构和 API 设计
- 不要扩展超出 Phase 1 的能力
- 使用清晰的类型注解
- 避免硬编码路径
- 日志不得泄露密码、cookie、token
- 所有需要登录保护的页面和 API 默认都要登录后访问
- 提交信息使用中英双语风格

## 验收标准

- 所有 Phase 1 核心功能完成
- 本地测试通过
- Docker Compose 可启动
- 登录可用
- API 可用
- 页面可用
- 代码已提交到仓库

## 工作方式

- 先看仓库，再动手
- 每完成一块就自检
- 若出现歧义，优先以 `PLAN.md` 和 `TASKS.md` 为准
- 除非真正阻塞，否则不要中断等待用户决策
- 最终输出要简明总结完成内容、测试结果和残留风险
