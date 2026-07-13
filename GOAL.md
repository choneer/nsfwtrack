# GOAL.md

# 当前目标：v1.0.5 发布准备

## 目标

整理并冻结 Phase 3-A1 至 A6，形成可发布的 v1.0.5 提交。

## 任务

- 应用版本从 1.0.4 更新为 1.0.5
- 将 CHANGELOG 的 Unreleased 整理为 1.0.5（2026-07-13）
- 新建空的 Unreleased 段
- README 更新当前版本、状态和功能摘要
- 同步 PLAN、TASKS、REVIEW、GOAL
- 明确 v1.0.5 包含 A1 至 A6 及 A1/A2 修复
- 运行完整测试、pip check 和 Docker 验收

## 边界

- 不新增功能
- 不修改 Schema 2、迁移、依赖或 Docker 安全配置
- 不修改旧 tag 或旧 Release
- 本轮只提交并推送发布准备
- 暂不创建 tag 和 GitHub Release
- 不部署到 N100

## 完成标准

- 所有版本与文档一致为 1.0.5
- pytest、pip check、Docker 和 Actions 通过
- 工作区干净并推送到 main
- 未创建 tag 或 Release

## 执行结果

- [x] FastAPI 应用版本和对应回归断言统一更新为 1.0.5
- [x] CHANGELOG 将完整 A1-A6 与两项修复冻结为 `[1.0.5] - 2026-07-13`
- [x] CHANGELOG 顶部保留新的空 Unreleased 段
- [x] README / PLAN / TASKS / REVIEW / GOAL 当前版本和发布状态同步
- [x] 明确最新已发布版本仍为 v1.0.4，v1.0.5 tag / GitHub Release 本轮不创建
- [x] 功能代码、Schema 2、迁移、依赖和 Docker 配置保持不变
- [x] 全量 `433 passed`，pip check 无损坏依赖
- [x] 隔离 Docker build、healthy、`/login` 200、版本 1.0.5、Schema 2 和重建验收通过并清理
- [ ] 发布准备提交推送到 main，最终 Actions test / Docker production smoke 通过
- [ ] 工作区与远端同步，未创建或移动 tag / GitHub Release
