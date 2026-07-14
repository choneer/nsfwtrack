# GOAL.md

# 当前目标：Phase 3-C1 — 断裂媒体引用手动修复

## 目标

允许用户从 Data Health 中逐项修复条目封面或创作者头像的无效引用。

## 任务

- 为媒体引用问题增加登录保护的单项修复入口
- 支持缺失、损坏、符号链接、非法路径和内部损坏锚点引用
- GET 展示对象、当前引用、问题类型和修复后果，保持零写入
- 用户手动选择一个现有合法媒体作为替代，或明确清除引用
- 替代媒体支持路径 / SHA 搜索、稳定排序和分页
- POST 复用 standard / strict 危险确认
- 提交时重新验证对象、原引用、问题状态和替代媒体完整身份
- 使用条件更新，仅修改用户选择的一个封面或头像引用
- 修复完成后展示旧路径、新路径或清除结果
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 不自动推荐替代媒体
- 不自动清除引用
- 每次只处理一个条目封面或一个创作者头像
- 替代目标必须是存在、合法、可用的普通本地媒体
- 不允许将 cleanup anchor 设为新引用
- recovered-* 可用的普通本地媒体
- 不允许将 cleanup anchor 设作为普通合法媒体使用
- 不删除、移动、改名或修改任何媒体文件
- 不批量修复，不处理其他 Data Health 问题
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- GET 全程零写入
- 陈旧、伪造、对象变化和原引用变化请求全部拒绝
- 替换后引用指向存在、合法且完整验证通过的媒体
- 清除模式只清除用户确认的单个引用
- 数据库失败完整回滚
- Data Health 修复后不再报告对应问题
- 非目标记录和全部媒体文件保持不变
- B3-B6、媒体库、备份与导入兼容性无回归
- pytest、pip check、Docker 和 Actions 通过

## 当前实现状态

- [x] Data Health 为五类无效封面 / 头像引用及损坏锚点引用提供登录保护的单项入口
- [x] GET 展示对象、原路径、问题类型、对象快照和后果，全程不写数据库或媒体文件
- [x] 替代候选按路径 / SHA 搜索、稳定排序和固定 20 条分页，只接受完整验证通过的普通媒体
- [x] `recovered-*` 保持普通媒体候选，cleanup anchor、损坏文件和符号链接不进入候选且服务端拒绝
- [x] 用户只能逐项明确替换或清除，不自动推荐、自动清除、批量修复或处理其他健康问题
- [x] POST 复用 standard / strict `CONFIRM`，并在 `BEGIN IMMEDIATE` 内重验对象、原引用和问题状态
- [x] 替换媒体按完整 SHA、size、device、inode、mtime、ctime 验证，条件更新后提交前再次确认身份
- [x] 条件 UPDATE 只修改一个 `item.cover_path` 或 `creator.avatar_path`，原值竞态、陈旧与伪造请求拒绝
- [x] 写锁、UPDATE、最终身份或 commit 失败整笔回滚，不修改、删除、移动或重命名任何文件
- [x] 成功结果展示旧路径、新路径或清除；Data Health 自然移除目标问题并保留非目标状态
- [x] 中文 / English、CHANGELOG Unreleased、README、PLAN、TASKS、REVIEW、GOAL 与专项测试已同步
- [x] C1 专项 `7 passed`、B3-B6 / 媒体库 / Data Health / 备份 / 导入组合回归 `232 passed`
- [x] 全量 `508 passed`、pip check 与隔离 Docker 双生命周期、真实替换 / 清除和媒体零变化验收通过
- [x] 功能提交 `05adaf7` 已推送 main，Actions run `29314452641` 的 test / Docker production smoke 均通过
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag / Release 和 N100 状态不变
