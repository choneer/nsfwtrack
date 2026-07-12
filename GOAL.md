# GOAL.md

# 当前目标：Phase 2-L1 — 测试依赖兼容性收口

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

消除现有 TestClient / HTTPX 弃用警告，并让测试依赖版本可重复安装。

## 边界

- 先复现并确认警告根因
- 使用最小的依赖兼容调整解决
- 不通过过滤或忽略警告掩盖问题
- 不修改业务逻辑、数据库、Schema 或迁移
- 不新增产品功能，不创建 Release

## 完成标准

- 全量测试通过且该弃用警告消失
- 隔离 Docker 验收通过
- 更新相关依赖声明、文档和 CHANGELOG
- 提交并推送

## 执行结果

- [x] 根因确认：Starlette 1.3.1 `testclient` 在仅有 `httpx` 时发出 `StarletteDeprecationWarning`，要求安装 `httpx2`
- [x] 最小修复：`requirements-dev.txt` 将 `httpx` 替换为 `httpx2==2.5.0`（仅测试依赖，不进运行时镜像）
- [x] 全量测试 `347 passed`，弃用警告消失
- [x] 隔离 Docker build / up / `/login` 200 / down 与清理通过
- [x] 文档与 CHANGELOG Unreleased 已更新
