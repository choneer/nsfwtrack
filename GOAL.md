# GOAL.md

# 当前目标：Phase 2-L5 — CI 最小权限与重复运行控制

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

收紧 GitHub Actions 权限，并取消同一分支上的过时 CI 运行。

## 任务

- 为 CI 明确设置最小只读权限
- 增加 workflow concurrency 和 `cancel-in-progress`
- 保持 pytest 与 Docker smoke 行为不变
- 修正 PLAN、TASKS 中过时的开发者角色和测试数量
- 在 CHANGELOG 的 Unreleased 记录 L4 收口及 L5 变更

## 边界

- 不修改业务代码、依赖、数据库、Schema 或版本
- 不使用额外密钥或写权限
- 不创建 Release

## 完成标准

- test 与 docker-smoke 均通过
- 过时的同分支运行可以自动取消
- 工作流权限为只读最小范围
- 文档状态一致并提交推送