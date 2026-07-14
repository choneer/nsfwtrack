# GOAL.md

# 当前目标：Phase 3-B6 — 无引用安全锚点手动清理

## 目标

允许用户明确确认后，安全删除不再被任何封面或头像引用的合法
`.cleanup-anchor-*` 残留文件。

## 任务

- 在恢复中心为合法、未引用锚点增加单项清理预览
- GET 展示路径、完整 SHA、大小、文件身份和永久删除后果
- POST 复用 standard / strict 危险确认
- 提交时重新扫描并验证完整 SHA、device、inode、size、mtime、ctime
- 使用数据库写锁重新确认条目封面和创作者头像引用数均为零
- 按完整文件身份删除目标并 fsync 所在目录
- 展示删除结果和明确失败原因
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 仅处理合法且零引用的 cleanup anchor
- 不处理已引用、损坏、符号链接、错误扩展或 recovered-* 文件
- 不自动清理，不批量处理
- 不迁移或清除任何数据库引用
- 不改变 B3、B4、B5 恢复流程
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- GET 全程零写入
- 引用新增、身份变化、哈希变化、缺失或伪造请求全部拒绝
- 仅删除用户确认的目标文件
- 删除失败时文件和数据库保持安全状态
- Data Health 和恢复中心能够反映删除后的状态
- 普通媒体、B1/B2、A3/A4 与 B3-B5 无回归
- pytest、pip check、Docker 和 Actions 通过

## 当前实现状态

- [x] 合法零引用锚点单项 GET 预览展示完整 SHA、size、device、inode、mtime、ctime 和永久后果，保持零写入
- [x] POST 复用 standard / strict `CONFIRM`，提交时重扫并逐字段验证完整身份
- [x] 结束预检读事务后使用 `BEGIN IMMEDIATE`，锁内复核条目封面和创作者头像引用均为零
- [x] 最终删除前再次验证身份与 SHA，身份绑定 unlink 后 fsync 所在目录
- [x] 已引用、损坏、符号链接、错误扩展、普通、`recovered-*`、缺失、陈旧、伪造和变化请求均拒绝
- [x] 引用竞态在写锁复核时拒绝，文件保留且不迁移或清除数据库引用
- [x] 删除 / 写锁失败保留目标并报告原因；目录同步失败准确报告文件已移除警告
- [x] 仅删除用户确认的一个目标，不创建恢复文件、不批量或自动清理
- [x] 中英文、CHANGELOG Unreleased、README、PLAN、TASKS、REVIEW、GOAL 和专项测试已同步
- [x] B6 专项 `15 passed`，媒体链及 B3-B5 回归 `156 passed`
- [x] 全量 `501 passed`、pip check 与最终工作树隔离 Docker 双生命周期及真实确认删除验收通过并清理
- [x] 功能提交 `b70e18e` 已推送 main，Actions run `29309167659` 的 test / Docker production smoke 均通过
- [x] 版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag / Release 和 N100 状态未改
