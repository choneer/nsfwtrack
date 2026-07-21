# Phase 6-R3 — Application 1.3.0 Release Candidate Freeze

## 1. 阶段目标

Phase 6 功能实现、集中修正和最终一致性审计已经完成。本阶段只进行 `v1.3.0` Release Candidate 冻结，不增加新功能、不重构现有实现、不接入真实 Provider。

执行顺序：

```text
冻结前基线确认
→ Application 1.2.0 更新为 1.3.0 release candidate
→ 精确同步当前版本断言与候选文档
→ 新增/更新 RC 不变量测试
→ focused + full + pip + diff 验证
→ 隔离 Docker 双生命周期验证
→ 普通线性提交并推送
→ GitHub Actions 全部成功
→ 报告精确 candidate SHA 并停止
→ 外部云端审查
→ 针对精确 candidate SHA 的唯一一次 Hermes 验收
→ 另行授权 Phase 6-R4 正式发布
```

本阶段不是正式发布，不创建 Tag/Release，不发布镜像，不部署 N100，也不调用 Hermes。

## 2. 冻结基线

```text
repository: /home/nsfwtrack
branch: main
base: 6ec824c123651a000252499f39ac8fc03b5faa31
latest stable: v1.2.0
Application: 1.2.0
Schema: 5
Backup export: nsfwtrack.backup.v2
Backup restore: v1/v2
Production Endpoint Registry: empty
Production Search Packages: empty
Production Search Providers: empty
Production Acquisition Registry: empty
Phase 6 full test evidence: 1453 passed
Phase 6 final consistency audit: PASS
```

开始前执行：

```bash
cd /home/nsfwtrack
git fetch origin main --tags
git rev-parse HEAD
git rev-parse origin/main
git status --short
git tag -l v1.3.0
```

必须满足：

```text
HEAD == origin/main == 6ec824c123651a000252499f39ac8fc03b5faa31
local v1.3.0 tag does not exist
remote v1.3.0 tag does not exist
GitHub v1.3.0 Release does not exist
```

开始前工作区只允许：

```text
?? data/
```

放入本 GOAL 后允许：

```text
M GOAL.md
?? data/
```

既有 `/home/nsfwtrack/data/` 不得读取、枚举、进入、复制、修改、移动、删除、格式化、暂存或提交。

## 3. 唯一允许的产品变化

将运行时 Application 版本从：

```text
1.2.0
```

精确更新为：

```text
1.3.0
```

当前已知运行时入口为 `app/main.py` 中 FastAPI metadata。必须先审计仓库内全部当前版本定义和可执行断言，确认不存在第二个运行时版本源。

不得使用全仓库盲目替换。必须逐项分类：

1. 当前候选版本引用，应更新为 `1.3.0`；
2. 最新稳定版本引用，必须继续为 `v1.2.0`；
3. 历史发布、历史测试、历史迁移、兼容性和 Actions 证据，必须保持原值；
4. Schema 仍为 `5`；
5. Backup 仍为 `nsfwtrack.backup.v2`，restore 仍支持 v1/v2；
6. production endpoint/package/provider/acquisition catalogs 仍为空。

## 4. 允许修改范围

只允许为 RC 冻结进行必要、最小、可审计的修改：

```text
app/main.py                       # 仅运行时版本 literal
当前版本相关测试断言
新增或更新的 v1.3.0 RC invariant tests
README.md
CHANGELOG.md
PLAN.md
TASKS.md
REVIEW.md
GOAL.md
PRODUCT_VISION.md                 # 仅当前状态确有需要时
PROVIDER_CONTRACT.md              # 仅当前状态确有需要时
其他明确包含“当前候选/当前版本”事实的发布文档
```

若发现必须修改其他文件，只有在它确实包含当前运行版本、候选状态或冻结不变量时才允许，并须在最终报告逐项解释。

不得：

- 修改 Phase 6 业务逻辑；
- 修改任务、下载、手动更新、媒体索引或事务实现；
- 修改 Schema、Migration 或 Backup 格式；
- 修改依赖、Docker、Compose、CI 行为；
- 激活 Provider、Package、Endpoint 或 Acquisition registry；
- 接入真实 Host、真实凭据、真实网络或真实内容来源；
- 放宽测试、安全、文件系统、Session、事务或并发边界；
- 删除或改写历史发布证据；
- amend 已推送提交或 force push。

## 5. 候选状态必须统一

冻结完成后，仓库当前状态必须一致表达为：

```text
Application = 1.3.0 release candidate
Latest stable release = v1.2.0
Schema = 5
Backup export = nsfwtrack.backup.v2
Backup restore = v1/v2
Phase 6 = complete/frozen
Final consistency audit = PASS
Production Endpoint Registry = empty
Production Search Packages = empty
Production Search Providers = empty
Production Acquisition Registry = empty
Real Provider/Auth/Host/Credential/Content = none
Hermes = not called in RC freeze
v1.3.0 Tag = not created
v1.3.0 Release = not created
Published image = none
N100 = not deployed
```

不得把 `v1.3.0` 描述为最新稳定版或正式 Release。

## 6. CHANGELOG 规则

本阶段保持 `Unreleased`，不得创建正式 `[1.3.0] - YYYY-MM-DD` 发布段，不填写正式发布日期。

`Unreleased` 应准确概括 Phase 6 已冻结的新增能力和安全修正，包括：

- Schema 5 持久任务模型；
- 受控下载 Preview/Confirm/Start/Pause/Resume/Cancel；
- owner/generation/expiry/cancel fencing；
- 原子并发 claim；
- 安全临时写入、校验、无覆盖发布、关系建立和媒体索引协调；
- 新 Session durable outcome verification；
- 手动来源 Check/Diff/逐字段 Confirm/Apply；
- 双语任务中心；
- production catalogs 继续为空。

