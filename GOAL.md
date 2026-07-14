# GOAL.md

# 当前目标：Phase 3-C3 — 媒体扫描跳过项定位中心

## 目标

让用户能够只读查看媒体扫描中被跳过的具体路径及原因，
替代当前只有汇总数量、无法定位问题的状态。

## 任务

- 记录每个扫描跳过项的相对路径和稳定原因代码
- 区分符号链接、扩展名不支持、特殊文件、目录不可读和条目检查失败
- 新增登录保护的只读跳过项页面
- 支持路径搜索、类型筛选、稳定排序和每页 20 条分页
- 展示路径、类型、扩展名及可安全取得的 stat 信息
- Data Health 汇总告警链接到对应筛选结果
- 保留现有 skipped_symlinks / skipped_unsupported 汇总兼容性
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 全程只读，不提供删除、移动、改名、恢复或关联操作
- 不跟随符号链接，不读取符号链接目标
- 不读取、解析或哈希被跳过文件的内容
- 不显示原始系统异常、绝对宿主机路径或敏感信息
- 不把 unsupported 文件当作合法媒体
- 不改变普通媒体、cleanup anchor、recovered-* 或上传残留行为
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- 页面 GET 和 Data Health GET 均零写入
- 路径结果确定、去重且排序稳定
- 符号链接只通过 lstat 识别，绝不跟随
- 不读取任何被跳过文件的内容
- 单个目录或条目失败不会中断整个扫描
- 汇总数量与逐项列表一致
- 搜索、筛选、排序和分页状态正确保留
- A3-A6、B1-B6、C1-C2、上传和媒体库无回归
- pytest、pip check、Docker 和 Actions 通过

## 本地验收

- C3 专项：`8 passed`
- A3-A6、B1-B6、C1-C2、媒体库、上传、Data Health、备份与导入组合回归：`261 passed`
- 全量测试：`538 passed`
- 依赖检查：`pip check` 无冲突
- Docker：image build、Compose healthy、`/login` 200、未登录跳过项页 303、down 清理均通过
- 功能提交：`c591ca4`，已推送 `main`
- GitHub Actions：run `29321642902` 的 `test` 与 `Docker production smoke` 均通过
