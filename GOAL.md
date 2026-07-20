# Phase 6 — v1.3.0 Controlled Acquisition and Manual Update Bundle

## 1. 阶段目标

本阶段不再拆分 N6A/N6B/N6C/N7A 等小阶段，而是一次性完成：

```text
统一任务基础设施
+ 受控资产保存与下载
+ 手动来源检查
+ 元数据差异预览
+ 用户逐字段确认更新
+ 完整任务中心与状态 UI
+ Schema 5
+ 端到端测试与 Docker 验证
```

开发流程：

```text
Codex 全量实现
→ 本地全量验证
→ 普通提交并推送
→ GitHub Actions
→ 一次云端整体复核
→ RC 冻结后再安排一次 Hermes 验收
```

中途不因普通环境、工具兼容、测试断言同步、文件范围遗漏或临时脚本问题请求授权。

## 2. 基线

```text
repository: /home/nsfwtrack
branch: main
base: 22781d3e5cd040d6d1def24f140b6725dc25c0db
latest stable: v1.2.0
Application: 1.2.0
Schema: 4
Backup export: nsfwtrack.backup.v2
Backup restore: v1/v2
Production Endpoint Registry: empty
Production Search Packages: empty
Production Search Providers: empty
full pytest baseline: 1402 passed
```

开始前：

