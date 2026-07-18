# Phase 5-N4C - 三类 Provider 技术研究与 Approval 草案完成摘要

## 完成状态

Phase 5-N4C 已完成本地研究、文档、范围审计和验证。本阶段仅修改授权文档，
没有实现、批准、注册或访问任何真实 Provider。

起始基线：

```text
branch: main
start: 410ef1b978782521ba492863945d59da64cf459e
application: 1.1.0
schema: 4
backup: nsfwtrack.backup.v2
production registry: EndpointRegistry(())
```

## 交付文件

新增：

```text
docs/provider-research/video-metadata.md
docs/provider-research/video-metadata-approval-draft.md
docs/provider-research/streaming-subscription.md
docs/provider-research/streaming-subscription-approval-draft.md
docs/provider-research/comic-source.md
docs/provider-research/comic-source-approval-draft.md
docs/provider-research/provider-roadmap.md
```

更新阶段状态：

```text
GOAL.md
README.md
PLAN.md
TASKS.md
REVIEW.md
CHANGELOG.md
```

共十三个授权文件，未超过十五个文件上限。未修改 `PROVIDER_CONTRACT.md` 或
`PROVIDER_APPROVAL_TEMPLATE.md`，因为 N4C 没有改变现有运行时合同或通用
Approval Validator 合同。

## 公开研究证据

| Repository | Branch | Reviewed commit | License conclusion |
|---|---|---|---|
| `lmixture/JavdBviewed` | `main` | `e26dfdf97c1a68a8f27035ecf8e982208bdc79e0` | `AGPL-3.0-only` |
| `Yuukiy/JavSP` | `master` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | root `GPL-3.0-only`; README also claims Anti-996/additional terms |
| `EWEDLCM/FnDepot` | `main` | `e565623a1797aaf40b6b376720046d9451bc6a0d` | no root license/SPDX established; subproject claim is not a root license |
| `venera-app/venera` | `master` | `a0eba914f4c2a84ac1bc925adec2baabe920b9be` | `GPL-3.0`; project states it is unmaintained |

每份研究文档记录了实际参考文件、采用的架构思路和明确拒绝的实现范围。仅采用
DTO、Capability、Parser/Operation 分层、provenance、状态机、生命周期和 fixture
测试思路；没有复制任何参考仓库实现代码。

明确拒绝：

- site-specific DOM/crawler/browser integration；
- 任意 URL/Host/Path、response-discovered authority 和 raw payload logging；
- 自动同步、重试、下载、文件系统整理或动态 import；
- JavaScript 引擎、远程 Source 安装或更新；
- 会员伪装、访问控制绕过、免登录受保护资源提取；
- 浏览器凭据/cookie 提取和跨 Provider secret 使用。

## 影视元数据研究结果

统一 DTO：

```text
VideoSearchResult
VideoDetail
VideoIdentifier
VideoPerson
VideoOrganization
VideoSeries
VideoTag
VideoRating
VideoAsset
VideoMetadataProvenance
```

Operation：

```text
search
detail
asset_list (optional, separately approved)
discover (future, not approved)
```

已定义用户字段优先、单来源不覆盖用户编辑、逐字段 provenance、缺失不删除、
空值不覆盖、标签 raw/normalized 并存、人物/组织 Provider-scoped identity、搜索
结果非详情权威、Asset 不自动解析或下载，以及稳定 Provider priority 的
deterministic merge。

## 订阅与未来播放研究结果

已分离：

```text
Subscription Catalog
-> untrusted candidate inventory

Approved Streaming Provider
-> separate production Approval and code-owned Registry entry
```

订阅 DTO：

```text
ProviderSubscription
SubscriptionRevision
SubscriptionCandidate
SubscriptionDiff
SubscriptionValidationResult
```

只使用目标中已知的订阅字段名：`id`、`name`、`baseUrl`、`group`、`enabled`、
`priority`。候选 `baseUrl` 是不可信数据，不访问、不探测、不注册；`enabled` 只
是订阅源建议；普通和 `premium` 只用于目录分组，不授予认证、订阅、播放或下载
权限。

未来播放 DTO 和 Operation：

```text
StreamingSearchResult
StreamingDetail
PlaybackGroup
PlaybackSource
PlaybackVariant
PlaybackManifest
PlaybackSegment
PlaybackError

search
detail
playback_list
playback_resolve
```

