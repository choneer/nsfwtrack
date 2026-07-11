# GOAL.md

# 当前目标：Phase 2-K2 — 投入使用前边界收口

请读取 `RULE.md`、`COMPLETION_AUDIT.md` 和 `TASKS.md`。

## 目标

完成 K1 审计确认的投入使用前阻塞项：

- 收紧 `cover_path` 和 `avatar_path`，只允许明确的本地路径
- 补齐批量写入、状态清除和关系解除的确认流程
- 启动时拒绝 `.env.example` 中的示例凭据
- 补齐 F4 安全提示专项测试
- 增加简洁的安装、升级和回滚清单

## 边界

- 不增加远程图片、上传、代理或 URL 导入
- 不新增依赖
- 不修改数据库结构、Schema 或迁移
- 不创建新版本或 Release
- 不接触默认 schema 2 数据卷

## 完成标准

- 三个审计问题全部关闭
- 相关安全与回滚测试通过
- 全量测试和隔离 Docker 验收通过
- 更新 `COMPLETION_AUDIT.md`、`PLAN.md`、`TASKS.md` 和相关文档
- 提交并推送

## 执行结果

- [x] 三个 K1 审计问题已关闭
- [x] F4 中英文、备份链接、提醒模式和空状态专项测试已补齐
- [x] README 已增加单一安装、升级、备份和回滚清单
- [x] 全量测试 `347 passed`
- [x] 隔离 Docker build / up / `/login` 200 / 登录后本地媒体 200 / down 通过并清理
- [x] 提交并推送
