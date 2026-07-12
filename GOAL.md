# GOAL.md

# 当前目标：Phase 2-L8 — 非 root 容器用户

请先读取 `RULE.md`、`PLAN.md`、`TASKS.md` 和 `README.md`。

## 目标

让生产镜像中的应用进程使用固定的非 root 用户运行，同时保持 L7 的运行时安全边界和数据持久化正常。

## 任务

- 在镜像中创建固定 UID/GID `10001:10001` 的 `nsfwtrack` 用户
- 使用 Dockerfile `USER` 运行应用和健康检查
- CI 隔离数据目录改为归 `10001:10001` 所有
- 验证容器实际 UID/GID、零 capability 和禁止提权状态
- 保持 `/app/data` 与 `/tmp` 可写，其他镜像路径只读
- 验证 SQLite 创建、重启持久化和 Schema 1
- 更新 README 中首次安装及 v1.0.3 升级后的数据目录权限步骤
- 同步 PLAN、TASKS、CHANGELOG 和 REVIEW

## 边界

- 不使用 root 启动脚本、sudo、gosu 或启动时自动 chown
- 不使用 `chmod 777` 或放宽数据目录权限
- 不修改业务代码、依赖、数据库、Schema、迁移或版本
- 不修改旧 tag 和 Release
- 所有测试在 WSL `/home/nsfwtrack` 执行
- 不部署到 N100

## 完成标准

- 容器 `Config.User` 为 `10001:10001`
- 容器内 `id -u` 和 `id -g` 均为 `10001`
- 容器保持 healthy，`/login` 与安全头正常
- `CapEff=0`、`NoNewPrivs=1`
- `/app/data` 和 `/tmp` 可写，其他镜像路径不可写
- SQLite 重启后持久化，Schema 保持 1
- pytest、pip check、Docker smoke 和 Actions 通过
- 提交并推送，不创建 Release

## 执行结果

- [x] 镜像创建固定 `nsfwtrack` UID/GID `10001:10001`，应用与健康检查由 Dockerfile `USER` 以该身份运行
- [x] CI 数据目录所有权和身份、安全边界、可写路径、HTTP / 安全头检查已同步
- [x] 358 项测试、`pip check` 与隔离 Docker 验收通过
- [x] SQLite 在停止并重建容器后保持同一持久化文件，Schema 仍为 1
- [x] README 已记录首次安装与 v1.0.3 存量数据的停机、可验证备份及 `10001:10001` / 0700 迁移
- [x] 未使用 777、root 启动脚本、sudo/gosu 容器入口或启动时自动 `chown`
- [x] 未修改业务代码、依赖、数据库、Schema、迁移、版本或旧 tag / Release，未部署到 N100
- [x] 发布提交已推送，Actions 的 test 与 Docker production smoke 通过
