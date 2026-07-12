# GOAL.md

# 当前目标：发布 v1.0.3

请先读取 `RULE.md`、`PLAN.md`、`TASKS.md` 和 `CHANGELOG.md`。

## 目标

正式发布 Phase 2-L7 Docker 运行时安全增强及配套部署文档修复。

## 任务

- 将应用版本更新为 `1.0.3`
- 将 `Unreleased` 整理为 `[1.0.3] - 2026-07-12`
- 保留新的空白 `Unreleased`
- 发布说明明确 rootful Docker 的数据目录权限准备要求
- 同步 README、PLAN、TASKS、REVIEW 和 GOAL
- 运行全量测试、`pip check` 和隔离 Docker 安全验收
- 创建发布提交、annotated tag `v1.0.3` 和正式 GitHub Release

## 边界

- 不修改业务逻辑、依赖、数据库、Schema 或迁移
- 不切换容器用户
- 不修改旧 tag 和 Release
- 所有操作在 WSL `/home/nsfwtrack` 执行
- 不部署到 N100

## 完成标准

- 358 项测试、`pip check`、Docker 安全与持久化验收通过
- Actions 的 test 与 Docker smoke 通过
- `main`、tag peeled commit 和 Release target 指向同一发布提交
- 工作区干净
- `v1.0.3` 正式发布

## 执行结果

- [x] Phase 2-L7 已整理为 `1.0.3`，并保留新的空白 `Unreleased`
- [x] 应用版本、回归断言与发布文档已同步更新
- [x] 358 项测试、`pip check`、隔离 Docker 安全配置与 SQLite 持久化验收通过
- [x] 发布提交、annotated `v1.0.3` tag 和正式 GitHub Release 已创建并推送
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移、容器用户或旧 tag / Release
- [x] 未部署到 N100，临时资源已清理，工作区干净
