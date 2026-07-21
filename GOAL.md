# Phase 6-R4 — Formal Release v1.3.0

## 1. 阶段目标

从已经冻结、云端复核通过且完成唯一一次 Hermes 独立验收的精确候选提交：

```text
00dbf1f4ead8411796eb417dd93a1dbeab7e5917
```

正式发布 NSFWTrack `v1.3.0`。

本阶段只执行发布状态同步、发布验证、annotated tag 和 GitHub Release，不增加功能、不重构实现、不接入真实 Provider、不发布容器镜像、不部署 N100。

严格顺序：

```text
冻结候选再确认
→ 发布文档与 CHANGELOG 同步
→ 本地完整验证
→ 普通 release commit
→ push main
→ 精确 release commit 的 main Actions 全部成功
→ 创建并推送 annotated tag v1.3.0
→ 精确 tag commit 的 tag Actions 全部成功
→ 创建非 draft、非 prerelease 的 GitHub Release
→ 验证 Release、Tag object、peeled commit 与发布提交一致
→ 最终报告并停止
```

不得跳步。

---

## 2. 已通过的发布前门禁

```text
Candidate SHA = 00dbf1f4ead8411796eb417dd93a1dbeab7e5917
Candidate commit = Freeze v1.3.0 release candidate
Cloud RC diff review = PASS
Blocking findings = 0
Hermes acceptance = PASS
Application = 1.3.0 release candidate
Latest stable = v1.2.0
Schema = 5
Backup export = nsfwtrack.backup.v2
Backup restore = v1/v2
Phase 6 = complete/frozen
Production Endpoint Registry = empty
Production Search Packages = empty
Production Search Providers = empty
Production Acquisition Registry = empty
N100 = not deployed
Published image = none
```

Hermes 因 SSH 会话寿命未独立完成一次完整 1458 项执行，但：

```text
Hermes RC invariants = 5 passed
Hermes Phase 6 focused = 45 passed
Hermes pip check = passed
Hermes git diff --check = passed
Hermes isolated Docker/security/state verification = passed
Candidate local full pytest = 1458 passed
Candidate GitHub Actions test job = success
Candidate GitHub Actions Docker production smoke = success
```

该偏差已由外部审查记录为非阻塞，不再次调用 Hermes。

---

## 3. 冻结基线

仓库：

```text
/home/nsfwtrack
```

开始前执行：

```bash
cd /home/nsfwtrack
git fetch origin main --tags
git rev-parse HEAD
git rev-parse origin/main
git status --short
git log -1 --oneline
git tag -l v1.3.0
git ls-remote --tags origin refs/tags/v1.3.0 refs/tags/v1.3.0^{}
```

必须满足：

```text
HEAD == origin/main == 00dbf1f4ead8411796eb417dd93a1dbeab7e5917
latest commit == Freeze v1.3.0 release candidate
workspace only == ?? data/
local v1.3.0 tag does not exist
remote v1.3.0 tag does not exist
GitHub v1.3.0 Release does not exist
```

若任一条件不满足，停止并报告，不继续发布。

既有目录：

```text
/home/nsfwtrack/data/
```

不得读取、枚举、进入、复制、修改、移动、删除、格式化、暂存或提交。

禁止执行：

```bash
ls data
find data
du data
tree data
stat data/*
git add data
```

所有数据库、媒体和 Docker 验证必须使用新建隔离临时目录或独立 volume。

---

## 4. 允许修改范围

本阶段不修改任何产品功能。

只允许必要的正式发布同步：

```text
CHANGELOG.md
README.md
PLAN.md
TASKS.md
REVIEW.md
GOAL.md
当前发布状态相关文档
当前发布状态相关测试断言
新增或更新的 v1.3.0 R4 formal-release invariant test
```

`app/main.py` 已经是 `1.3.0`，不得再次修改运行时版本或其他生产代码。

不得修改：

```text
app/** 业务实现
Schema / Migration
Backup 实现或格式
任务、下载、手动更新、媒体索引、事务或安全逻辑
requirements*
Dockerfile
docker-compose*
.github/workflows/**
模板、路由、i18n 或配置行为
生产 Provider / Package / Endpoint / Acquisition registry
```

若发现必须修改上述禁止范围才能发布，停止并报告。

---

## 5. 正式发布状态

发布完成后，仓库必须一致表达：

```text
Application = 1.3.0
Latest stable release = v1.3.0
Schema = 5
Backup export = nsfwtrack.backup.v2
Backup restore = v1/v2
Phase 6 = complete/frozen
Phase 6-R3 = frozen
Cloud RC diff review = PASS
Hermes acceptance = PASS
Phase 6-R4 = released
Production Endpoint Registry = empty
Production Search Packages = empty
Production Search Providers = empty
Production Acquisition Registry = empty
Real Provider/Auth/Host/Credential/Content = none
Published image = none
N100 = not deployed
```

