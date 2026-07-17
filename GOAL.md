# 已完成目标：Phase 4-R1D — 发布候选文档修正

## 阶段状态

Phase 4-R1 静态审计和 Phase 4-R1D 文档修正均已完成，为尚未开始的
Phase 4-R2 发布候选验收建立干净基线。推荐下一版本为 `v1.1.0`，但尚未
正式确定或发布。

本阶段只修改了文档，未执行 R2，未修改代码、测试、配置、依赖、工作流、
应用版本 `1.0.6`、Schema `3` 或迁移实现。

## 授权范围

只允许修改：

- `GOAL.md`
- `README.md`
- `PLAN.md`
- `TASKS.md`
- `REVIEW.md`
- `CHANGELOG.md`

`RULE.md`、`PERFORMANCE.md`、`COMPLETION_AUDIT.md` 和
`PHASE3_COMPLETION_AUDIT.md` 必须保持不变。不得接触既有 `data/`，不得
创建 tag、Release，不得部署 N100，不得继续开发新功能。

## 文档职责

- README：面向用户记录真实的 Schema 1 → 2 → 3 升级、备份、回滚和应用降级限制
- PLAN：记录 R1 已完成、R1D 当前阶段、R2 下一步及 `v1.1.0` 建议
- TASKS：记录 R1/R1D/R2 状态和 R2 验收类别
- REVIEW：形成 R2 发布候选门禁
- CHANGELOG：只在 Unreleased 简记本阶段文档修正，无运行行为变化
- GOAL：只保留本阶段授权、职责、验证和完成标准

## 已核实的迁移边界

仓库没有独立迁移 CLI。正式支持的流程是登录后使用：

- `GET /schema-upgrade` 查看状态
- `POST /schema-upgrade/preview` 执行只读 dry-run
- `POST /schema-upgrade/apply` 显式应用迁移

apply 要求服务端确认和升级前备份确认；strict 模式还要求精确输入
`CONFIRM`。启动、GET 和 dry-run 不执行迁移。Schema 1 按 1 → 2 → 3
连续升级；Schema 2 执行 2 → 3。失败时整条迁移事务回滚，不支持自动降级。

## 验证与提交

完成后执行 `git diff --check`、确认只修改六份授权文档，只暂存这些文档，
创建一笔 `Document Phase 4-R1 release candidate audit` 提交并推送 `main`。
等待该提交的 Actions `test` 与 `Docker production smoke` 均成功。

## 完成标准

- README 的 Schema 2 → 3 步骤真实、可执行且包含回滚/降级限制
- PLAN、TASKS、REVIEW、CHANGELOG 状态与各自职责一致
- Phase 4-R2 仍未开始，版本和 Schema 未改变
- 未修改授权范围外文件
- Actions 两个 job 成功
- 最终工作区只剩既有 `?? data/`

完成后停止，等待用户授权 Phase 4-R2。