已定义 playback 与 future download 状态机、expiry/cancel/unknown、短期 Locator、
relative-reference 不扩 Host、播放不授权下载，以及 SPA/player 资源清理边界；未
实现任何播放网络或下载。

## 漫画研究结果

漫画 DTO：

```text
ComicSearchResult
ComicDetail
ComicCreator
ComicCategory
ComicTag
ComicChapter
ComicPage
ComicPageAsset
ComicReadingProgress
```

Operation：

```text
search
detail
category_list
category_items
chapter_list
page_list
asset_list
```

未来可选 auth/favorite/comment/rating/download 均保持未批准。阅读流固定为搜索或
分类、详情、章节、页面、页面资源、本地阅读进度；Comic/Chapter/Page 均使用
Provider-scoped opaque identity，Page/Asset/Locator 分离，本地进度和收藏与远程
状态分离，不自动下载整章或因远端缺失删除本地记录。

Venera 的 JavaScript Source 模型仅作 capability/DTO/lifecycle 参考。NSFWTrack
未来每个漫画来源必须是固定、审查过的 Python Adapter，不执行远程或本地来源
JavaScript，不支持远程代码更新。

## 状态与安全矩阵

三份技术研究均包含：

- Operation 状态矩阵；
- 网络副作用矩阵；
- 数据库写入矩阵；
- 权限矩阵；
- 认证矩阵；
- 错误矩阵；
- 结果不确定性矩阵。

完整区分：

```text
success
invalid_request
not_approved
not_supported
unauthorized
forbidden
not_found
rate_limited
provider_unavailable
invalid_payload
response_too_large
expired
cancelled
unknown
```

GET 页面保持零 Provider 网络和零写入；Operation 不自动串联；失败或 unknown
不猜测、不清除本地状态、不产生 partial DTO 普通成功。

## Approval 草案状态

三份 Approval 文档均明确为：

```text
draft / not approved
```

草案只包含 placeholder 和未勾选决策，没有真实 Provider Host、Endpoint、凭据、
Cookie、响应 payload、live locator 或已批准状态。草案本身不能构造 Capability、
Endpoint 或 Registry，也不能授权网络。

## 缺失输入

用户提供的订阅 JSON 和独立油猴脚本在受保护本地数据边界外不可用。因此：

- 未猜造订阅 envelope、version、类型、可选性或真实候选内容；
- 未访问任何候选 `baseUrl`；
- 未把 JavdBviewed 的公开历史脚本冒充为用户脚本；
- 未执行任何脚本；
- HLS query inheritance、segment 并发/重试/取消、TS-to-MP4 等具体行为明确
  保持 blocked，等待未来单独静态输入授权。

## 固定后续路线

```text
N4D video metadata Provider: search + detail + optional asset_list
N4E subscription catalog: refresh + parse + revision + diff + approve + disable
N4F streaming Provider: playback_list + playback_resolve + playback UI
N4G comic Provider: search + detail + chapter_list + page_list
N5 unified source search, preview, and manual import UI
N6 controlled resource save and download
N7 controlled multi-source update, sync, and recommendation
```

每个真实阶段仍需单独完整 Provider Approval 和新的正式 GOAL。Catalog candidate
Approval 不等于 runtime Provider Approval。

## 验证结果

```text
git diff --check: passed
pytest: 965 passed in 200.02s
pip check: No broken requirements found.
```

静态复核确认：

- 应用仍为 `1.1.0`；
- `CURRENT_SCHEMA_VERSION` 仍为 `4`；
- Backup 仍为 `nsfwtrack.backup.v2`；
- Production Provider Registry 仍为 `EndpointRegistry(())`；
- 没有修改 Python、测试、依赖、配置、Schema、Migration、Backup、Docker、
  Compose 或 CI；
- 没有真实 Provider、认证、播放、下载、后台任务或网络入口；
- 没有调用 Hermes；
- 没有创建 tag/Release；
- 没有部署 N100；
- 既有未跟踪 `data/` 未进入、读取、枚举、修改、暂存或提交。

## 提交门禁

唯一提交信息：

```text
Research provider integration directions
```

推送后等待 GitHub Actions `test` 与 `Docker production smoke` 均成功。
