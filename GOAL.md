# GOAL.md

# 当前目标：Phase 2-L7 — Docker 运行时安全基线

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

限制容器运行时权限，同时保持 SQLite、媒体、上传和健康检查正常。

## 任务

- 将容器根文件系统设为只读
- 移除全部 Linux capabilities
- 启用 `no-new-privileges`
- 为 `/tmp` 提供临时可写空间
- 保持 `/app/data` 正常持久化
- 让 CI Docker smoke 使用相同安全配置

## 边界

- 本轮不切换容器用户
- 不修改业务代码、依赖、数据库、Schema、迁移或版本
- 所有测试在 WSL `/home/nsfwtrack` 执行
- 不部署到 N100

## 完成标准

- 容器保持 `healthy`
- `/app/data` 和 `/tmp` 可写
- 其他容器路径不可写
- pytest、pip check、Docker smoke 和 Actions 通过
- 更新 PLAN、TASKS、CHANGELOG 和简短 README
- 提交并推送
