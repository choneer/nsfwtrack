# GOAL.md

# 当前目标：Phase 2-L2 — 直接依赖版本基线

请先读取 `RULE.md`、`PLAN.md` 和 `TASKS.md`。

## 目标

固定项目直接依赖的兼容版本，使开发、CI 和 Docker 安装结果更稳定。

## 任务

- [x] 在全新 Python 3.12 环境确认当前兼容依赖版本
- [x] 固定 `requirements.txt` 中的直接运行时依赖
- [x] 固定 `requirements-dev.txt` 中的直接测试依赖
- [x] CI 增加 `pip check`
- [x] 验证全新安装、全量测试和隔离 Docker

## 边界

- 只固定直接依赖，不生成庞大的传递依赖锁文件
- 不盲目升级到最新版本
- 不修改业务代码、数据库、Schema 或迁移
- 不新增产品功能，不创建 Release
- 所有测试在 WSL `/home/nsfwtrack` 执行

## 完成标准

- 全新环境可安装且 `pip check` 通过
- 全量测试无警告、无回归
- Docker build/up/down 与 `/login` 通过
- 更新相关文档和 `CHANGELOG.md`
- 提交并推送

## 执行结果

- [x] 在全新 Python 3.12 venv 安装当前已验证直接依赖版本
- [x] 运行时直接依赖固定为 fastapi / uvicorn / sqlalchemy / jinja2 / python-multipart / itsdangerous 的已验证版本
- [x] 测试直接依赖固定为 httpx2==2.5.0 / pytest==9.1.1
- [x] 未生成完整传递依赖锁文件；未盲目升级
- [x] CI 在安装后增加 `pip check`
- [x] 全新 venv：`pip check` 通过；`347 passed` 无弃用警告
- [x] 隔离 Docker build / up / `/login` 200 / version 1.0.1 / down 清理通过
- [x] 业务代码、数据库、Schema、迁移未改
