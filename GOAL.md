# GOAL.md

# 当前目标：v1.0.6 发布准备

## 目标

冻结并整理 Phase 3-B1 与 B2，形成可发布的 v1.0.6 提交。

## 任务

- 应用版本从 1.0.5 更新为 1.0.6
- 将 CHANGELOG 的 Unreleased 冻结为 `[1.0.6] - 2026-07-13`
- 在 CHANGELOG 顶部新建空 Unreleased
- 明确 v1.0.6 包含 B1 重复媒体定位和 B2 重复媒体组视图
- 同步 README、PLAN、TASKS、REVIEW、GOAL
- 运行完整测试、pip check 和 Docker 验收

## 边界

- 不新增或修改业务功能
- 不修改 Schema 2、迁移、依赖或 Docker 安全配置
- 不修改旧 tag 或旧 Release
- 本轮只提交并推送发布准备
- 暂不创建 v1.0.6 tag 或 GitHub Release
- 不部署到 N100

## 完成标准

- 应用与文档版本一致为 1.0.6
- B1/B2 发布范围和只读安全边界记录完整
- pytest、pip check、Docker 和 Actions 通过
- 工作区干净并推送至 main
- 未创建 v1.0.6 tag 或 Release

## 本地验收结果

- [x] 应用版本和发布回归断言更新为 1.0.6
- [x] CHANGELOG 新建空 Unreleased，并将 B1 / B2 冻结为 `[1.0.6] - 2026-07-13`
- [x] README / PLAN / TASKS / REVIEW / GOAL 已同步发布候选状态
- [x] 发布范围仅包含 Phase 3-B1 与 B2，保留只读、无媒体操作、无引用迁移边界
- [x] 全量测试 `441 passed in 65.72s`，`pip check` 通过
- [x] 隔离 Docker 双生命周期均 healthy、`/login` 200、版本 1.0.6、Schema 2
- [x] 容器重建前后 SQLite 校验和不变，临时资源已清理
- [x] 除版本元数据与对应断言外未修改功能代码；未改 Schema 2、迁移、依赖或 Docker/CI
- [x] 旧 tag / Release 未移动，本地与远端均无 v1.0.6 tag
- [ ] 发布准备提交推送、Actions 和最终工作区 / GitHub Release 不存在性验收
