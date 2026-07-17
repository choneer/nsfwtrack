# 当前目标：Phase 4-R2C1 — 修复目录删除预览路由并重新完成 R2

## 1. 阶段目标

修复登录用户访问目录删除预览时发生的 `NameError`，补齐真实 HTTP 路由测试，然后在修复提交上重新执行完整 Phase 4-R2 发布候选验收。

这是最小 corrective implementation。

不得借本阶段修改目录删除业务语义、签名快照、FD 安全、媒体锁、事务、索引协调、Schema、版本或其他功能。

## 2. 必须读取的文件

开始前必须读取并遵守：

- `RULE.md`：长期开发、安全和数据规范
- `GOAL.md`：本阶段唯一授权
- `REVIEW.md`：R2.1–R2.14 完整验收门禁
- `PLAN.md`：项目阶段和发布路线
- `TASKS.md`：R2 当前状态
- `README.md`：Schema 升级、备份与回滚基线
- `CHANGELOG.md`：当前 Unreleased 范围
- `PERFORMANCE.md`：历史性能基线，只读参考

同时读取：

- `app/routers/pages.py`
- `app/services/local_media.py`
- `app/services/media_directory_management.py`
- `tests/test_media_directory_management.py`
- 相关路由、i18n、索引和锁测试

## 3. 授权基线

- 仓库：`/home/nsfwtrack`
- 分支：`main`
- HEAD / `origin/main`：

  `dfe908cabfc7d7bab24782da4ef6f24fd83d98bf`

- 应用版本：`1.0.6`
- Schema：`3`
- 稳定版：`v1.0.6`
- 稳定版 peeled commit：

  `961a3d0cc169e82b261d83207b0ec802007e292b`

开始时工作区只能是：

    M GOAL.md
    ?? data/

staged 必须为空。

## 4. data/ 安全边界

既有 `data/` 属于用户真实数据。

严禁：

- 进入或枚举 `data/`
- 读取任何内容、文件名或元数据
- 修改、删除、复制、移动或暂存其中内容
- 将其用于测试、迁移、备份、恢复或 Docker
- 使用仓库默认数据挂载执行验收

所有验证必须使用全新隔离临时目录、数据库和 Docker volume。

## 5. 允许修改的文件

只允许修改：

- `GOAL.md`
- `app/routers/pages.py`
- `tests/test_media_directory_management.py`

只有在新增测试确实需要中英文文案时，才允许修改：

- `app/i18n.py`

不得修改其他文件。

## 6. 最小实现修复

修复：

`media_directory_delete_preview()`

中未定义的 `local_media` 模块引用。

优先采用与当前 import 风格一致的最小修复：

- 显式导入 `validate_local_media_directory`
- 直接调用该函数

或采用功能完全等价、没有额外副作用的最小模块导入。

不得：

- 捕获 `NameError` 后返回 400
- 绕过目录验证
- 改用不安全的 `Path.stat`
- 重写目录删除服务
- 改变异常状态码或确认流程
- 修改签名 token 内容
- 降低保护目录和非法路径拒绝标准

## 7. 必须补充的测试

在 `tests/test_media_directory_management.py` 补充真实 HTTP 路由覆盖。

### 7.1 有效删除预览

已登录用户请求：

    GET /media-library/directories/delete?source=/media/library/empty

必须确认：

- 返回 200
- 页面包含合法签名 token
- 页面使用 `confirm=delete`
- 不返回 500
- 目录仍存在
- GET 前后数据库无写入
- GET 前后索引状态不变
- GET 不创建媒体操作锁文件
- 文件系统身份和内容不变

### 7.2 预览后删除 POST

使用 GET 返回的真实 token 请求：

    POST /media-library/directories/delete

必须确认：

- 返回 303
- 空目录被删除
- 每请求只调用一次索引协调
- `last_refresh_source=post_directory`
- `last_scan_kind=incremental`
- 索引保持 valid
- `stale_reason` 为空