```bash
cd /home/nsfwtrack
git fetch origin main --tags
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

必须满足：

```text
HEAD == origin/main == 22781d3e5cd040d6d1def24f140b6725dc25c0db
```

工作区只允许既有：

```text
?? data/
```

将本 GOAL 放入仓库后允许：

```text
M GOAL.md
?? data/
```

既有 `/home/nsfwtrack/data/` 不得读取、枚举、进入、复制、修改、移动、删除、格式化、暂存或提交。

## 3. 宽执行边界

采用“按功能类别授权”，不使用逐文件白名单。

Codex 可自行创建、修改、重构完成本阶段所必需的：

```text
app/**
tests/**
templates / i18n
models / migrations / schema verification
routers / services / contracts / DTOs
config / example configuration
README / CHANGELOG / PLAN / TASKS / REVIEW / RULE / Provider docs
Docker smoke assertions
```

允许：

- 自动发现并修改相关测试与文档；
- 自动处理 `python` / `python3` / `.venv/bin/python` 差异；
- 自动处理 Shell、CLI、SQLite、SQLAlchemy、Jinja、HTMX 等兼容问题；
- 自动修复测试、lint、类型、格式、临时脚本和只读审计问题；
- 为完成同一功能合理扩大文件范围；
- 自动创建后续修复提交，不因普通失败停下；
- 使用多个逻辑提交组织大型功能；
- 在最终推送前反复运行并修复测试；
- 在不弱化安全性的前提下重构现有 N5C、媒体写入、索引协调和事务辅助代码。

优先不增加第三方依赖。确有必要时可自行增加维护良好且用途明确的依赖，并同步 requirements、Docker 和测试，无需中断，但必须在最终报告说明理由。

## 4. 只有以下情况必须停止

仅在出现真正高风险情况时停止并报告：

1. 需要读取、修改、迁移或删除既有 `data/`；
2. 迁移设计可能破坏已有用户数据，且无法证明事务回滚；
3. 需要 force push、重写已发布历史、移动或删除既有 Tag/Release；
4. 需要启用真实 Provider、真实外部 Host、真实凭据或真实内容来源；
5. 发现密钥、Cookie、Token、密码或隐私数据可能泄漏；
6. 需要绕过访问控制、权限、付费、年龄或地区限制；
7. 需要部署 N100、发布镜像或创建新 Release/Tag；
8. 产品目标必须发生实质改变，而不是实现细节调整；
9. 无法在不削弱现有安全、事务、Session 或文件系统边界的情况下完成。

普通代码缺陷、环境差异、命令错误、测试失败、遗漏文件、Schema 实现细节、CLI 不兼容和只读诊断问题不得抛回。

## 5. 版本与发布边界

本阶段是 v1.3.0 功能开发，不是 RC 或正式发布。

保持：

```text
Application = 1.2.0
latest stable = v1.2.0
```

可以更新开发文档为：

```text
next target = v1.3.0
Phase 6 bundle = in development / completed after implementation
```

不得提前改为 1.3.0，不创建 v1.3.0 Tag/Release，不再次调用 Hermes，不部署 N100。

## 6. Schema 5

明确授权 Schema 4 → 5，用于持久化统一任务和必要历史。

必须支持：

```text
fresh Schema 5
1 → 2 → 3 → 4 → 5
2 → 3 → 4 → 5
3 → 4 → 5
4 → 5
repeat migration
future schema rejection
structural mismatch rejection
transaction rollback
```

稳定 v1.2.0 对 Schema 5 的拒绝行为必须测试。

Backup 保持：

```text
Backup export = nsfwtrack.backup.v2
Restore = v1/v2
```

任务、临时状态、进度、错误、运行租约和操作历史属于运行数据，不进入普通业务备份。恢复 v1/v2 后新任务表为空、Schema 为 5、原业务数据保持、零网络、不自动恢复任务。

## 7. 统一任务模型

至少支持任务类型：

```text
asset_download
source_check
metadata_update
```

建议状态：

```text
planned
awaiting_confirmation
queued
running
paused
cancelling
cancelled
succeeded
failed
blocked
outcome_unknown
```

状态名称可调整，但必须：

- 状态闭集和合法转换矩阵；
- 非法转换拒绝；
- 乐观并发或版本事实；
- 类型/状态数据库约束；
- UTC 时间；
- 稳定脱敏错误码；
- 不保存秘密、完整 locator、Cookie、Token 或原始响应；
- 可关联 Item、ItemSource、Provider identity、Asset identity；
- 可记录 bytes、expected size、MIME、hash、目标相对路径等受限事实；
- 支持取消、重试、恢复、分页、过滤与终态历史清理；
- 删除历史必须显式确认且不删除正式媒体。

任务租约与恢复：

- 同一任务同一时刻只能由一个执行者运行；
- 租约含 owner、generation、started/heartbeat/expiry；
- 重启后的遗留 running 不能视为成功；
- 恢复为 paused、blocked 或安全可重试状态；
- 重启后不自动恢复网络操作；
- stale lease 可安全回收；
- 失败分类基于持久化事实，不基于异常类型猜测。

## 8. Provider-neutral 下载合同

不接真实 Provider。Production Provider/Package/Endpoint Registry 继续为空。

实现 Provider-neutral 下载合同和 tests-only synthetic Adapter：

```text
asset descriptor
download authorization
stream/open operation
optional range resume
content metadata
bounded chunk stream
cancellation
stable errors
```

要求：

- Web/UI 不能提交任意 URL、Host、协议、端口、base URL 或路径；
- 下载依据只能来自已验证 Package 的 opaque Provider/External/Asset identity；
- locator 只在 Adapter/Outbound 内部短暂存在；
- locator 不进入 HTML、日志、普通数据库字段、Token 或错误；
- capability/operation 显式批准；
- 无 download capability 时在网络和文件动作前拒绝；
- tests-only Adapter 使用内存字节、临时文件或 `.invalid` 合成环境；
- 测试不得访问真实 DNS、真实站点或真实内容源；
- Production registry 继续为空。

## 9. 下载 Preview 与 Confirm

闭环：

```text
Asset facts
→ Download Preview
→ 用户明确确认
→ 创建 confirmed task
→ 显式开始/恢复
→ 临时隔离写入
→ 校验
→ 原子发布
→ 建立本地关系
→ 媒体索引协调
```

Preview：零文件写入、零执行、零网络；展示 Provider、Asset 类型、建议文件名、预计大小、MIME、Hash 可用性、目标 Item、冲突与重复；使用 Session-bound、purpose-bound、短 TTL 签名 Token，绑定 Session、generation、任务意图、Provider/Asset、Item、目标相对路径和快照事实；no-op/无权限/不可下载不生成 Token。

Confirm：精确确认；不重新调用 search/detail；Token-first；验证 Session/context/expiry 和快照；只创建一个任务；重放不得创建第二个；不在 Confirm 中自动下载，除非提供独立明确的“确认并立即执行”POST。

## 10. 安全下载执行器

必须复用或加强现有文件系统安全模式：

- directory FD；
- `O_NOFOLLOW`；
- 路径限制在媒体根和任务临时根；
- 拒绝绝对路径、`..`、NUL、分隔符注入；
- 文件名规范化和长度上限；
- 随机临时文件；
- 临时区与正式媒体区分离；
- 禁止符号链接、硬链接欺骗和目录替换；
- publication 前后验证 device/inode/mode/owner；
- 目标存在默认拒绝，不覆盖正式文件；
- 原子 rename/publication；
- fsync 文件和父目录；
- 发布后独立确认；
- 失败/取消清理临时文件；
- outcome_unknown 不盲目重试或覆盖。

资源与内容校验：

- 全局最大大小与 Provider/Asset 更小上限；
- streamed actual-byte hard limit；
- Content-Length 仅提示；
- MIME allowlist；
- magic/signature；
- 可选 expected SHA-256；
- 始终计算实际 SHA-256；
- 空文件、截断、非法 range 拒绝；
- timeout、并发、块大小有界；
- cancellation 每个 chunk 生效；
- 日志仅 task id、错误码、字节数、耗时，不含 locator/秘密。

Resume：仅合同允许 range 时；临时文件身份、大小和快照必须匹配；范围事实精确匹配；不把 200 当作 resume；不拼接不同对象；失败不覆盖正式文件。

## 11. 下载提交、关系与索引

阶段化：

```text
temporary_complete
verified
published
database_linked
index_coordinated
durable_verified
```

要求：

- 明确事务内建立任务、Item、ItemSource、Asset identity 与本地文件关系；
- 不按标题自动绑定；
- 不修改 status/rating/review/tags/collections；
- 不覆盖 cover_path 或本地字段，除非 Preview 明确选择；
- 唯一约束和重复 Hash/路径冲突分类；
- commit 后独立 Session 验证；
- 文件发布与 DB commit 异常按实际状态分类；
- outcome_unknown 不自动重试；
- replay 不重复写文件或关系。

媒体索引：每个完成/失败/取消请求最多一次协调；已知文件变化则刷新或标记 stale；未知则标记 unusable/stale；不在事务锁内全盘扫描；复用 media operation lock、write coordination 和 index invariants；Docker recreate 后关系与索引一致。

## 12. 手动来源检查

闭环：

```text
ItemSource
→ 用户点击 Check
→ exactly one Provider detail call
→ 生成规范化 snapshot
→ 比较 metadata hash 与本地字段
→ 记录可审查结果
```

要求：仅认证 POST；GET 零网络；Provider identity 来自数据库和已激活 Package；生产为空时 UI 正常空状态；exactly one detail；不链 search/asset/download；取消传播；稳定脱敏错误；检查成功可更新 last_checked_at，但不得自动覆盖 Item；metadata_hash 仅显式 mark-checked 或确认 Apply 更新；检查结果有 TTL 并绑定当前 ItemSource；不保存原始 payload。

## 13. 元数据 Diff 与手动更新

闭环：

```text
Check
→ Field Diff Preview
→ 用户逐字段选择
→ Signed Update Plan
→ Confirm
→ Transactional Apply
```

至少支持：

```text
summary
release_date
source title
last_checked_at
metadata_hash
```

规则：

- title 默认本地所有，不能静默覆盖；
- status/rating/review/collections/media/extra/用户标签不得由 Provider 更新；
- Provider 空值不能清空本地非空值；
- 展示 old/new/source/provenance；
- 用户逐字段选择；
- no-op 不生成 Token；
- duplicate/title hints 只提示；
- Token 绑定 Item、ItemSource、Provider identity、旧值、新值、选择字段、hash、Session、generation、expiry；
- Confirm 零 Provider 调用；
- `BEGIN IMMEDIATE` 后重读全部快照；
- 任一变化返回 stale；
- 只写白名单字段；
- flush/post-check/commit 后独立 Session 证明；
- replay 返回 stale/already_applied；
- commit exception 不依据异常猜测；
- outcome_unknown 不自动重试。

## 14. 任务中心与 Web UI

至少提供：

```text
GET  /tasks
GET  /tasks/{id}
POST /tasks/{id}/start
POST /tasks/{id}/pause
POST /tasks/{id}/resume
POST /tasks/{id}/cancel
POST /tasks/{id}/retry
POST /tasks/{id}/delete-history
```

实际路径可调整，但必须：登录保护；unsafe same-origin；GET 不启动任务、不访问 Provider、不写 DB；分页与过滤；详情展示进度/错误码/时间/Item；不显示 locator、秘密、完整 external ID 或敏感路径；PRG；幂等；completed 不可 cancel 回退；retry 只对安全状态；outcome_unknown 无盲重试；删除历史精确确认且不删媒体；Jinja/HTMX 风格；中英翻译；含 Token 页面 no-store；打开页面不自动触发下一步。

## 15. 执行模型

允许轻量、可见、受控的进程内 runner：

- 仅执行用户已确认并显式 start/resume 的任务；
- 默认不周期扫描；
- 不隐藏网络活动；
- 并发数可配置且默认保守；
- 同一任务单执行者；
- shutdown 请求取消/安全暂停；
- 重启后不自动继续网络；
- 任务持久化；
- 不依赖 Celery/Redis，除非实现证明必要；
- 测试使用 fake clock/runner/synthetic stream；
- Production Provider 为空时无外部请求。

可选同步 request-driven runner、受控线程 runner或其他简单方案，以正确性、可测试性和重启安全优先，不因执行模型细节请求授权。

## 16. 配置

至少新增：

```text
TASK_MAX_CONCURRENCY
DOWNLOAD_MAX_BYTES
DOWNLOAD_CHUNK_BYTES
DOWNLOAD_TIMEOUT_SECONDS
DOWNLOAD_TEMP_RETENTION_HOURS
TASK_HISTORY_RETENTION_DAYS
```

严格类型、范围和保守默认值；非法配置启动失败；无真实 Provider 地址或秘密；Docker 保持 non-root/read-only；临时任务目录位于 `/app/data` 受控子目录或独立 volume。

## 17. 测试要求

必须覆盖：

### Schema
fresh 5；1/2/3/4→5；repeat；future；malformed；rollback；stable v1.2.0 reject Schema 5；restore v1/v2 后任务表为空。

### Task matrix
全部合法/非法转换；并发；lease；stale lease；restart recovery；cancel；retry；replay；unknown；pagination/filter；history delete。

### Download
preview zero side effects；confirm token/session/TTL/context；no arbitrary URL；no capability；one task；streamed size；MIME/magic；hash；empty/truncated；cancel；pause/resume；range mismatch；no-overwrite；duplicate；symlink/path traversal/race；fsync/rename failure；DB conflict；commit exception；post-state classification；index coordination；restart persistence；无泄漏。

### Manual update
GET zero network；check exactly once；diff determinism；selected fields only；local ownership；no-op；stale；replay；cross-session；commit failure；unknown；last_checked/hash；Confirm zero Provider。

### Security/UI
auth；same-origin；XSS；no remote resources；no locator/secret/external ID leakage；PRG；no-store；bilingual；empty production state；production 不导入 tests；页面不自动运行。

### Full

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pip check
git diff --check
```

测试不得访问真实 DNS、真实 Provider 或既有 `data/`。

## 18. Docker 验证

使用独立临时目录或 volume：production build；non-root；read-only rootfs；CapDrop ALL/CapEff0；no-new-privileges；`/login` 200 和 headers；fresh Schema 5；创建 synthetic/local task；recreate 后任务/SQLite/媒体/索引保持；遗留 running 恢复为安全状态且不自动联网；临时任务目录权限正确；完整清理。不得挂载 `/home/nsfwtrack/data/`。

## 19. 开发提交策略

允许 3–8 个逻辑提交，例如：

```text
Add Schema 5 task foundation
Add controlled download execution
Add manual source update flow
Add task center UI and integration tests
Complete v1.3.0 bundle documentation
```

全部普通线性提交；不 amend 已推送提交；不 force push；本地连续修复；完整功能和全量验证通过后普通 push；Actions 普通失败可自行修复并追加普通提交后再次 push，无需请求授权；最终无 merge commit。

## 20. 云端与验收边界

结束条件：完整功能闭环 + Full pytest + pip check + diff check + Docker smoke + GitHub Actions success + workspace only `?? data/`。

完成后报告并停止，由外部做一次整体云端 diff 复核。

本阶段不调用 Hermes、不创建 RC、不创建 v1.3.0 Tag/Release、不部署 N100、不接真实 Provider。云端复核发现普通缺陷时，下一轮允许 Codex直接修复并推送，不再拆小阶段。全部冻结后才进入 v1.3.0 RC 与唯一一次 Hermes 验收。

## 21. 最终报告

报告：起始/最终 SHA；全部逻辑提交；修改文件分类；Application 仍 1.2.0；Schema 5；Backup v2/v1-v2 restore；任务模型/状态矩阵；下载 Preview/Confirm/Execute/Resume/Cancel；文件系统与事务安全；Check/Diff/Confirm/Apply；任务中心 UI；Production catalogs 为空；无真实 Provider/Host/凭据/真实网络；focused/schema/task/download/update/security/full tests；pip/diff；Docker；Actions；自动修复提交；无 Hermes/Tag/Release/镜像/N100；最终仅 `?? data/`；data/ 未接触。

普通实现问题、环境问题和工具兼容问题由 Codex自行解决并在最终报告汇总，不得中途逐项请求授权。