必须保留 v1.2.0、v1.1.0 及更早版本的发布、Tag、迁移兼容性、测试和 Actions 历史证据。

不得使用全仓库盲目替换。

---

## 6. CHANGELOG 发布规则

当前顶部为：

```text
## Unreleased
```

将当前 `Unreleased` 中属于 Phase 6 / v1.3.0 的完整内容原样归档到：

```text
## [1.3.0] - 2026-07-21
```

并在文件顶部重新保留一个新的空：

```text
## Unreleased
```

要求：

- 不遗漏 Phase 6 原有条目；
- 不重复条目；
- 不改写 `[1.2.0]`、`[1.1.0]` 或更早章节；
- GitHub Release 正文必须从冻结后的 `[1.3.0]` CHANGELOG 章节生成；
- Release 正文不得包含新的、未在冻结 CHANGELOG 中记录的功能声明。

---

## 7. 发布不变量测试

新增或更新专门的 Phase 6-R4 正式发布测试，至少证明：

1. FastAPI runtime metadata 精确为 `1.3.0`；
2. Schema 精确为 `5`；
3. Backup export 为 v2，restore 接受 v1/v2；
4. production endpoint/search/acquisition catalogs 全为空；
5. Phase 6 路由矩阵和安全不变量保持；
6. README 当前 Application 与 latest stable 均为 `v1.3.0`；
7. README 指向正式 `v1.3.0` Release；
8. CHANGELOG 顶部有新的空 `Unreleased`；
9. `[1.3.0] - 2026-07-21` 章节存在；
10. `[1.2.0]` 及历史发布章节保持；
11. 文档不再把当前状态描述为“v1.3.0 candidate 尚未发布”；
12. R3、云端审查、Hermes PASS 和 R4 released 状态一致；
13. synthetic adapter 不进入生产模块；
14. 没有真实 Provider、Host、凭据或新的生产网络入口；
15. N100 仍未部署，镜像仍未发布。

允许同步旧 R3/R4 测试中的“当前文档状态”断言，但不得删除或削弱版本、Schema、Backup、空生产目录、路由或安全断言。

---

## 8. 本地验证

至少运行：

```bash
cd /home/nsfwtrack

.venv/bin/python -m pytest tests/test_phase6_r3_release_candidate.py
.venv/bin/python -m pytest <Phase 6-R4 formal release tests>
.venv/bin/python -m pytest <Phase 6 task/download/update/security focused set>
.venv/bin/python -m pytest
.venv/bin/python -m pip check
git diff --check
```

完整测试不得少于候选基线的：

```text
1458 tests
```

通常会因新增 R4 invariant test 增加测试数量。不得删除测试、跳过测试或扩大忽略范围。

测试不得访问真实 DNS、真实 Provider、真实站点或既有 `data/`。

---

## 9. 隔离 Docker 验证

使用新建隔离临时目录或独立 Docker volume，不得挂载 `/home/nsfwtrack/data/`。

至少验证：

```text
production image builds
Application = 1.3.0
fresh Schema = 5
/login = 200
security headers present
UID/GID = 10001:10001
read-only root filesystem
CapDrop ALL
CapEff = 0
no-new-privileges
/tmp tmpfs
isolated writable /app/data
production catalogs empty
SQLite integrity_check = ok
foreign_key_check = no violations
```

执行双生命周期：

1. 第一次启动并创建隔离数据库、任务和测试媒体关系；
2. 停止并 recreate；
3. 验证 Schema、SQLite、任务恢复、文件、DB link 和媒体索引一致；
4. 遗留 running 恢复为 paused 或安全状态；
5. 不自动执行网络操作；
6. Application 仍为 `1.3.0`；
7. 清理本次容器、网络、volume、镜像、凭据和临时目录。

---

## 10. Release commit

完成文档、测试和本地验证后，创建普通线性发布提交，例如：

```text
Release v1.3.0
```

要求：

- 不 amend 候选提交；
- 不 force push；
- 不创建 merge commit；
- 不包含 `data/`；
- 发布提交前工作区只能包含本阶段允许修改和 `?? data/`；
- 提交后工作区只能剩 `?? data/`。

普通 push 到 `main`。

记录精确：

```text
release commit SHA
```

---

## 11. Main Actions 门禁

push 后必须确认 GitHub Actions run 精确绑定 release commit SHA。

必须同时成功：

```text
test = success
Docker production smoke = success
```

不得只根据分支最新状态猜测。

若 main Actions 失败：

