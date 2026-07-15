# GOAL.md

# 当前目标：Phase 4-A2 — 普通媒体安全重命名

## 目标

允许用户从普通媒体详情页预览并手动确认修改文件名，
同时安全迁移全部封面和头像引用。

## 任务

- 为有效普通媒体增加登录保护的重命名预览 GET
- 只允许修改同目录下的 basename，扩展名必须保持不变
- 展示源路径、目标路径、完整 SHA、身份、引用和后果
- 目标名称执行严格校验，不接受路径段、控制字符、保留前缀或过长名称
- 禁止覆盖现有文件、symlink、目录或其他对象
- confirmed POST 复用 standard / strict CONFIRM
- 通过验证父目录 FD 创建目标硬链接，不重新解析可替换路径
- 事务内将全部 item cover 和 creator avatar 引用迁移到目标路径
- 数据库失败时删除新目标并保留原文件和原引用
- 提交后再安全删除原路径；删除失败时准确报告双路径保留
- 从 A1 详情页进入，完成后返回新文件详情页
- 同步双语、测试和 Unreleased 文档

## 边界

- 仅允许有效普通媒体和 recovered 普通媒体
- 不允许 cleanup anchor、上传残留、损坏、symlink、特殊文件或扫描跳过项
- 不允许跨目录移动、目录创建、扩展名修改、覆盖或批量操作
- 不修改条目标题、创作者名称、标签、来源或其他元数据
- 不请求网络资源，不增加识别、AI、爬虫或远程图片
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI
- 不创建 tag、Release，不部署 N100

## 完成标准

- 有引用和无引用文件都能安全改名
- 全部封面和头像引用准确迁移
- SHA、内容和重复组关系保持不变
- 目标抢占、父目录替换、文件身份变化和伪造请求全部拒绝
- 数据库失败保留原状态，不产生目标残留
- 原路径删除失败时目标和引用仍有效，并给出准确结果
- GET 零写入，所有失败路径不覆盖或删除外部对象
- pytest、pip check、Docker 和 Actions 通过

## A2 当前结果

- 已新增 A1 详情入口、登录保护 GET 预览和 confirmed POST；仅有效普通 / recovered 媒体可进入
- basename、原扩展名、保留前缀、长度、目标对象和目标引用均严格校验，不允许跨目录、覆盖或批量操作
- 预览展示源 / 目标、完整 SHA、mode / size / dev / inode / mtime / ctime、全部引用与后果，SQL / 文件 / 目录写入为零
- POST 在 `BEGIN IMMEDIATE` 内重验源、目标与全部引用，通过 held verified parent FD 创建 no-overwrite 同 inode 目标
- 全部 cover / avatar 引用精确迁移；数据库失败 rollback 并按 inode 清理自建目标，commit 后才身份绑定删除源
- unlink / fsync / 删除复核失败均保留有效目标和引用，并按实际状态报告源路径；成功返回保留来源状态的新详情
- 目标抢占、源 / 目标替换、普通目录 / symlink 父替换、同 inode hardlink、引用变化、commit / unlink 失败均有专项覆盖
- SHA、内容、inode 与完整 SHA 重复组关系保持，不通过目标 `Path.stat` / `Path.read_bytes` 二次打开
- A2 专项 `43 passed`；local-media / B3 / B5 / C1/C2/C4 / A1 / i18n 回归 `144 passed`；媒体 / Data Health / 备份 / UI 组合 `309 passed`
- 全量 `644 passed in 119.82s`，`pip check` 无冲突；Docker build、隔离 Compose healthy、`/login` / 匿名 rename / API login / 认证媒体库 HTTP 验收通过，临时资源已清理
- 实现提交 `b32e848` 已推送；Actions run `29396021693` 的 `test` 与 `Docker production smoke` 均为 success
- 版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 均未改变
