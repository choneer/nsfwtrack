# GOAL.md

# 当前目标：Phase 2-J — 发布 v1.0.0

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

完成 NSFWTrack `v1.0.0` 正式发布。

## 任务

- 将应用版本更新为 `1.0.0`
- 将 `CHANGELOG.md` 中已完成内容整理为：

  `## [1.0.0] - 2026-07-11`

- 保留新的空白 `Unreleased`
- 同步更新 `README.md`、`PLAN.md`、`TASKS.md`、`REVIEW.md`
- 运行全量测试和隔离 Docker 验收
- 创建并推送发布提交
- 创建 annotated tag `v1.0.0`
- 创建正式 GitHub Release：`NSFWTrack v1.0.0`

## 边界

- 不修改业务逻辑
- 不修改数据库结构、索引、Schema 版本或迁移
- 不新增依赖
- 不修改旧 tag 或 Release
- 不使用或修改默认 schema 2 数据卷
- 不创建 draft 或 prerelease

## 完成标准

确认：

- 测试与 Docker 验收通过
- `origin/main` 指向发布提交
- `v1.0.0` tag 指向同一提交
- GitHub Release 已发布
- 工作区干净

完成后汇报：

1. 测试结果
2. 发布提交 hash
3. tag 对象及目标提交 hash
4. Release 地址
5. 最终仓库状态

## 发布记录

- 版本：`v1.0.0`
- 发布日期：`2026-07-11`
- CHANGELOG：Phase 2-I1 / I2 / I3 / I4 已归档到 `## [1.0.0] - 2026-07-11`
- 测试：`309 passed`
- Docker：全新隔离数据目录 build / up / `/login` 连续 200 / down 通过
- 应用版本：`1.0.0`
- 数据库边界：`CURRENT_SCHEMA_VERSION = 1`，生产迁移注册表为空
- Release：https://github.com/choneer/nsfwtrack/releases/tag/v1.0.0
- 范围：未修改业务逻辑、数据库结构、索引、Schema 版本、生产迁移或依赖
- 发布：annotated `v1.0.0` tag 与正式 GitHub Release