### 7.3 拒绝路径

真实 GET 路由必须继续安全拒绝：

- 非空目录
- `/media`
- `/media/library`
- 非法或越界路径
- missing 路径
- symlink 或不安全对象

不得返回 500。

### 7.4 中英文与登录边界

确认：

- 匿名请求仍按现有登录保护处理
- 中文和 English 页面均不返回 500
- 不新增不对称 i18n key
- `tests/test_i18n.py` 继续通过

## 8. 本地测试

修复后执行并记录实际数量：

1. 新增删除预览路由测试
2. `tests/test_media_directory_management.py`
3. 全部 `tests/test_media_*.py`
4. 页面、路由、错误处理和 i18n 相关测试
5. 全量 pytest
6. `pip check`

执行：

    git diff --check

不得沿用之前 R2 的测试数量，必须报告本次实际结果。

## 9. Docker corrective 验证

在提交前使用隔离 Docker 环境重放 R2.9 生命周期：

- 启动并 healthy
- `/login` 200
- 上传媒体
- 建立 Item cover 和 Creator avatar 引用
- 建立有效索引
- create
- rename
- move
- 删除空目录 GET 预览返回 200
- 使用预览 token 执行删除 POST
- 引用保持最终路径
- 旧路径消失
- 索引只包含最终路径
- `post_directory`
- incremental
- 每请求单次协调

保留同一隔离 volume 重建容器，确认第二生命周期持久性和安全属性。

## 10. 提交与 Actions

确认只修改授权文件后，创建一笔提交：

    Fix media directory delete preview route

推送 `main`，等待该提交对应的：

- `test`
- `Docker production smoke`

均成功。

不创建第二笔 corrective 提交。

## 11. 在最终提交上重新执行完整 R2

Actions 通过后，在最终提交且工作区只剩 `?? data/` 的状态下，重新执行 `REVIEW.md` 的 R2.1–R2.14。

可以复用之前建立的隔离脚本和执行方法，但不得复用旧运行结果。

本轮必须补齐此前未完成的：

- 真实稳定版 Schema 2 数据库升级
- 稳定版真实 JSON 备份兼容
- 恢复失败原子性
- 恢复后索引失效与 full rebuild
- 完整 outcome/index 动态矩阵
- 完整 Docker 双生命周期
- 删除空目录真实 GET 和 POST

任一门禁失败时停止，不继续修复。

## 12. 禁止事项

不得：

- 修改应用版本
- 修改 Schema 或迁移
- 修改依赖、Docker、CI 或工作流
- 扩展功能
- 修改其他文档
- 创建 tag 或 Release
- 部署 N100
- 接触既有 `data/`
- 在 R2 未全部通过时宣称候选可发布

## 13. 最终报告

一次性报告：

### Corrective implementation

- 开始 SHA
- 最终提交 SHA
- 修改文件
- 根因
- 修复方式
- 新增测试
- 测试数量
- Actions run 和两个 job 结果

### R2.1–R2.14

按 `REVIEW.md` 逐项提供：

- 实际命令或方法
- 实际证据
- 结果

### Schema 与备份

- 稳定版数据库生成
- 2 → 3 升级
- 1 → 2 → 3
- 稳定版备份
- 当前版恢复
- 故障回滚
- 索引失效与重建

### Docker

- 第一生命周期
- create / rename / move / delete
- 精确引用
- 索引状态
- 第二生命周期
- 安全属性
- 清理

### 工作区与边界

- HEAD / origin/main
- `git status --short`
- `data/` 未接触
- 版本 1.0.6
- Schema 3
- 无 tag、Release、N100

### 最终结论

只能选择：

- Corrective 通过且 R2 全部通过，可进入云端复核
- Corrective 通过但 R2 仍不通过
- Corrective 不通过
- 因环境问题未完成

完成后停止，等待云端复核。