# GOAL.md

# 当前目标：Phase 3-B5 — 安全锚点手动恢复

## 目标

允许用户将合法 `.cleanup-anchor-*` 安全锚点手动恢复为普通
`recovered-*` 媒体，并安全迁移相关封面和头像引用。

## 任务

- 在恢复中心为合法锚点增加独立恢复预览
- GET 展示锚点身份、完整 SHA、引用和操作后果，保持零写入
- POST 复用 standard / strict 危险确认
- 提交时重新验证路径、类型、SHA、设备、inode、大小和时间戳
- 无覆盖创建唯一 `recovered-*` 文件并执行文件、目录 fsync
- 将全部封面 / 头像引用事务迁移到恢复文件
- 确认锚点已无引用后，再按身份安全删除原锚点
- 普通交互式封面 / 头像设置入口拒绝新建锚点引用
- 同步中英文、测试、CHANGELOG Unreleased 和当前文档

## 边界

- 每次只处理一个明确选择的合法锚点
- 不处理损坏锚点、符号链接、错误扩展或 `recovered-*`
- 不覆盖任何已存在文件
- 不自动恢复，不批量处理，不直接丢弃媒体内容
- 不改变 B1/B2/B3/B4 分组和审计语义
- 不影响备份恢复兼容性或 B3 内部锚点机制
- 不请求网络，不使用 AI 或图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag / Release，不部署 N100

## 完成标准

- 已引用和未引用合法锚点均可手动恢复
- 成功后引用全部指向存在、合法、同 SHA 的恢复文件
- 原锚点仅在零引用且身份未变化时删除
- 数据库失败时不删除锚点，并清理新建恢复文件
- 锚点删除失败时引用仍安全指向恢复文件，并明确报告残留
- 陈旧、伪造、变化或损坏请求全部拒绝
- GET 零写入，普通媒体和候选流程无回归
- pytest、pip check、Docker 和 Actions 通过

## 当前实现状态

- [x] 合法锚点单项预览展示完整 SHA、文件身份、全部引用和后果，GET 零写入
- [x] POST 复用 standard / strict `CONFIRM`，并重扫比对路径、类型、SHA、device、inode、size、mtime、ctime
- [x] 唯一 `recovered-*` 无覆盖发布已验证同 inode / SHA，并完成文件与目录 fsync
- [x] 全部封面 / 头像引用在单事务迁移，提交后复核零引用与完整身份再删除锚点
- [x] 数据库失败回滚并清理新恢复文件；删除失败保持恢复引用并报告锚点残留
- [x] 损坏、符号链接、错误扩展、陈旧、伪造、变化、普通及 `recovered-*` 请求均拒绝
- [x] 普通交互式封面 / 头像入口不能新建 cleanup anchor 引用，既有内部引用仍兼容
- [x] 中英文、CHANGELOG Unreleased、README、PLAN、TASKS、REVIEW、GOAL 和专项测试已同步
- [x] B5 专项 `12 passed`、全量 `486 passed`、pip check 与隔离 Docker 双生命周期通过并清理
- [x] 功能提交 `9e19509` 已推送 main，Actions run `29306074275` 的 test / Docker production smoke 均通过
- [x] 版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag / Release 和 N100 状态未改
