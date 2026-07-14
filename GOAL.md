# GOAL.md

# 当前目标：Phase 3-C4 — 损坏媒体文件手动清理

## 目标

允许用户逐项预览并安全删除无法通过本地图片校验的零引用媒体文件。

## 任务

- 为损坏普通媒体增加 Data Health 单项记录和清理入口
- 媒体库 invalid 卡片提供单项预览链接
- GET 展示安全相对路径、原始 SHA、size、device、inode、mtime、ctime、引用和后果
- GET 保持零写入，只做有上限的本地内容校验
- POST 复用 standard / strict 危险确认
- 提交时重新验证路径、完整身份、原始 SHA，并确认文件仍然损坏
- 使用 `BEGIN IMMEDIATE` 重新确认封面和头像引用均为零
- 按目录 FD 只删除选定目标，并 fsync 所在目录
- 展示成功、未删除失败及已删除但同步失败警告
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 仅处理允许扩展名的普通非符号链接文件
- `recovered-*` 继续按普通媒体处理
- 不处理有效图片、cleanup anchor、上传残留、扫描跳过项、目录或特殊文件
- 已引用目标只提供 C1 修复指引，不显示删除表单
- 不修改、迁移或清除任何数据库引用
- 不自动清理，不批量删除，不恢复或改写文件
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- GET 全程零写入
- 有效图片、伪造路径、符号链接、陈旧身份、SHA 变化和同路径替换全部拒绝
- 文件在预览后变为有效图片时拒绝删除
- 引用新增竞态在写锁内拒绝
- unlink 失败时文件与数据库不变
- unlink 成功但目录 fsync 失败时准确报告已删除警告
- 删除后媒体库和 Data Health 不再显示目标
- 非目标文件及数据库保持不变
- B3-B6、C1-C3、媒体上传、恢复中心和备份导入无回归
- pytest、pip check、Docker 和 Actions 通过

## 本地验收

- C4 专项：`17 passed`
- B3-B6 / C1-C3 / 媒体链 / Data Health / 备份导入组合回归：`281 passed`
- 全量 pytest：`557 passed`
- pip check：无依赖冲突
- Docker image build：通过
- Docker Compose：healthy
- `/login`：HTTP 200
- Docker down：容器与网络已清理
- 功能提交：`1e686f3`，已推送 `origin/main`
- Actions：run `29336790587` 的 test / Docker production smoke 均通过
