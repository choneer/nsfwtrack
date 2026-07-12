# GOAL.md

# 当前目标：发布 v1.0.2

请先读取 `RULE.md`、`PLAN.md`、`TASKS.md` 和 `CHANGELOG.md`。

## 目标

正式发布 Phase 2-L1 至 L6 的维护与稳定性改进。

## 任务

- 将应用版本更新为 `1.0.2`
- 将 `Unreleased` 整理为 `[1.0.2] - 2026-07-12`
- 保留新的空白 `Unreleased`
- 同步 README、PLAN、TASKS、REVIEW 和 GOAL
- 运行全量测试、`pip check` 和隔离 Docker 验收
- 创建发布提交、annotated tag `v1.0.2` 和正式 GitHub Release

## 边界

- 不修改业务逻辑、依赖、数据库、Schema 或迁移
- 不修改旧 tag 和 Release
- 所有操作在 WSL `/home/nsfwtrack` 执行
- 不部署到 N100

## 完成标准

- 测试、Docker 和 Actions 通过
- `main`、tag 和 Release 指向同一发布提交
- 工作区干净
- `v1.0.2` 正式发布

## 执行结果

- [x] L1 至 L6 已整理为 `v1.0.2` 发布内容，新的 `Unreleased` 保持空白
- [x] 应用版本与 README / PLAN / TASKS / REVIEW / GOAL 已同步为 `1.0.2`
- [x] 全量测试 `358 passed`，`pip check` 与隔离 Docker healthy / `/login` / 版本验收通过
- [x] 发布提交、annotated tag 和正式 GitHub Release 已创建并推送
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移或旧 tag / Release
- [x] 未部署到 N100，临时资源已清理，工作区干净
