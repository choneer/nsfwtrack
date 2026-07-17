# 当前状态：Phase 4-R3 — v1.1.0 发布候选准备完成

## 阶段结果

Phase 4-R3 已将通过完整 R2 验收的 Unreleased 代码准备为 `v1.1.0`
发布候选。本阶段只更新应用版本元数据、现有版本断言和授权状态文档，
未修改业务功能、Schema、迁移、依赖、备份格式、Docker 或 CI。

## 发布候选状态

- 开始基线：`d9d3c45b9980efbe8ae129e3eb978b803e159849`
- 应用内部版本：`1.1.0`
- Schema：`3`
- 正式稳定版与最新 Release：`v1.0.6`
- CHANGELOG：继续使用 `Unreleased`
- `v1.1.0` tag / Release：未创建
- N100：未部署

历史 `v1.0.6` tag、Release、peeled commit、已发布阶段记录、稳定版
Schema 2 → 3 升级来源以及回滚和备份说明均保持原意。

## 本地验证

- 版本 targeted：`1 passed`
- 全量 pytest：`785 passed in 292.33s`
- `pip check`：通过
- 隔离 Docker：镜像构建、healthy、`/login` HTTP 200、容器内应用版本
  `1.1.0`、Schema `3`、UID/GID `10001:10001`、readonly root、
  `CapEff=0`、no-new-privileges 和受限写路径全部通过
- 清理：临时容器、网络、volume、镜像 tag、数据、Compose 文件和随机
  凭据均已清理
- 既有 `data/`：未接触

## 提交与后续

本阶段只创建并推送一笔：

    Prepare v1.1.0 release candidate

该提交必须通过对应 Actions 的 `test` 与 `Docker production smoke`；
run ID 和结果由推送后的最终报告记录，不为外部结果创建第二笔提交。

Actions 成功后停止，等待云端复核和 Hermes 独立验收。正式发布仍需
用户单独授权；在此之前不得创建 tag、Release 或部署 N100。