- 不创建 Tag；
- 不创建 Release；
- 分析失败；
- 仅可在正式发布范围内创建普通 corrective commit；
- 不 amend、不 force push；
- 重新执行本地验证并 push；
- 以最终通过的提交作为 release commit；
- 最终报告列出全部发布提交。

只有 main Actions 全部成功后才能创建 Tag。

---

## 12. Annotated Tag

在已经通过 main Actions 的最终 release commit 上创建 annotated tag：

```text
v1.3.0
```

Tag message：

```text
NSFWTrack v1.3.0
```

必须是 annotated tag，不得是 lightweight tag。

推送 Tag 后记录：

```text
annotated tag object SHA
peeled commit SHA
```

必须确认：

```text
peeled commit SHA == final release commit SHA
```

不得移动、删除或重建已推送 Tag。

---

## 13. Tag Actions 门禁

推送 `v1.3.0` 后，必须等待并确认该 Tag 对应的 GitHub Actions：

```text
test = success
Docker production smoke = success
```

必须确认 Tag run 实际 checkout 的 peeled release commit。

若 Tag Actions 失败：

- 不创建 GitHub Release；
- 不移动或删除 Tag；
- 停止并报告；
- 不擅自创建修复提交后移动 Tag。

只有 Tag Actions 全部成功后才能创建 GitHub Release。

---

## 14. GitHub Release

Tag Actions 全部成功后，创建：

```text
Tag: v1.3.0
Title: NSFWTrack v1.3.0
Draft: false
Prerelease: false
```

Release 正文来源：

```text
CHANGELOG.md 中冻结的 [1.3.0] - 2026-07-21 章节
```

不得：

- 自动生成未经审查的额外功能声明；
- 上传二进制或容器镜像；
- 修改 Tag；
- 将 Release 标记为 prerelease；
- 再次调用 Hermes；
- 部署 N100。

创建后验证：

```text
Release exists
Release tag_name = v1.3.0
Release target resolves to final release commit
draft = false
prerelease = false
Release body matches frozen CHANGELOG section
```

记录：

```text
GitHub Release ID
Release URL
```

---

## 15. 凭据安全

使用现有、已批准的 GitHub 发布凭据方式。

若使用 token 文件：

- 文件权限必须为 `600`；
- 只在受控子进程中读取；
- 不打印、不复制、不写入仓库；
- 不写入 shell history、日志、报告或临时明文文件；
- 使用后清理本阶段创建的临时凭据文件。

若安全凭据不可用，停止并报告，不尝试绕过。

---

## 16. 禁止事项

本阶段不得：

```text
修改产品功能
修改 Schema/Migration/Backup
修改依赖、Docker、Compose 或 CI 行为
启用真实 Provider/Auth/Host/Credential/Content
访问真实内容来源
调用 Hermes
发布容器镜像
部署 N100
读取或修改既有 data/
amend
force push
创建 merge commit
在 main Actions 成功前创建 Tag
在 tag Actions 成功前创建 Release
移动或删除已推送 Tag
```

---

## 17. 完成条件

只有全部满足才可报告正式发布完成：

```text
Application = 1.3.0
Latest stable = v1.3.0
Schema = 5
Backup = v2 / restore v1-v2
Phase 6 = complete/frozen
Cloud RC review = PASS
Hermes acceptance = PASS
R4 = released
Full pytest passed
pip check passed
git diff --check passed
Docker double-lifecycle passed
main Actions test passed
main Actions Docker production smoke passed
annotated tag v1.3.0 exists
tag peeled commit == final release commit
tag Actions test passed
tag Actions Docker production smoke passed
GitHub Release exists
Release is non-draft and non-prerelease
Release body matches frozen CHANGELOG
Production catalogs empty
No real Provider/Auth/Host/Credential/Content
No published image
No N100 deployment
Workspace only ?? data/
data/ not accessed
```

---

## 18. 最终报告

最终报告必须包含：

- 起始 candidate SHA；
- 最终 release commit SHA；
- 全部 release/corrective commits；
- 修改文件及理由；
- Application、latest stable、Schema、Backup；
- CHANGELOG 归档结果；
- Phase 6 冻结范围；
- production catalogs 空状态；
- focused/full/pip/diff 结果；
- Docker 双生命周期结果；
- main Actions run、job IDs 和精确 commit；
- annotated tag object SHA；
- peeled commit SHA；
- tag Actions run、job IDs 和精确 commit；
- GitHub Release ID、URL、draft/prerelease 状态；
- Release body 与 CHANGELOG 一致性；
- 没有再次调用 Hermes；
- 没有发布镜像；
- 没有部署 N100；
- 最终工作区仅 `?? data/`；
- `data/` 未读取、枚举、进入或修改；
- 临时容器、网络、volume、镜像、凭据和审计目录已清理。

完成后停止。不得自动开始 N100 部署或下一功能阶段。
