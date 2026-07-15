# GOAL.md

# 当前目标：Phase 4-A1 — 本地媒体单文件详情页

## 目标

为普通本地媒体增加统一、登录保护、只读的单文件详情页，
集中展示文件身份、可用状态、引用、重复关系和相关安全入口。

## 任务

- 新增登录保护的普通媒体详情 GET 页面
- 使用规范化媒体路径定位目标，不接受外部 URL、转义路径或 cleanup anchor
- 复用现有安全扫描和 FD 验证结果，不直接通过 Path 重新读取目标
- 展示逻辑媒体路径、文件名、扩展名、MIME、大小和完整 SHA-256
- 展示有效、损坏、recovered、已引用、未引用和重复状态
- 展示所有条目封面和创作者头像引用，并链接到对应对象
- 展示重复组数量、组大小和可释放空间，并链接到准确重复组
- 有损坏或引用问题时，仅链接到现有 C1/C4 安全流程
- 从媒体库文件卡片、重复组成员和 recovered 普通媒体进入详情页
- 同步中英文、测试和 Unreleased 文档

## 边界

- GET 必须保持数据库和文件系统零写入
- 不新增删除、移动、重命名、替换或批量操作
- 不展示宿主机绝对路径或原始 OSError
- cleanup anchor 继续只进入恢复中心，不进入普通详情页
- 不请求网络资源，不增加爬虫、远程图片、识别或 AI
- 不修改版本 1.0.6、Schema 2、迁移、依赖、Docker/CI
- 不创建 tag、Release，不部署 N100

## 完成标准

- 有效、损坏、recovered、重复及有/无引用媒体均能准确展示
- 非法路径、缺失、symlink、特殊文件和 anchor 请求安全拒绝
- 页面不读取任何外部替换目标，不泄露主机路径或异常
- 所有入口和返回链接保留原列表筛选状态
- GET 前后数据库、目标文件和目录状态完全不变
- 原有媒体、重复组、恢复、Data Health 和备份功能无回归
- pytest、pip check、Docker 和 Actions 通过

## A1 当前结果

- 已新增登录保护、仅 GET 的普通媒体详情页，非法 / 外部 / 转义 / missing / symlink / 特殊文件 / cleanup anchor 均安全 404
- 文件事实复用现有安全扫描和验证 FD 链，不通过目标 `Path.stat` / `Path.read_bytes` 二次打开
- 已展示路径、文件名、扩展名、MIME、size、完整 SHA、有效 / 损坏 / recovered / 引用 / 重复状态
- 已展示全部 item cover / creator avatar 引用及对象链接，并按完整 SHA 展示准确重复组与入口
- 损坏文件 / 引用只复用 C4 / C1；详情页未新增 POST 或其他写操作
- 媒体库、重复组、恢复中心 recovered 普通媒体入口均保留规范化筛选、排序和分页返回状态
- SQL 写捕获为 0，文件 / 目录快照不变，父目录替换竞态不读取外部目标
- A1 专项 `17 passed`，媒体 / 恢复 / C1/C4 / Data Health / 备份 / UI 组合 `252 passed`
- 全量 `601 passed in 91.96s`，`pip check` 无冲突；Docker build、隔离 Compose healthy、`/login` / 匿名详情 / 认证详情与媒体库 HTTP 验收通过，临时资源已清理
- 实现提交 `c8cfb99` 已推送；Actions run `29389862206` 的 `test` 与 `Docker production smoke` 均为 success
- 版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 均未改变