不得改写已发布的 `[1.2.0]`、`[1.1.0]` 或更早章节。

## 7. RC 不变量测试

新增或更新专门的 v1.3.0 RC 测试，至少证明：

1. FastAPI runtime metadata 精确为 `1.3.0`；
2. Schema 精确为 `5`；
3. Backup export 为 v2，restore 兼容 v1/v2；
4. production endpoint/package/provider/acquisition catalogs 均为空；
5. tests-only synthetic Adapter 不会进入 production；
6. Phase 6 的 task/download/manual-update routes 与核心不变量仍存在；
7. 当前文档不把 `v1.3.0` 声称为已发布或最新稳定；
8. `v1.2.0` 历史 Release、Tag 和兼容性证据保持；
9. 不存在真实 Provider、真实 Host、真实凭据或新的生产网络入口；
10. RC 冻结没有削弱 owner/generation fencing、outcome verification、no-overwrite、Session-bound token 或 GET zero-side-effect 边界。

不得通过删除断言、扩大忽略范围、降低精确性或跳过现有测试来使冻结通过。

## 8. 验证要求

至少执行：

```bash
.venv/bin/python -m pytest <v1.3.0 RC focused tests>
.venv/bin/python -m pytest <Phase 6 task/download/update/security focused set>
.venv/bin/python -m pytest
.venv/bin/python -m pip check
git diff --check
```

完整测试不得少于当前基线所包含的测试；若测试总数变化，必须解释新增/删除原因。正常情况下只应新增 RC 不变量测试，不应删除 Phase 6 测试。

测试不得访问真实 DNS、真实 Provider、真实站点或既有 `data/`。

## 9. Docker RC 验证

使用全新隔离临时目录或 volume，不得挂载 `/home/nsfwtrack/data/`。

至少验证：

```text
production image build succeeds
Application reports 1.3.0
fresh Schema 5
/login = 200
security headers present
UID/GID = 10001:10001
read-only root filesystem
CapDrop ALL / CapEff = 0
no-new-privileges
/tmp tmpfs
isolated writable /app/data
production catalogs empty
no external network operation
```

执行双生命周期：

1. 第一次启动创建隔离数据库、任务、测试媒体/关系；
2. 停止并 recreate；
3. 验证 SQLite、Schema 5、任务恢复规则、文件、DB link 和媒体索引仍一致；
4. 遗留 running 恢复为安全状态，不自动联网；
5. Application 仍为 `1.3.0`；
6. 完整清理容器、网络、volume/image 和临时审计目录。

## 10. 提交与推送

目标为一个最小、普通、线性的 RC freeze commit，例如：

```text
Freeze v1.3.0 release candidate
```

允许在本地验证前修改；一旦推送，不 amend、不 force push。

如 GitHub Actions 因普通 RC 同步缺陷失败，可追加一个普通 corrective commit，但不得修改功能或削弱门禁。最终报告必须列出全部候选提交，并明确最终 candidate SHA。

推送后必须等待并验证当前 candidate SHA 对应的：

```text
test = success
Docker production smoke = success
```

不得只根据分支最新状态猜测，必须确认 Actions 绑定精确 candidate SHA。

## 11. 停止边界

出现以下情况必须停止并报告：

1. `HEAD` 或 `origin/main` 不等于基线 SHA；
2. 工作区除 `GOAL.md` 和既有 `?? data/` 外已有未知改动；
3. 需要读取或修改既有 `data/`；
4. 已存在本地/远程 `v1.3.0` Tag 或 GitHub Release；
5. 发现多个冲突运行时版本源，无法安全确定权威入口；
6. RC 冻结必须修改业务逻辑、Schema、Backup、依赖、Docker/CI 或安全边界；
7. 需要真实 Provider、Host、凭据或网络；
8. 需要 force push、重写历史、移动/删除 Tag/Release；
9. 测试或 Docker 暴露新的功能级阻塞缺陷，无法在纯冻结范围内修复；
10. 可能泄露秘密或用户数据。

普通版本断言同步、文档状态矛盾、RC 测试补充和隔离验证问题由 Codex 自行修复，不逐项请求授权。

## 12. 完成条件

只有同时满足以下条件才可报告 RC freeze 完成：

```text
Application = 1.3.0
Latest stable = v1.2.0
Schema = 5
Backup = v2 / restore v1-v2
Phase 6 scope frozen
Production catalogs empty
Focused tests pass
Full pytest pass
pip check pass
git diff --check pass
Docker double-lifecycle pass
GitHub Actions test pass
GitHub Actions Docker production smoke pass
No v1.3.0 tag
No v1.3.0 Release
No published image
No N100 deployment
No Hermes call
Workspace only ?? data/
data/ not accessed
```

## 13. 最终报告

报告必须包含：

- 起始 SHA 与最终 candidate SHA；
- 所有 RC freeze/corrective commit；
- 实际修改文件及每个文件的理由；
- 运行时版本入口审计结果；
- 当前候选引用与保留历史引用清单；
- Application 1.3.0、latest stable v1.2.0、Schema 5、Backup v2/v1-v2 restore；
- Phase 6 冻结范围；
- production catalogs 为空的证明；
- focused/full/pip/diff 结果；
- Docker 双生命周期结果；
- candidate SHA 对应的 Actions run/job 状态；
- 没有 Tag/Release/镜像/N100/Hermes；
- 最终工作区只剩 `?? data/`；
- `data/` 未读取、枚举、进入或修改。

完成后停止。下一步不是继续编码，而是对精确 candidate SHA 做一次云端 RC diff 复核；通过后再单独编写并执行唯一一次 Hermes 验收提示词。正式 `v1.3.0` 发布必须由用户另行授权。
