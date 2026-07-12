# GOAL.md

# 当前目标：发布 v1.0.4

请先读取 `RULE.md`、`PLAN.md`、`TASKS.md`、`CHANGELOG.md` 和 `README.md`。

## 目标

正式发布 Phase 2-L8 固定非 root 容器用户及数据目录权限迁移流程。

## 任务

- 将应用版本更新为 `1.0.4`
- 将 `Unreleased` 整理为 `[1.0.4] - 2026-07-12`
- 保留新的空白 `Unreleased`
- Release notes 明确固定 UID/GID `10001:10001`
- Release notes 明确从 v1.0.3 及更早版本升级前的数据目录权限迁移
- 同步 README、PLAN、TASKS、REVIEW 和 GOAL
- 运行全量测试、`pip check` 和隔离 Docker 安全及持久化验收
- 创建发布提交、annotated tag `v1.0.4` 和正式 GitHub Release

## 边界

- 不修改业务逻辑、依赖、数据库、Schema 或迁移
- 不修改容器 UID/GID 和现有安全配置
- 不使用 root 入口、自动 chown、sudo/gosu 或 chmod 777
- 不修改旧 tag 和 Release
- 所有操作在 WSL `/home/nsfwtrack` 执行
- 不部署到 N100

## 完成标准

- 358 项测试与 `pip check` 通过
- Docker 以 `10001:10001` 运行并保持 healthy
- L7/L8 安全边界、SQLite 持久化和 Schema 1 验收通过
- main 与 tag Actions 均通过
- `main`、tag peeled commit 和 Release target 指向同一发布提交
- 工作区干净
- `v1.0.4` 正式发布

## 执行结果

- [x] Phase 2-L8 已整理为 `1.0.4`，并保留新的空白 `Unreleased`
- [x] 应用版本、相关断言和发布文档已同步更新
- [x] 358 项测试、`pip check` 与隔离 Docker 身份、安全、HTTP 和 SQLite 重建持久化验收通过
- [x] README 与 Release notes 明确 v1.0.3 及更早版本的停机、可验证备份和 `10001:10001` / 0700 迁移
- [x] 发布提交、annotated `v1.0.4` tag 和正式 GitHub Release 已创建并推送
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交，两次 Actions 均通过
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移、容器 UID/GID、安全配置或旧 tag / Release
- [x] 未部署到 N100，临时资源已清理，工作区干净
