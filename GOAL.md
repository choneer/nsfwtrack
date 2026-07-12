# GOAL.md

# 当前目标：Phase 2-L3 — 浏览器安全响应头基线

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

为所有 HTML、JSON、错误和重定向响应增加一致的安全响应头。

## 任务

- [x] 增加统一的安全响应头中间件
- [x] 覆盖成功、重定向、404、422、500 和媒体响应
- [x] 至少处理：
  - `X-Content-Type-Options`
  - `Referrer-Policy`
  - 防止页面被第三方框架嵌入
  - 禁用不需要的浏览器权限
- [x] 保持 request ID、405 `Allow` 和现有页面行为不变
- [x] 增加专项测试并完成全量测试与隔离 Docker 验收

## 边界

- 不添加会破坏现有表单或脚本的激进 CSP
- 本地 HTTP 环境不启用 HSTS
- 不修改业务逻辑、数据库、Schema、依赖或版本
- 所有测试在 WSL `/home/nsfwtrack` 执行

## 完成标准

- 所有响应包含预期安全头
- 登录、媒体、错误响应和确认流程无回归
- 全量测试、`pip check` 和 Docker 验收通过
- 更新文档后提交推送

## 执行结果

- [x] 新增 `SecurityHeadersMiddleware`，统一附加最小安全响应头
- [x] 覆盖 HTML 成功、重定向、404、422、405、JSON API 与本地媒体响应
- [x] 头集合：`X-Content-Type-Options: nosniff`、`Referrer-Policy: strict-origin-when-cross-origin`、`X-Frame-Options: DENY`、受限 `Permissions-Policy`
- [x] 未启用 HSTS；未加入激进 CSP
- [x] 保留 `X-Request-ID` 与 405 `Allow`
- [x] 专项 9 项通过；全量 `356 passed`；`pip check` 通过；隔离 Docker `/login` 200 且头齐全
- [x] 未改业务逻辑、数据库、Schema、依赖或版本
