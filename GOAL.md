# GOAL.md

# 当前目标：发布 v1.0.1

请先读取 `RULE.md`、`PLAN.md`、`TASKS.md` 和 `CHANGELOG.md`。

## 目标

正式发布包含 K1、K2 收口修改的 `v1.0.1`。

## 任务

- 将应用版本更新为 `1.0.1`
- 整理 `CHANGELOG.md` 的 `v1.0.1` 内容
- 同步更新 `README.md`、`PLAN.md`、`TASKS.md` 和 `REVIEW.md`
- 运行全量测试和隔离 Docker 验收
- 创建发布提交
- 创建 annotated tag `v1.0.1`
- 创建正式 GitHub Release

## 边界

- 不修改业务逻辑
- 不修改依赖、数据库结构、Schema 或迁移
- 不修改旧 tag 和 Release
- 不接触默认 schema 2 数据卷

## 完成标准

- 测试与 Docker 验收通过
- `main`、tag 和 Release 指向同一发布提交
- 工作区干净
- `v1.0.1` 正式发布

## 执行结果

- [x] K1 / K2 已整理为 `v1.0.1` 发布内容
- [x] 应用版本和发布文档已更新为 `1.0.1`
- [x] 全量测试 `347 passed`
- [x] 隔离 Docker build / up / `/login` 200 / 应用版本 / Schema 1 / down 通过并清理
- [x] 发布提交、annotated tag 和正式 GitHub Release 已创建并推送
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未修改业务逻辑、依赖、数据库结构、Schema、迁移或旧 tag / Release
- [x] 未接触默认 schema 2 数据卷，工作区干净
