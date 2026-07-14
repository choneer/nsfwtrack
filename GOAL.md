# GOAL.md

# 当前目标：Phase 3-C2 — 上传残留文件手动清理

## 目标

允许用户从 Data Health 中逐项确认并安全删除遗留的
`.upload-*.tmp` 本地上传临时文件。

## 任务

- 为 `media_upload_residue` 增加登录保护的单项清理入口
- GET 展示路径、大小、device、inode、mtime、ctime 和删除后果
- GET 保持数据库与文件零写入
- POST 复用 standard / strict 危险确认
- 提交时重新验证路径、文件类型和完整身份
- 使用 `BEGIN IMMEDIATE` 重新确认没有封面或头像引用该路径
- 按身份只删除用户选择的目标，并 fsync 所在目录
- 展示成功、失败及目录同步警告
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 仅处理 basename 精确匹配 `.upload-*.tmp` 的普通文件
- 不处理符号链接、目录、普通媒体、cleanup anchor 或 recovered-*
- 已被封面或头像引用的残留必须先通过 C1 修复
- 不自动清理，不批量删除
- 不读取、解析或恢复临时文件内容
- 不修改任何数据库引用
- 不操作其他媒体文件
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- GET 全程零写入
- 路径伪造、名称近似、符号链接、缺失和身份变化请求全部拒绝
- 引用新增竞态在写锁内拒绝，文件保持不变
- unlink 失败时文件和数据库保持不变
- unlink 成功但目录 fsync 失败时准确报告已删除警告
- 成功后 Data Health 不再报告目标残留
- 非目标记录和文件保持不变
- C1、B3-B6、媒体上传和备份流程无回归
- pytest、pip check、Docker 和 Actions 通过

## 本地验收记录

- C2 专项：`22 passed`
- C1 / B3-B6 / 上传 / Data Health / 备份 / 导入组合回归：`253 passed`
- 全量测试：`530 passed`
- `pip check`：无依赖冲突
- Docker image build：通过
- Docker Compose：healthy，`/login` HTTP 200，验收后已完整 down
- 功能提交：`ab373b3`，已推送 `main`
- GitHub Actions：run `29317914417` 的 test / Docker production smoke 均通过
- 版本保持 `1.0.6`，Schema 保持 `2`
- 迁移、依赖、Docker/CI、旧 tag / Release 与 N100 状态未修改
