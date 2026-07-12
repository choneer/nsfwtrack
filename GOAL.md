# GOAL.md

# 当前目标：Phase 2-L4 — CI Docker 冒烟验收

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

让 GitHub Actions 自动验证生产 Docker 镜像可以构建、启动并正常响应。

## 任务

- [x] 在 CI 中增加独立 Docker 验收任务
- [x] 使用临时测试凭据和隔离数据目录启动容器
- [x] 等待 `/login` 返回 200，并检查基础安全响应头
- [x] 失败时输出容器日志，结束后始终清理资源
- [x] 保留现有 pytest 与 `pip check`

## 边界

- 不修改业务逻辑、数据库、Schema、依赖或版本
- 不提交 `.env` 或真实凭据
- 不使用 `.env.example` 的占位值
- 不创建 Release

## 完成标准

- CI 的测试任务和 Docker 任务均通过
- 本地全量测试与隔离 Docker 验收通过
- 更新文档和 `CHANGELOG.md`
- 提交并推送

## 执行结果

- [x] 新增独立 `docker-smoke` job，与 pytest job 并行
- [x] 临时随机凭据 + 隔离数据目录 + 独立 compose project
- [x] 等待 `/login` 200，并校验 nosniff / Referrer-Policy / X-Frame-Options / Permissions-Policy / X-Request-ID
- [x] `if: failure()` 输出 compose logs；`if: always()` 执行 down 与临时目录清理
- [x] 保留原有 test job 的 pip check + pytest
- [x] 本地全量测试通过；本地按 CI 设计的 Docker 冒烟通过并清理
- [x] 未改业务代码、依赖、数据库、Schema 或版本
