# GOAL.md

# 当前目标：Phase 2-L6 — Docker 健康状态与就绪验收

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

为生产镜像增加 Docker 健康检查，并让 CI 使用同一健康状态判断容器是否就绪。

## 任务

- 在生产镜像中增加 `HEALTHCHECK`
- 只使用 Python 标准库，不安装 curl 或新依赖
- CI 等待容器变为 `healthy` 后，再执行现有 `/login` 和安全头检查
- 保持失败日志和 `always()` 清理逻辑
- 同步更新 PLAN、TASKS、CHANGELOG 和简短 README 说明

## 边界

- 不新增业务接口
- 不修改业务代码、数据库、Schema、依赖或版本
- 不部署到 N100
- 所有测试在 WSL `/home/nsfwtrack` 执行

## 完成标准

- `docker compose ps` 显示容器为 `healthy`
- CI test 与 docker-smoke 均通过
- 全量测试、`pip check` 和隔离 Docker 验收通过
- 提交并推送
