# Phase 5-N4D-D-B0 corrective fix — Repository-derived Provider Evidence Profile

## 完成摘要

Phase 5-N4D-D-B0 corrective fix 已完成本地文档修正与验证。起始基线为
`65001aeddaa9fae74acd46b6ff6b5cb95a35060f`，分支为 `main`。本轮只修改
五份授权 Markdown，没有修改生产代码、测试、配置、依赖、Registry、Outbound、
Schema、Backup、Docker、Compose 或 CI，未改变运行时行为。

应用版本保持 `1.1.0`，Schema 保持 `4`，Backup 保持
`nsfwtrack.backup.v2`，Production Registry 保持 `EndpointRegistry(())`。

## 固定证据

证据严格固定到：

```text
lmixture/JavdBviewed
8c9245726906ece8d49f553542874980512d4504

Yuukiy/JavSP
c4cfe61188234dd24c75b53b42b054327fef3e58

EWEDLCM/FnDepot
9a2449eaf012c352bca2ed4381e005a37f67d757

venera-app/venera
a0eba914f4c2a84ac1bc925adec2baabe920b9be
```

Evidence Ledger 记录了各仓库的 default branch、archived/maintenance 状态、
license/extra terms、实际采用的合同概念与明确排除项。没有 clone 或 vendor
上游代码、fixture、图片、脚本或内容。

## 文档产物

新增：

```text
docs/provider-research/repository-evidence-ledger.md
docs/provider-research/video-metadata-field-crosswalk.md
docs/provider-research/provider-operation-matrix.md
docs/provider-research/repository-derived-video-metadata-profile-v1.md
docs/provider-research/provider-production-readiness.md
```

同步更新：

```text
PLAN.md
TASKS.md
REVIEW.md
CHANGELOG.md
PROVIDER_CONTRACT.md
PROVIDER_APPROVAL_TEMPLATE.md
docs/provider-research/provider-roadmap.md
docs/provider-research/video-metadata.md
docs/provider-research/video-metadata-approval-draft.md
```

## 提取结论

- JavSP 只贡献 metadata 字段体系、source-scoped provenance、显式 priority、
  first-nonempty、missing-is-not-delete、候选资产和 required-field gate；未提取
  真实站点、Host、Endpoint、selector、crawler 或 fixture。
- JavdBviewed 只贡献本地状态、用户字段、manual edit protection、soft delete、
  sync contract 与 deterministic merge；未提取页面解析、账号、登录、下载或
  媒体搜索实现。
- FnDepot 只贡献 versioned JSON manifest、stable key、required/optional、
  explicit override、backward compatibility 和 parser-before-admission 规则；
  未采纳 download locator、路径拼接、目录发现或 manifest-driven executable。
- Venera 只贡献 source identity/version、search/detail/category/asset 分离和
  page/next-token pagination taxonomy；未使用 JavaScript runtime、remote source、
  login、Cookie、content load 或 download。

## Profile 与批准状态

四个仓库均为 `reference only`，都不是可直接激活的 Production Provider。
当前 Production Profile 只保留：

```text
search
detail
asset_list (optional)
```

`video-metadata-approval-draft.md` 继续明确为：

```text
draft
not approved
no production activation
```

任何未来真实 Provider 仍需用户单独明确批准、合法访问依据、精确固定网络事实、
稳定 response schema、脱敏 static fixture、production Approval Artifact、
code-owned Adapter，并通过 N4D-C/D-A 全部门禁。

## Corrective fix

- 修正 `VideoMetadataProvenance` 边界：当前 DTO 只有
  `provider_key`、`external_id`、`operation`、`field_name`、`observed_at`、
  `source_updated_at`、`confidence`，不包含 digest/hash 字段。metadata
  hash/digest 只属于独立来源快照、ItemSource tracking 或未来合同。
- 修正 `duration_seconds` 为 optional positive integer seconds；缺失使用
  `None`，`0`、负数、float、bool 均不合法。
- 修正 `release_date` 为无时区 strict calendar date；不执行 UTC 或时区换算，
  不附加 datetime/timezone 语义；无法无歧义解析时保持缺失或产生稳定解析错误。

## 验证结果

```text
.venv/bin/python -m pytest
1161 passed

.venv/bin/python -m pip check
No broken requirements found.

git diff --check
passed
```

提交前范围审计确认只有本文件及其余十四份授权 Markdown；没有真实内容站点
Host、Endpoint、URL、selector、response、凭据、login、download、playback、
scraper、第三方代码或 fixture。既有未跟踪 `data/` 未被读取、枚举、进入、复制、
修改、移动、删除、暂存或提交。未调用 Hermes，未创建 tag/Release，未部署 N100。

本轮使用唯一 corrective 提交信息：

```text
Correct repository metadata contract profile
```
