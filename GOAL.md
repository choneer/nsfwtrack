# GOAL.md

# 当前目标：Phase 3-C5 — 媒体根目录诊断与安全初始化

## 目标

为 `media_root_unavailable` 提供只读诊断，并允许用户在根目录确实缺失时手动安全创建。

## 任务

- 增加登录保护的媒体根目录诊断页
- 展示逻辑路径、状态、父目录与根目录身份、引用数量及处理后果
- GET 保持数据库与文件系统零写入
- 仅在状态为 `missing` 时显示初始化表单
- POST 复用 standard / strict 确认
- 从应用目录开始逐段以目录 FD 和 `O_NOFOLLOW` 验证父路径
- 重新确认根目录仍不存在后，仅创建配置中的目标目录
- 创建后 fsync 新目录及父目录
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档
- 将 C4 指定回归基线从 281 更正为 280

## 边界

- 不自动初始化
- 不处理 symlink、not_directory、unreadable 或 scan_failed
- 不删除、替换、移动、chmod 或 chown 任何现有路径
- 不创建或恢复媒体文件，不修改数据库引用
- 初始化不会恢复旧媒体；现有断裂引用继续交给 C1
- 不泄露宿主机绝对路径、原始 OSError、UID 或敏感挂载信息
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- GET 全程零写入
- 只有真实 missing 状态可以初始化
- 父路径替换、symlink 竞态、目标抢先创建及身份变化全部拒绝
- 不覆盖任何已存在的文件、目录或链接
- 成功后 `media_root_unavailable` 消失
- 原有媒体引用和其他文件保持不变
- Docker 挂载卷内可以成功初始化并跨重建保持
- C1-C4、媒体上传、扫描、Data Health、备份与导入无回归
- pytest、pip check、Docker 和 Actions 通过

## 本地验收

- C5 专项 `16 passed`，包括 mkdir 期间父路径替换后的拒绝
- C1-C4、上传、扫描、Data Health、恢复、备份校验与导入回归 `240 passed`
- 全量 `573 passed`，`pip check` 无依赖冲突
- Docker build、Compose healthy、`/login` 200 与 down 清理通过
- named volume 内初始化成功，容器重建后空目录保持且不再提供初始化表单
- 临时容器、网络、volume、cookie 与响应文件均已清理
- 功能提交 `9a3a546` 已推送 main，Actions run `29343264820` 的 test / Docker production smoke 均通过
