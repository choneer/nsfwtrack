# NSFWTrack — 项目进度与开发规划

> NSFWTrack 是 NSFW-first、local-first、privacy-first、single-user、
> self-hosted 的内容收藏、来源聚合、内容获取、状态追踪和个性化发现应用。
> 普通全年龄内容仅作为通用模型的附带兼容能力；长期定位、阶段授权能力与
> 永久禁止项以 `PRODUCT_VISION.md` 和 `RULE.md` 为准。

---

## 一、当前总体状态

当前应用版本与开发阶段：

```text
v1.1.0 stable / Phase 5-N5A Provider-neutral Search Orchestration Service locally complete
```

当前最新稳定版本为 `v1.1.0`，发布范围包含已冻结并验收完成的 Phase 3 后续媒体维护能力与 Phase 4 全部能力。

当前发布引用：

```text
annotated tag object: 07643bf6a7b36cb488c80c0ac694b6bc733e61e3
peeled commit: c1ff2760f8ee8ca988493aa04e8b4affbc4b4b9d
Release: https://github.com/choneer/nsfwtrack/releases/tag/v1.1.0
```

当前项目状态：

```text
基础可用：已完成
本地管理闭环：已完成
数据导入 / 备份闭环：已完成
合集体系：已完成
重复条目清理：已完成
元数据清理：已完成
使用效率增强：已完成
数据健康检查：F1 / F2 / F3 已发布，F4 提示行为与 K2 专项验收均已完成
设置中心：G1 基础设置中心、G6 危险操作偏好已发布
维护与迁移：Phase 2-H 已完成并随 v0.9.0 发布
稳定性收尾：Phase 2-I1 基线、I2 查询优化、I3 错误处理、I4 发布冻结审查已随 v1.0.0 发布
完成度审计：Phase 2-K1 / K2 已随 v1.0.1 发布；代码开发与 WSL 验收已完成
维护与 CI：Phase 2-L1 至 L6 已随 v1.0.2 发布；L7 已随 v1.0.3 发布；L8 固定非 root 容器用户已随 v1.0.4 发布
产品功能重启：Phase 3-A1 至 A6 已随 v1.0.5 发布；Phase 3-B1 / B2 已随 v1.0.6 发布；Phase 3-B3 / B4 / B5 / B6 / C1 / C2 / C3 / C4 / C5、D1 最终集成审查及 Phase 4-A1 / A2 / M1 / M2 / M3 / M4 / M5 均已随 v1.1.0 正式发布
正式发布：Phase 4-R1 至 R3D 的审计、验收和候选冻结均已完成，Phase 4-R4 已正式发布 `v1.1.0`
下一目标：v1.2.0 三类 Provider 路线；Phase 5-N4A/N4B 通用基础设施、N4C 静态研究、N4D-A/B/C、N4D-D-A Artifact 离线门禁、N4D-D-B0 固定仓库证据 profile 与 N5A Provider-neutral Search Orchestration Service 已完成；N4D-D-B/N4E/N4F/N4G 仍分别等待完整 Provider Approval，N5B/N5C 保持独立后续阶段
```

当前完成度估算：

```text
核心业务能力：已完成
代码发布状态：v1.1.0 已正式发布，annotated tag 与正式 GitHub Release 按发布门禁验证
当前开发状态：Phase 5-N5A 已完成 Provider-neutral、零网络零写入的 Search Orchestration Service；只接收通过现有 Package 门禁的 Video Metadata Package，operation authority 仅来自 Adapter Binding，Production Search Packages 与 Production Registry 均为空。应用仍为 `1.1.0`、Schema 为 4、Backup 为 `nsfwtrack.backup.v2`，无真实 Provider。
Phase 5-N3：Provider 合同、认证、资产、动态 Locator、受控下载 MVP、状态矩阵和批准模板已完成；仅新增/更新授权文档，未实现 Provider 或下载
Phase 5-N4A：capability/Protocol/SourceAsset/Auth 状态/typed Registry/Outbound 基础和 test-only Fixture Provider 已完成；初始全量 934 passed，最终安全复核后全量 938 passed，production registry 仍为空
Phase 5-N4B：immutable Approval/Host/Operation/Auth/Asset/Download model、纯本地一致性 Validator 与 opaque Asset ID 强化已完成；N4B 27、N4A/Adapter/Outbound 120、全量 965 passed，production registry 仍为空
Phase 5-N4C：影视元数据、订阅/未来播放、漫画三类静态研究与三份 placeholder-only Approval 草案已完成；四个公开仓库的准确 SHA/许可证/参考文件已记录，用户订阅 JSON 与独立油猴脚本缺失且未猜造，production registry 仍为空
Phase 5-N4C 验证：全量 965 passed，pip check 与 git diff --check 通过；只改授权文档
WSL 验收：已完成
N100 部署：尚未开始，等待用户明确授权
```

### Phase 5-P2：长期产品原则与路线对齐

Phase 5-P2 只调整文档，建立 `PRODUCT_VISION.md`，并明确：

- 产品长期保持 NSFW-first、local-first、privacy-first、single-user、
  self-hosted
- 任意 URL、无限制爬虫、权限绕过、凭据窃取/泄漏、隐藏网络和未经确认的
  大量写入或下载永久禁止
- Provider 认证、Provider-specific 解析、受控下载、第二 Provider、可控后台
  同步、本地推荐和可选 AI 默认拒绝，但可由未来独立 `GOAL.md` 明确授权
- TVmaze 不再是首个 Provider 路线，MediaTrack 更名与普通影视主线均已取消
- v1.2.0 改为 N3 合同与需求规划、N4 首个用户批准的 NSFW 核心 Provider、
  N5 搜索/详情/手动入库、N6 受控下载、N7 手动检查更新与安全体验收尾，
  然后进入 I1、R1 和 R2

P2 不选择或实现真实 Provider，不修改 N1/N2 代码及其历史证据。

### Phase 5-N3：核心 Provider 合同、认证与下载需求规划

N3 完成静态审计和文档规划，详细规范位于
`PROVIDER_CONTRACT.md`，逐项用户批准门禁位于
`PROVIDER_APPROVAL_TEMPLATE.md`。本阶段不选择、命名、搜索或访问真实
Provider，也不实现网络、认证、Secret Vault、Discovery、资产解析、下载、
路由、UI、Schema、Migration、Backup、依赖、Docker、Compose、CI 或后台任务。

审计记录当前事实：SourceAdapter 只有 search/detail；Endpoint Registry 只有
代码固定的 HTTPS/443、路径、参数、JSON 和大小边界；Outbound HTTP 只有固定
GET+JSON，禁止任意 URL、Host、Path、Header、Cookie、Body、Token、密码和
Locator；Schema 4 只有 ItemSource 来源身份/检查字段；Production Registry 仍
为空。现有媒体锁、目录 FD/O_NOFOLLOW、稳定身份/映射复核、no-overwrite 发布、
`BEGIN IMMEDIATE`、精确引用迁移、独立 Session 复核和 post-mutation 索引协调
仅作为 N6 的安全复用模式，不被误称为已实现下载能力。

规划合同分为 Metadata、Auth、Discovery、Asset、Download 五层，并要求 immutable
且 code-owned capability manifest；Search、Detail、Discover、Asset List、Asset
Resolve 和 Download 严格分离。认证只允许逐 Provider 批准的 `none`、`api_token`、
`oauth`、`username_password`、`session_cookie`。推荐的 Provider Secret Vault 使用
独立 `PROVIDER_SECRET_KEY` 和版本化 AEAD 信封，绑定 Provider/auth mode，拒绝
symlink/hardlink/special file，且不进入普通 backup/config export；N3 不选择依赖。

Outbound 未来只接受固定 typed method/body/auth/header/cookie/response/redirect
策略和精确 Asset Host allowlist，保留 N1 的 DNS/IP/TLS/peer、超时、大小、并发、
取消和脱敏边界。`SourceAsset` 通过 asset_list 与 asset_resolve 分离动态 Locator；
Locator 只短期存在，必须重验精确 Host、路径/query、expiry、认证绑定和全部网络
peer 事实，不得转化为任意 URL Fetch 权限。

v1.2.0 下载 MVP 限于用户主动确认的单项或有界小批次、同一请求内执行、临时隔离、
流式实际字节限制、MIME/magic/hash 校验、no-overwrite 发布、精确本地关系写入、
取消传播、独立 commit 复核和每请求一次索引协调。没有隐藏后台 worker、队列、
暂停/续传、自动重试、定时下载、启动恢复、推荐自动下载或无限批量。Auth 与
Download 状态矩阵、稳定错误、unknown/cleanup 边界和 deterministic fixture/fake
测试要求均已写入合同。

N4 交接必须由用户填写并逐项批准 Provider 身份、核心用途、法律/条款/归属、每个
Host/Endpoint、method/encoding/response/content-type/size/rate/redirect、认证
生命周期、Search/Detail/Discovery/Asset/Download 映射、动态 Locator、文件命名
和来源归属、完整故障矩阵、依赖和 Schema 影响。任何缺失信息都停止交接，Codex
不得自行推断或搜索。

### Phase 5-N4A：Provider 基础设施与 Fixture-only Reference Provider

N4A 将 N3 的 provider-neutral 合同落为基础设施，不选择或实现真实 Provider：

- `ProviderCapabilities` 按 Metadata/Auth/Discovery/Asset/Download 五层冻结，
  标准 `ProviderOperation` 与层级固定，capability 缺失以稳定错误拒绝
- `SourceMetadataAdapter`、`ProviderAuthAdapter`、`ProviderDiscoveryAdapter`、
  `ProviderAssetAdapter`、`ProviderDownloadAdapter` 为 runtime-checkable Protocol；
  旧 `SourceAdapter` 保留为 Metadata alias
- `SourceAsset` 固定 kind、opaque asset ID、MIME、size、checksum、auth/downloadable
  facts，并拒绝 URL asset ID、非 canonical MIME/hash 和不一致 checksum
- AuthMode 覆盖 none/api_token/oauth/username_password/session_cookie，AuthState
  覆盖 not_configured/configured/valid/expired/invalid/revoked/unknown；本阶段只
  定义状态和错误，不实现凭据或 Vault
- 每个 ProviderEndpoint 必须绑定同 key capabilities，Endpoint set 与 manifest
  精确一致；typed operation 固定 GET/POST、JSON/form body mapping、auth/cookie、
  response kind/content type、fixed safe headers、redirect 和 exact Asset Host
- `OutboundRequest` 不新增任何 URL/Host/Path/Method/Body/Header/Cookie/Secret 字段；
  shared client 只从 code-owned business mapping 生成请求，未实现 auth/cookie/
  non-JSON/redirect policy 在 DNS 前稳定拒绝
- test-only Reference Provider 仅位于 `tests/`，只实现 search/detail/asset_list，
  使用 `.invalid` synthetic host、静态 fixtures、Fake Resolver/Clock、MockTransport
  和 Fake Network Backend；响应不能增加 operation、Host、Locator 或 Download
- 初始 N4A 专项 17、N4A+N1 116、N2/source 46、全量 934 tests；最终安全复核后
  N4A 专项 21、全量 938 tests，`pip check` 全部通过

N4A 不实现真实认证、Secret Vault、UI、数据库入库、下载、推荐、同步或真实网络，
不修改版本、Schema、Backup、依赖、配置、Docker 或 CI。Production Provider
Registry 继续为空，真实 N4 的 Approval 门禁不因 Fixture Provider 而放宽。

### Phase 5-N4B：Provider Approval Validator 与 Asset ID 契约强化

N4B 将真实 N4 前的人工 Approval 门禁落为 machine-checkable 本地合同：

- frozen/slots `ProviderApproval`、exact-purpose Host、独立 Operation、Auth、Asset、
  Download、attribution、rate、scope 与稳定错误类型
- Approval 与 `ProviderCapabilities` / `ProviderEndpoint` 的 Provider identity、
  operation set、Host mapping、path/typed parameter、method/encoding、auth/cookie、
  response/content type、redirect、Asset Host、limit/rate/exclusion 精确比较
- Approval 只用于审查，不生成 Capability/Endpoint/Registry，不写文件/数据库，
  不访问 DNS、网络、Vault、环境变量、URL 或动态代码
- fixture scope 强制 `.invalid` Host 并禁止 activation；当前未实现 operation/policy
  返回 incomplete，Production Registry 继续为 `EndpointRegistry(())`
- `SourceAsset.asset_id` 收紧为 ASCII 字母/数字/`-_.~` opaque allowlist，拒绝
  URL/URI、绝对/相对路径、分隔符、dot segment、空白、控制和非 ASCII；
  `external_id` 兼容语义不变
- N4B 专项 27、N4A/Adapter/Outbound 回归 120、全量 965 tests、`pip check` 和
  `git diff --check` 全部通过

N4B 不选择或批准真实 Provider，不实现认证、Vault、UI、入库、Asset Resolve、
下载、推荐或同步，也不修改版本、Schema、Migration、Backup、依赖、Docker 或 CI。
真实 N4 仍需用户完整填写模板并明确批准 production-scope 合同。

### Phase 5-N4C：三类 Provider 技术研究与 Approval 草案

N4C 仅新增 `docs/provider-research/` 下七份文档并更新项目状态文档：

- 影视元数据定义 Video Search/Detail/Identifier/Person/Organization/Series/Tag/
  Rating/Asset/Provenance DTO，固定 `search`、`detail`、可选 `asset_list`，并明确
  用户字段优先、来源 provenance、缺失不删除、空值不覆盖与 deterministic merge
- 订阅方向分离 Subscription Catalog 与 Approved Streaming Provider，定义
  Subscription/Candidate/Revision/Diff/Validation DTO、用户主动 refresh/parse/diff/
  approve 流程；候选 `baseUrl` 不访问，普通/`premium` 仅为目录分组
- 在线播放只设计 PlaybackGroup/Source/Variant/Manifest/Segment、`playback_list` /
  `playback_resolve` 与 playback/download 状态机，不实现真实网络、播放或下载
- 漫画方向采用 search/category/detail/chapter/page/asset capability 与 DTO 思路，
  但固定未来来源为审查过的 Python Adapter，禁止 JavaScript 引擎和远程 Source
- 三份研究均包含 Operation、网络、数据库、权限、认证、错误和 unknown 矩阵；
  三份 Approval 均为 placeholder-only `draft / not approved`
- 公开研究快照固定为 JavdBviewed `8c924572...`、JavSP `c4cfe611...`、
  FnDepot `9a2449ea...`、Venera `a0eba914...`；只记录合同证据，不复制实现
- 用户提供的订阅 JSON 与独立油猴脚本未找到，因此 envelope/HLS/转换细节明确
  阻塞且未猜造，未访问任何候选地址或执行脚本

后续固定为 N4D 首个影视元数据 Provider、N4E 订阅目录、N4F 在线播放、N4G
漫画 Provider、N5 统一搜索/预览/手动入库、N6 受控资源保存、N7 多来源更新。
每个真实阶段仍需完整、单独、明确的 Provider Approval。
N4C 本地验证通过全量 965 tests、`pip check` 与 `git diff --check`。

### Phase 5-N4D-A：首个真实 Provider 前的 Approval 合同闭环

N4D-A 只补齐 Provider-neutral typed Approval 合同，不选择或实现真实 Provider：

- `ApprovedFixedHeader` 与 `ApprovedOperation.fixed_headers` 只允许有界、静态、
  非敏感 printable ASCII；Header name 大小写不敏感、value 大小写敏感、顺序不影响，
  Approval/runtime 增减、改名、改值均 exact mismatch
- 既有 forbidden Header、credential-like Header name 和 Bearer/Basic/Token/ApiKey
  value 全部 fail closed；固定 Header 永远不是 Auth/Vault 通道
- `ApprovedTimeoutPolicy` 精确绑定共享 `3.0` connect / `10.0` total 常量，拒绝
  bool、非有限、非正、超限和 total 小于 connect，不改变 Outbound 行为
- `ApprovedErrorMappingProfile` 当前只允许 `shared_outbound_v1`；
  `ApprovedRawPayloadRetention` 生产只允许 `discard`，`test_fixture_only` 只允许
  `test_fixture` scope，不实现生产 raw payload 持久化
- Approval format 继续为 `1`，新字段使用现有行为兼容的 deny-safe 默认值；Production
  Registry 仍为空，N4D-B 先固定 DTO/fixture/merge，N4D-C 再完成 Package 离线门禁

N4D-A 只修改 `app/source_adapters/approval.py`、其导出、合同/模板/视频草案、
阶段状态文档和 N4D-A 测试；`registry.py`、`outbound_http.py`、版本、Schema、
Backup、依赖、Docker、Compose、CI 和真实网络行为保持不变。
本地验证通过 N4D-A 专项 64、N4A/N4B/N4D-A/Adapter/Outbound 组合 211、全量
1029 tests、`pip check` 与 `git diff --check`。

### Phase 5-N4D-B：Video Metadata DTO 与 Fixture Adapter Framework（已完成）

N4D-B 新增独立的 `app/video_metadata/` Provider-neutral frozen/slots DTO、
`VideoMetadataAdapter` async Protocol、严格字段/UTC/rating/opaque asset 验证、
available-fields 与 provenance 一致性，以及不写数据库的确定性 metadata merge
plan。`tests/video_metadata_fixture_provider.py` 只读取合成静态 JSON，严格分离
search/detail/asset_list，不使用 DNS、socket、httpx 或 OutboundHttpClient。

本阶段未选择、命名或实现真实 Provider，未修改 Registry、Outbound、Schema、
Migration、Backup、依赖、Docker 或 CI；Production Registry 继续为
`EndpointRegistry(())`。专项、组合和全量验证结果以最终提交记录为准。

### Phase 5-N4D-C：Provider Package 绑定与离线激活门禁（已完成）

N4D-C 将 typed Approval、Capabilities、Endpoint、显式 Adapter Binding 和
Evidence Manifest 绑定为 frozen/slots `ProviderPackage`。离线 validator 精确校验
provider identity、display/content scope、operation、scope、Adapter Protocol 和
opaque fixture ID/SHA-256 evidence；所有 package 必须先全部通过，Registry 或
binding 才按 provider key 稳定构建，任一失败均不返回部分结果。

生产模块不读取 fixture、路径、环境或目录，不执行 Adapter operation，也不访问
网络、DNS、数据库或文件。tests-only synthetic Source/Video packages 只对明确固定的
现有 static fixtures 计算摘要；Production Registry 继续为 `EndpointRegistry(())`。
N4D-D 才允许一个完整、明确批准的真实 Video Metadata Provider package。

### Phase 5-N4D-D-A：Provider Approval Artifact v1 与离线装载门禁（已完成）

N4D-D-A 新增固定 `nsfwtrack.provider-approval` / version `1` 的 strict JSON
Artifact。bytes-only parser 在 typed object 构造前拒绝 invalid UTF-8、任意层级
duplicate key、unknown/missing field、NaN/Infinity，以及超限 depth/node/string/
array/total bytes；canonical serializer 使用稳定 key 排序、紧凑 Unicode JSON 和
单一终止 LF，并以不含 attestation 的 canonical payload 计算 SHA-256 完整性摘要。

Artifact 只携带 opaque `binding_id`。Adapter factory 只能由调用方提供的 immutable
code-owned registry 解析，不使用 importlib、entry point、环境或目录发现；全部
Artifact/attestation/typed/parity/binding metadata 门禁通过后 factory 才调用一次，
返回 Adapter 仍必须通过 N4D-C Binding/Package validation。tests-only Video Artifact
只复用六份 `.invalid` 静态 fixture；Production Registry 继续为空。N4D-D-B 才允许
一个用户明确批准的真实 Provider Artifact 与 Adapter。

### Phase 5-N4D-D-B0：Repository-derived Provider Evidence Profile（已完成）

B0 仅修改授权 Markdown，将四个用户指定仓库固定到精确 commit，
新增 Evidence Ledger、Field Crosswalk、Operation Matrix、Video Metadata
Profile v1 与 Production Readiness。JavSP/JavdBviewed 只作 metadata/local-state
合同参考，FnDepot 只作 versioned manifest 参考，Venera 只作
operation taxonomy 参考。

四者都不能直接激活 Production Provider；当前 Profile 只保留 `search`、
`detail`、可选 `asset_list`，Approval draft 仍为 `draft / not approved /
no production activation`，Production Registry 仍为 `EndpointRegistry(())`。
本地验证通过全量 `1161 passed`、`pip check` 与 `git diff --check`。

### Phase 5-N5A：Provider-neutral Search Orchestration Service（已完成）

N5A 新增 immutable/slotted `SearchProviderDescriptor`、三类独立 request、三类
immutable envelope 和 `ProviderSearchService`。Service 构造只接受 exact Package
tuple，逐个调用现有 `validate_provider_package`，只接受 Video Metadata Binding，
并从 `ProviderAdapterBinding.operations` 建立唯一 operation authority。

`search`、`detail`、`asset_list` 各自只调用对应 Adapter operation 一次；capability
缺失在调用前拒绝。返回结果必须通过 exact type、Provider identity、external ID、
query、page/page_size、bounded tuple 与 duplicate asset identity 复核。稳定、脱敏的
Service error 不保留 query、external ID、payload、Host、Path 或原始异常文本，
`asyncio.CancelledError` 原样传播。

Production Search Packages 固定为 `()`，因此 production providers 为 `()`，任意
Provider 请求稳定返回 `provider_not_available`；没有 synthetic Provider、真实
Provider、Host、Endpoint、网络、数据库、文件读写或 Registry 修改。N5B 后续只负责
search/detail empty-state 与 approved-provider UI；N5C 单独负责 signed preview 和
manual apply plan/write gate。N5A 本地门禁为 focused `33 passed`、targeted
`376 passed`、full `1194 passed`。

### Phase 5-P1：v1.2.0 外部内容源规划（历史，已由 P2 取代）

Phase 5-P1 已完成静态审计与路线设计，不包含任何功能实现。此前讨论过的
`v2.0.0` 本地媒体关系化路线已作废，不构成当前或后续阶段输入。下一目标
版本明确为向后兼容的 `v1.2.0`。

本节保留 P1 当时的技术规划证据，不再定义当前路线。其无凭据 Provider、
第二 Provider/统一搜索和 blanket non-goal 约束均由 P2 的产品原则、批准门禁
和新 N3-N7 路线取代。

### Phase 5-N2：Schema 4 来源追踪与 Backup v2

N2 已完成以下实现与本地门禁：

- `ItemSource` 新增四个 nullable 来源追踪字段，双非空 provider/external-ID
  partial unique index 使用精确 predicate；fresh Schema 4 与 3 -> 4 后结构等价
- 生产迁移链连续覆盖 1 -> 2 -> 3 -> 4；3 -> 4 使用明确 DDL、
  `BEGIN IMMEDIATE`、完整 precheck/postcheck，并验证全链失败整体 rollback
- 新导出固定为 `nsfwtrack.backup.v2`，v1 继续恢复为四字段 null；Schema 3
  在升级前仍可导出和预览显式 null 的 v2
- payload 重复、URL/identity/metadata 矛盾和本地 hard conflict 在写入前或事务
  内阻止；exact reuse 不覆盖本地 title/check/hash，legacy enrichment 不自动执行
- restore 在事务内重新分类，commit 异常后使用独立 Session 对完整相关状态
  digest 复核，区分 committed、committed-after-error、confirmed rollback 与 unknown
- migration、backup preview、restore 零网络；应用保持 1.1.0，production registry
  保持空，无 provider、搜索 UI、远程图片、凭据、后台同步或新依赖
- N2 专项 33、targeted 164、全量 917 tests、`pip check`、稳定 v1.1.0
  future-schema 拒绝与隔离 Docker 双生命周期均通过；既有 `data/` 未使用
- 实现提交 `df90473d827be86b83da4d7d8487fd852fcff35c` 已推送 main；
  Actions run `29637868492` 的 `test` 与 `Docker production smoke` 均成功

#### N2 实施前审计基线与可复用能力（历史）

- 当前应用为 `1.1.0`、Schema `3`；真实迁移注册表连续包含
  `1 -> 2 create_item_sources` 与 `2 -> 3 create_media_index`
- `ItemSource` 当前保存 `item_id`、`url`、全局唯一 `normalized_url`、可空
  `title` 与 `created_at`；`normalize_source_url()` 只接受无凭据 HTTP/HTTPS
  URL，现有书签/文本导入只解析本地输入，从不请求 URL
- `build_source_preview()` / `import_source_rows()` 已提供预览、明确确认、
  标题歧义检查、全局 URL 冲突与事务回滚，可复用其本地映射和结果摘要模式
- `Item`、`Creator`、`Tag` 已具备手动字段映射所需关系；现有 importer 在
  单一事务内按大小写不敏感规则复用或创建 Creator / Tag
- 迁移 preview 使用 SQLite `query_only` 与 authorizer，apply 使用
  `BEGIN IMMEDIATE`；未来 Schema 拒绝、连续路径、precheck / postcheck 和
  版本记录均已有框架
- 当前 JSON envelope 为 `nsfwtrack.backup.v1`；`item_sources` 已进入
  JSON / CSV / import / restore，旧备份允许缺少该可选表，restore 保持事务性
- 所有非公开路由沿用登录 session；unsafe request 沿用
  `require_same_origin`。same-origin 是请求边界，不应把签名快照描述为 CSRF
  防护
- 当前请求日志仅记录 request ID、method、route template、status、duration
  与 exception type，适合扩展为受限 provider 事件而不记录查询或响应
- runtime 依赖没有 outbound client；开发依赖已固定 `httpx2==2.5.0` 并提供
  async client 与 mock transport。P1 不改依赖；N1 只有在明确审查后才可把
  已固定 client 提升为 runtime 依赖
- CI 对 push 运行完整 pytest 与隔离 `Docker production smoke`；生产容器
  继续使用 UID/GID 10001、read-only root、无 capabilities 与
  no-new-privileges

#### Adapter 与领域 DTO

router 不得包含 provider HTTP、解析或错误映射逻辑。采用 async
`SourceAdapter` protocol，由代码注册表持有获批 adapter：

```python
class SourceAdapter(Protocol):
    key: str
    display_name: str

    async def search(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
    ) -> SourceSearchPage: ...

    async def fetch_detail(self, external_id: str) -> SourceDetail: ...
```

adapter 只返回 immutable、provider-neutral DTO：

- `SourceSearchResult`：provider key、opaque external ID、canonical URL、
  title、alternate titles、summary、release date、creators、tags、provider
  update time、result type 与 completeness
- `SourceDetail`：同一标准字段、稳定详情标识、字段可用性和可导入字段；
  不含图片字节，不保存未使用的完整原始响应
- `SourceSearchPage`：provider、原始规范化 query、page、page size、total 或
  `has_more`、results、稳定 warning/error
- provider-specific payload、HTTP status 细节和 parser 类型不得泄漏到
  router、模板、数据库核心服务或备份

`SourceAdapterRegistry`、`OutboundHttpClient`、`SourceSearchService`、
`SourceImportService`、`SourceRefreshService` 与 `SourceConflictService`
保持职责分离。adapter 不能自行创建 HTTP client，也不能绕过共享 client。

#### Outbound HTTP 安全边界

所有 adapter 只能调用一个 `OutboundHttpClient`，其实现和测试必须同时满足：

- provider、hostname、port `443`、base path 与允许的 endpoint 模板均由代码
  固定；只允许 HTTPS，不接受用户的 scheme、host、port、base URL 或任意 path
- `trust_env=False`，不读取代理环境、浏览器配置、Cookie、Token 或账号；不
  发送 `Authorization`，provider 配置也不得包含凭据
- 请求前解析并固定一个公开 IP；拒绝 loopback、private、link-local、
  multicast、reserved、unspecified 及解析为空/混合不安全结果，连接不得因
  DNS rebinding 改投其他地址
- TLS hostname verification、SNI 与 HTTP Host 始终保持 allowlisted hostname，
  不能改为固定 IP 名称或关闭证书验证
- 默认禁用 redirect；只有 provider registry 明确批准时，最多允许一次同
  scheme、同 host、同 port 且 path 仍获批的 redirect
- connect timeout `3s`、total timeout `10s`、单响应上限 `1 MiB`；流式读取
  达上限立即停止
- 发送 `Accept-Encoding: identity`，只接受预期 JSON Content-Type；意外压缩、
  非 JSON、malformed JSON 和超大 body 使用稳定错误，不返回原始响应
- query 清理后不能为空且最多 `200` 字符，单页最多 `50` 条；一次聚合最多
  `4` 个 provider，并发最多 `4`
- 不做无限或隐式重试；DNS/security rejection、timeout、401/403、404、429、
  5xx、redirect、content type、malformed JSON、oversized body 使用稳定错误类
- provider 事件日志只允许 provider key、operation、受限 status class、
  latency 与 request ID；不得记录 query、external ID、URL、response、header、
  signed snapshot 或本地条目内容

测试只能使用 `MockTransport` 或确定性 fixture，不访问真实 DNS、provider 或
互联网。具体 provider 仍需用户批准，通用 client 不授权任何真实 endpoint。

#### 页面、网络与写入状态矩阵

```text
GET  /source-search
     login; local-only render; no network; no database write
POST /source-search
     login + same-origin; bounded network read; no database write
POST /source-import/preview
     login + same-origin; one approved detail fetch; no database write
POST /source-import/apply
     login + same-origin; local database write; no network
GET  /items/{item_id}/sources
     login; local database read; no network or write
POST /items/{item_id}/sources/{source_id}/check
     login + same-origin; one approved detail fetch; no database write
POST /items/{item_id}/sources/{source_id}/update
     login + same-origin; local database write; no network
POST /items/{item_id}/sources/{source_id}/remove
     login + same-origin; local database write; no network
```

网络阶段与写入阶段不得合并：

```text
search POST
-> signed result token
-> detail/import-preview POST
-> signed immutable import snapshot
-> user selects fields
-> apply POST revalidates local conflicts under BEGIN IMMEDIATE
```

```text
check POST
-> provider detail + signed diff
-> user selects non-empty fields
-> update POST revalidates local state and applies without network
```

快照使用现有 `SECRET_KEY` 做 HMAC-SHA256，包含明确 format / purpose /
version、expiry、provider / external ID、canonical mapped fields、目标 Item
本地快照与冲突事实；验证使用恒定时间比较。快照不保存 secret、原始 provider
响应或凭据，也不能与现有媒体操作 token 混用。签名只证明应用生成的预览，
不能替代登录、same-origin、事务内本地冲突复核或 provider allowlist。

preview/check 不更新 `last_checked_at`。只有 confirmed apply，或未来明确设计的
confirmed “mark checked” 操作，才在同一事务更新 `last_checked_at` 与
`metadata_hash`。`metadata_hash` 是带格式版本的 canonical provider-neutral
detail 字段摘要，不是原始响应 hash，也不得包含未映射 payload。

#### Schema 4 与迁移

v1.2.0 采用 Schema `4`，直接向现有 `item_sources` 增加四个 nullable 字段：

- `provider_key`
- `external_id`
- `last_checked_at`
- `metadata_hash`

增加 `(provider_key, external_id)` partial unique index，仅在两列均非 null 时
生效。provider key 是代码定义的小写稳定标识；external ID 是 provider 内
opaque、区分大小写的字符串，不做猜测归一化。Schema 3 旧行迁移后四列均为
null；不创建 provider 表或持久化搜索结果缓存。

Schema `3 -> 4` 必须进入现有连续迁移 registry，preview 保持 `query_only` +
authorizer，apply 保持 `BEGIN IMMEDIATE`、备份确认、precheck、postcheck、
版本记录与全链 rollback。必须覆盖 fresh Schema 4、1 -> 2 -> 3 -> 4、稳定
v1.1.0 Schema 3 -> 4、重复 apply、缺失路径与未来版本拒绝。

稳定 `v1.1.0` 必须通过现有 future-schema preflight 拒绝 Schema 4 数据库，
不得尝试运行或降级。rollback 是停机后恢复升级前已验证的 Schema 3 SQLite
副本；不实现自动 downgrade，也不把新数据库交给旧二进制。

#### 冲突与手动字段映射

- 同 provider / external ID 已在同一 Item：复用或 no-op
- 同 provider / external ID 已属于另一 Item：hard conflict，零写入
- 同 normalized URL 已属于另一 Item：hard conflict，零写入
- 同 normalized URL 已在目标 Item 的 legacy null-provider 行：preview 必须
  展示显式 enrichment 决定；不得静默重分配或创建重复来源
- title 相似只作为 warning，不得自动判断同一条目或自动合并
- apply 在 `BEGIN IMMEDIATE` 后重新查询 provider ID、normalized URL、目标
  Item 和 Creator / Tag 冲突；签名 preview 不能替代最终查询
- provider 的空字段不能清空本地值；现有字段默认不覆盖，只有用户逐项选择
  的非空字段可写
- Creator / Tag 只做 additive 映射并必须预览；case-fold 后存在歧义时阻止
  apply，不猜测复用
- 不修改 status、rating、review、collections、media 或 extra data；不自动创建、
  更新、合并或删除 Item
- 成功、复用、跳过和冲突数量必须准确；异常 rollback，不留半写入状态
- manual check 只用已注册 `provider_key + external_id` 获取详情，绝不请求
  ItemSource 中的用户 URL 或 provider 返回的任意 URL

#### 多来源聚合

- provider 失败隔离，单个 timeout / 429 / malformed response 不使整页 500；
  页面明确展示部分成功、空结果与各 provider 稳定错误
- 提供 provider-grouped view；aggregate view 按 provider-local rank、registry
  order、external ID 做确定性 round-robin
- 仅对完全一致的 canonical URL 做视觉分组，同时保留所有 provider provenance
- provider/external ID 只在 provider 内判断唯一；title similarity 只提示
- 不持久化搜索结果，不做自动 identity 决策、跨 provider merge 或自动 import

#### 备份、恢复与兼容

v1.2.0 导出新的 `nsfwtrack.backup.v2` envelope，并继续接受 v1 备份。v2 将
四个来源追踪字段纳入 `item_sources`，但不包含搜索结果、HTTP 响应、adapter
错误或 signed snapshots。

- v1 备份恢复到 Schema 4 时，新字段按 null 处理
- v2 preview 显示来源数量、provider/external ID 与 normalized URL 冲突摘要
- payload 内重复 normalized URL 或 provider/external ID 是 validation error；
  与本地映射后完全相同的来源可复用/skip 并单独计数，指向不同 Item 或事实
  不一致的 URL / external-ID 冲突必须在 preview 阻止 restore
- restore 在单一事务内处理；任一阻塞冲突或异常必须全量 rollback
- 恢复不访问外部网络，不检查 provider 在线状态，不自动 refresh
- duplicate normalized URL 与 provider/external ID 冲突分别报告，不能统称 skipped
- v1.2.0 备份不承诺可恢复到 v1.1.0；v1.1.0 不应接受 v2 后静默丢弃元数据
- 媒体文件和可重建媒体索引继续不进入业务备份；restore 后沿用现有索引失效规则

#### P1 路线结论（已失效）

P1 当时提出的“无凭据公开 Provider -> 第二 Provider 与统一搜索 -> 手动更新”
路线和 blanket non-goal 清单不再作为开发输入。P2 已重新定义 Provider 批准
门禁、永久禁止/阶段授权分类和 N3-N7 路线；当前唯一执行顺序见本文第七节。

P1 的共享 client、DTO、状态分离、HMAC 快照、Schema/Backup 和风险控制设计
仍作为 N1/N2 与后续阶段的历史技术依据。任何具体 Provider 仍需用户明确
批准，且不得把任意 URL 能力伪装为 Adapter。

### Phase 5-N1：受控 HTTP 与 Adapter 基础（已完成）

实现范围：

- `httpx2==2.5.0` 从 development-only 提升为 runtime 直接依赖，版本不变；
  `requirements-dev.txt` 继续继承 runtime requirements，未增加其他直接依赖
- 新增 async runtime-checkable `SourceAdapter` protocol 和 frozen
  `SourceCreator`、`SourceTag`、`SourceSearchResult`、`SourceDetail`、
  `SourceSearchPage`；canonical URL 拒绝凭据、fragment、字面空白和反斜杠
- 新增 immutable `EndpointRegistry` / `ProviderEndpoint` /
  `EndpointOperation`；production registry 精确为空
- client 公共输入只包含 provider key、operation 和 typed query/external-ID/
  page/page-size，不接受 URL、host、port、base URL、path、header、proxy、
  Cookie 或 auth
- 新增稳定 `OutboundErrorCode` / `OutboundError` / `OutboundHttpError` 与递归
  immutable JSON response

Connection-bound pinning 使用 httpx2 2.5.0 与其精确依赖 httpcore2 2.5.0
顶层公开 API：

1. resolver 返回本次 A/AAAA 全部结果，空、invalid、non-global 或 mixed set
   整体拒绝
2. 每个逻辑请求新建 HTTP/1.1 pool，origin 仍为 allowlisted hostname，
   retries=0、keepalive=0
3. 自定义公开 `AsyncNetworkBackend` 只允许 pool 请求该 hostname:443，但实际
   delegate connect 使用 selected 数值 IP
4. TCP stream 的公开 `server_addr` 必须精确等于 selected IP:443
5. TLS `server_hostname`、证书 hostname verification 与 HTTP Host 保持原
   allowlisted hostname，TLS 后再次复核同一 peer
6. unexpected target、第二次 connect、unix socket、backend retry 均 fail closed

HTTP 边界：

- `trust_env=False`、proxy/auth/cookies=None；`.netrc` 与 proxy 环境不生效，
  Set-Cookie 不跨逻辑请求保留
- HTTP/1.1 only、redirect 完全禁止、无自动重试
- connect 3s、total 10s、body 1 MiB、query 200、page-size 50、global 4、
  per-provider 1
- `Accept-Encoding: identity`；非 identity encoding 拒绝
- 仅 `application/json` / `application/*+json`；逐 chunk 在复制前执行 size
  gate，完整读取后才 JSON decode；重复 object key、非有限数和递归异常拒绝，
  并按 operation 约束 object/array
- 日志只含 sanitized provider/operation/outcome/status-class/latency-bucket/
  request-id，不含 query、URL、external ID、headers、body、DNS 地址或异常文本

本地验证：

- N1 专项 `99 passed`
- release security、error handling、security headers、config 回归 `66 passed`
- `pip check` 无损坏依赖
- 隔离 Docker build/healthy/login 通过，runtime import httpx2 2.5.0、应用
  1.1.0、Schema 3、UID/GID 10001、read-only root、`CapEff=0`、
  no-new-privileges 保持
- 全部 outbound 测试只使用 fake resolver/clock、MockTransport 或 fake public
  network backend，没有真实 DNS、provider 或互联网请求
- 临时 Docker 容器、镜像、数据和上下文已清理；既有 `data/` 未接触

范围保持：未实现真实 provider、页面、路由、Schema 4、migration、backup v2、
remote image、credential、sync、background job、tag、Release、N100 或 Hermes。
下一阶段为 Phase 5-N2，需由用户正式授权。

### Phase 4-R 发布候选路线

- Phase 4-R1：已完成 Unreleased 范围、状态语义、Schema/备份、文件系统安全、UI 和测试覆盖静态审计
- Phase 4-R1D：已完成 Schema 2 → 3 用户升级/回滚说明及各阶段状态文档修正
- Phase 4-R2C1：已在候选提交 `b7c5a634ad8c2b79ced74da9dcf0247d7af06a4b` 修复目录删除预览路由并补齐真实路由回归；Actions run `29577588841` 的两个 job 均成功
- Phase 4-R2：R2.1–R2.14 已全部通过，包括真实 Schema 连续迁移、稳定版备份兼容、`785 passed`、媒体目录 HTTP 生命周期、outcome/index 故障矩阵和 Docker 双生命周期
- Phase 4-R3：应用内部版本已提升为 `1.1.0`；版本 targeted、全量 `785 passed`、`pip check`、隔离 Docker、云端 diff、Actions run `29586484449` 和 Hermes 独立验收均通过，无 corrective，Schema 保持 `3`
- Phase 4-R4：`CHANGELOG` 已归档，发布提交、annotated `v1.1.0` tag、tag Actions、正式 GitHub Release 和发布后一致性验证按门禁完成
- 当前稳定版：`v1.1.0`；Phase 4 开发和发布路线全部完成，下一目标版本需重新规划
- Phase 4 冻结已结束；Phase 5-N1/N2 后续实现与验收现已完成，当前进入
  P2 产品原则对齐；N100 未部署且仍需独立授权

### Phase 4-M3 当前实施范围

- Schema 3 只新增可删除重建的媒体索引与状态表，正式迁移路径保持 1 → 2 → 3 连续
- 增量缓存命中绑定 HMAC、完整文件身份和稳定目录映射；不可信或变化记录重新读取与哈希
- 完整验证不信任缓存内容事实，成功刷新通过单一事务原子替换，失败保留上一份完整快照
- 扫描中心只允许手动 POST 刷新；GET 零写入，没有后台线程、任务队列、定时或启动扫描
- 主要只读页面优先索引，缺失 / 失效 / 损坏时安全降级；全部写操作仍即时重验文件与引用
- 索引不进入备份恢复，恢复事务将索引标记失效；应用版本保持 1.0.6
- 最终门禁均已通过：M3 专项、迁移、核心组合、全量、pip check、Docker 持久化，以及实现提交 `cb7561f` 对应的 GitHub Actions run `29510396534`

### Phase 4-M4 当前实施范围

- 固定应用数据目录锁通过安全目录 FD 和普通私有锁文件执行跨进程互斥，拒绝 symlink、特殊对象、不安全权限、硬链接与路径替换
- 上传及全部现有媒体文件写入口、手动增量扫描和确认完整重建共享同一锁；超时在目标媒体和业务数据变化前返回 `media_busy`
- 业务事务完成后按 no-change / known / partial-known / unknown 分类处理索引，batch 每请求最多一次增量刷新
- unknown 禁止推测刷新并失效旧索引；写后刷新失败保留业务结果、标记 `post_mutation_refresh_failed` 并降级 filesystem
- 纯 cover/avatar 引用变化不触发扫描；原有文件、目录、引用、签名预览、POST 和确认复核继续作为唯一写授权依据
- 扫描中心展示手动及各类 post-mutation 来源；CI 验证容器重建前后私有锁文件、重获锁和有效协调刷新
- 保持版本 1.0.6、Schema 3、依赖、备份格式和旧 tag / Release 不变；不增加后台任务、网络、AI 或 N100 部署

### Phase 4-M5 当前实施范围

- 只允许在媒体根内管理干净的普通目录树；媒体根、默认上传目录、保留目录和不安全对象继续拒绝
- 创建使用父目录 FD 相对 mkdir；rename / move 使用 HMAC 快照、父目录身份与映射重验、manifest digest、精确引用迁移和 no-overwrite 原子目录 rename
- 删除只允许真正为空目录，并使用父目录 FD 相对 rmdir；不实现递归删除、目录合并、覆盖、跨设备复制或批量目录操作
- 所有 POST 共用 M4 跨进程锁和 `BEGIN IMMEDIATE`，独立 Session 复核 committed / rolled-back / committed-after-error / unknown 结果
- 成功目录操作最多刷新一次索引，来源为 `post_directory`；unknown 只失效索引；GET 零写入且不创建锁文件
- 保持版本 1.0.6、Schema 3、依赖、备份格式、tag / Release、N100、网络、AI、后台任务和既有 `data/` 隔离边界

云端审查修复已完成：manifest 使用明确上限和有界流式读取，rename/move
在 `BEGIN IMMEDIATE` 后执行最终快照，引用快照绑定精确对象 ID，独立
Session 精确区分 committed-after-error、rollback、mixed 和 unknown；
partial-known 与 `directory_outcome_unknown` 使用独立刷新/失效原因和提示。
corrective commit `d00d059` 及 Actions run `29557896374` 均已通过。
- 后续 corrective commit `d651d1f649972c39ce7a3bd8af44b715b9c705cd` 完成 mkdir/rmdir 后异常、安静 rollback、锁复核 unknown 和成功提示边界
- 最终 corrective commit `090eb61e10f0974bfed3f8379a7ba50a91f29207` 完成 outcome × index.status 提示矩阵、INVALIDATION_FAILED 准确提示及目录专用 stale reason
- Hermes 在代码与 Actions 完成后独立确认目录全生命周期、精确引用迁移、`last_refresh_source=post_directory`、full → incremental、每请求单次协调和 unknown 无普通成功提示
- Hermes Docker 第二生命周期保持最终目录与数据库引用，且 UID 10001、非 root、readonly root、`CapEff=0`、no-new-privileges、`/login` 200；临时容器、网络、volume 已清理，既有 `data/` 未接触
- Phase 4-M5 已完成且无代码阻塞，不再需要 corrective implementation；不创建新 tag / Release，N100 继续等待明确授权
- 本地专项 89、协调层 17、核心组合 457、全量 735 与 pip check 已通过；隔离 Docker 两个生命周期均 healthy，登录 200、锁 inode / mode / owner 持久且协调写后索引从 1 条刷新到 2 条，资源已清理
- 实现提交 `5899588` 已推送 main；Actions run `29519131776` 的 test 与 Docker production smoke 均成功

---

## 二、角色分工

- 用户：需求确认、范围审批、最终发布确认
- 开发者：编码实现、测试、Docker 验收、提交推送
- 审查者：范围、安全、结果与发布前复核

---

## 三、长期开发规则

长期规则以 `RULE.md` 为准。

每个阶段的当前目标以 `GOAL.md` 为准。

原则：

- `RULE.md` 负责长期边界
- `GOAL.md` 负责当前阶段目标
- `CHANGELOG.md` 记录版本变化
- `TASKS.md` 记录任务状态
- `REVIEW.md` 记录审查重点
- `PLAN.md` 记录总体路线和进度

---

## 四、已发布版本

### v0.1.0 — Phase 1 MVP

目标：完成项目底座。

已完成：

- FastAPI 项目结构
- SQLite / SQLAlchemy 数据模型
- Jinja2 页面与轻量原生 JavaScript 交互
- 单用户登录保护
- 条目 CRUD
- 标签管理
- 创作者管理
- 状态 / 评分 / 短评
- 本地搜索
- 基础统计
- CSV / JSON 导入
- Docker Compose
- 基础测试
- README / TASKS / REVIEW / CHANGELOG

---

### v0.2.0 — Phase 2-A 本地管理增强

目标：增强日常条目管理能力。

已完成：

- Phase 2-A1：高级筛选 / 排序 / 分页
- Phase 2-A2：批量编辑
- Phase 2-A3：条目详情页增强
- Phase 2-A4：导入增强

能力：

- 多条件筛选
- 列表排序
- 分页控制
- 当前页批量编辑
- 状态 / 标签 / 评分批量处理
- 条目详情页快速维护
- CSV / JSON 模板
- 导入预览
- 导入错误摘要

---

### v0.3.0 — Phase 2-B UI 与统计增强

目标：提升界面可用性和本地统计能力。

已完成：

- Phase 2-B1：响应式 UI / 移动端打磨
- Phase 2-B2：统计面板增强

能力：

- 移动端布局优化
- 导航与表格适配
- 状态分布统计
- 评分分布统计
- 标签排行
- 创作者排行
- 最近活动
- 数据完整度统计

---

### v0.4.0 — Phase 2-C 合集 / 清单体系

目标：新增合集 / 清单管理能力，并纳入备份导入闭环。

已完成：

- Phase 2-C1：本地合集 / 清单管理
- Phase 2-C2：合集备份 / 导入 / 导出支持

能力：

- 创建合集
- 编辑合集
- 删除合集
- 合集详情页
- 条目加入 / 移出合集
- 批量加入 / 移出合集
- 按合集筛选
- 合集统计
- JSON 备份合集
- JSON 恢复合集
- CSV 导出 / 导入合集
- 旧备份兼容

---

### v0.5.0 — Phase 2-D 数据清理与手动合并

目标：补齐本地数据质量维护能力。

已完成：

- Phase 2-D1：重复条目检测与手动合并
- Phase 2-D2：标签 / 创作者 / 合集清理与合并

能力：

- 重复条目候选检测
- 条目对比页
- 条目手动合并
- 标签重复检测
- 创作者重复检测
- 合集重复检测
- 标签手动合并
- 创作者手动合并
- 合集手动合并
- 合并时 primary 保留
- 合并时 duplicate 删除
- 关联关系转移
- 重复关联跳过
- 合集 description 冲突处理
- 合并前危险提示
- 合并前备份提示
- 合并结果摘要

安全边界：

- 不自动合并
- 不使用 AI 判断语义
- 不请求外部信息
- 不引入外部内容源
- 不删除条目
- 合并必须登录
- 合并必须 POST
- 合并必须手动确认

---

### v0.6.0 — Phase 2-E 使用效率增强

目标：减少重复操作，提高日常使用效率。

已完成：

- Phase 2-E1：保存筛选视图 / 常用视图
- Phase 2-E2：最近访问 / 最近编辑
- Phase 2-E3：快捷操作入口 / 工作台增强

能力：

- 条目列表保存当前筛选视图
- 已保存视图应用 / 更新 / 删除
- saved views JSON 备份 / 恢复兼容
- 条目详情访问记录
- 用户主动编辑记录
- 最近活动页面
- item_activity JSON 备份 / 恢复兼容
- 首页 / 工作台快捷入口
- 条目列表页快捷入口
- 快捷入口只做导航

安全边界：

- 不自动执行危险操作
- 不绕过登录
- 不绕过 POST
- 不绕过 confirm
- 不做 AI 推荐
- 不做智能分析
- 不做外部内容源
- 不做云同步
- 不做多用户共享

---

### v0.7.0 — Phase 2-F 数据健康与校验

目标：补齐本地数据健康检查、写入前校验和低风险维护能力。

已完成：

- Phase 2-F1：数据健康检查 / 本地数据自检
- Phase 2-F2：备份文件校验 / 恢复 dry-run / 导入 dry-run 增强
- Phase 2-F3：数据健康手动修复 / 低风险维护操作

能力：

- 只读数据健康检查页
- 条目基础数据检查
- 孤立关系检查
- 重复关系检查
- saved views 参数检查
- item_activity 检查
- JSON 备份文件校验
- 备份恢复 dry-run 报告
- 导入 dry-run 报告增强
- 低风险手动修复
- 孤立 / 重复关系清理
- 孤立 activity 清理
- 负数 activity 计数修正
- saved views 危险或未知参数清理

安全边界：

- 手动修复不删除 items / tags / creators / collections
- 所有修复必须登录
- 所有修复必须 POST
- 所有修复必须 confirm
- 不自动修复
- 不做一键修复全部
- 不做 AI 判断
- 不做外部内容源
- 不做云同步
- 不做多用户功能

---

### v0.8.0 — Phase 2-G 设置与安全确认

目标：提供本地基础偏好设置，并统一危险操作的安全提示与确认流程。

已完成：

- Phase 2-G1：基础设置中心
- Phase 2-G6：危险操作偏好与确认流程统一

能力：

- 默认语言、分页数量、排序字段、排序方向和首页入口
- 显式 URL 参数和 saved views 优先于默认设置
- standard / strict 危险操作确认模式
- strict 模式服务端精确验证 `CONFIRM`
- 删除、合并、备份恢复、活动清空、健康修复和设置重置统一确认
- 安全提示不可完全关闭
- 摘要 / 详细结果展示偏好
- `app_settings` JSON 备份、校验和恢复兼容
- 旧备份缺少新设置时使用安全默认值

安全边界：

- 不绕过登录、POST、浏览器确认、服务端确认或 rollback
- 结果详情设置不改变业务逻辑、数据范围或事务
- 不做一键全部删除、合并或修复
- 不做多用户、云同步、外部账号、插件或 AI 推荐
- 不做外部内容源

---

### v0.9.0 — Phase 2-H 数据库版本与迁移框架

目标：为本地 SQLite 数据库提供可审查的版本预检和显式升级框架。

已完成：

- Phase 2-H1：数据库版本记录与升级预检
- Phase 2-H2：显式迁移框架与升级 dry-run

能力：

- 内部 `schema_migrations` 版本记录
- 新数据库基线登记和旧数据库安全预检
- 高版本数据库安全拒绝启动
- 低版本数据库只提示升级，不自动迁移
- 代码内迁移注册表和连续路径解析
- 只读升级 dry-run
- 登录、POST、浏览器确认、服务端确认和备份确认
- 迁移步骤、检查和版本记录同事务提交或整链回滚

安全边界：

- 启动时只做兼容性预检，不自动执行迁移
- 升级必须由用户显式触发，升级前建议先做 JSON 备份
- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空，不虚构 `1 -> 2` 生产迁移
- 不支持 Alembic、自动降级、任意 SQL 或用户指定目标版本
- `schema_migrations` 不进入 JSON 备份或恢复

---

### v1.0.0 — Phase 2-I 稳定性与发布冻结

目标：完成本地单用户稳定版的性能、安全、兼容性和发布审查。

已完成：

- Phase 2-I1：100 / 1,000 / 10,000 条隔离性能基线
- Phase 2-I2：按需关系加载、分页收敛和查询优化
- Phase 2-I3：统一安全错误响应、request ID 和脱敏请求日志
- Phase 2-I4：登录、Session、同源写请求、输入输出、rollback 和数据库兼容性总审查

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空
- 不新增索引、表、字段、依赖或生产迁移
- 不包含外部内容源、URL 导入、爬虫、推荐、AI、云同步或多用户系统

---

### v1.0.1 — Phase 2-K 审计与边界收口

目标：归档 K1 开发完成度审计和 K2 投入使用前边界收口。

已完成：

- Phase 2-K1：实现、文档、入口、测试缺口和 F4 安全提示审计
- Phase 2-K2：本地素材路径契约与登录保护
- 全部批量写入、状态清除和关系解除的浏览器 / 服务端确认
- `.env.example` 精确占位凭据启动拒绝
- F4 双语、备份链接、确认策略和健康空状态专项测试
- 首次安装、v0.9/v1.0 升级、备份和回滚清单

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空
- 不新增业务功能、依赖、表、字段、索引或生产迁移
- 不修改 v1.0.0 或更早 tag / Release

---

### v1.0.2 — Phase 2-L 维护与 CI 稳定性

目标：发布 L1 至 L6 的依赖兼容、安全响应头和 Docker / CI 稳定性收口。

已完成：

- TestClient 兼容依赖与直接依赖版本基线，CI 增加 `pip check`
- 最小兼容浏览器安全响应头及 500 响应覆盖
- 独立生产 Docker smoke、最小只读权限与同 ref 过时运行取消
- Python 标准库镜像健康检查，CI 先等待 `healthy` 再验证 HTTP / 安全头

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`，生产迁移注册表保持为空
- 不新增业务功能、接口、数据库变化、Schema、迁移或外部集成
- 不修改 v1.0.1 或更早 tag / Release

---

### v1.0.3 — Phase 2-L7 Docker 运行时安全基线

目标：发布生产与 CI Docker 运行时最小权限收口及配套权限准备说明。

已完成：

- 只读根文件系统、`cap_drop: ALL` 与 `no-new-privileges`
- `/tmp` 64 MiB tmpfs，并保留 `/app/data` 持久化写入
- CI 同步验证实际 capabilities、挂载和可写边界
- rootful Docker 在启动前准备数据目录权限，存量安装先停机并完成可验证备份

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`，生产迁移注册表保持为空
- 不新增业务功能、依赖、数据库变化、迁移或容器用户切换
- 不修改 v1.0.2 或更早 tag / Release

---

### v1.0.4 — Phase 2-L8 固定非 root 容器用户

目标：发布固定 UID/GID 运行身份及安全的数据目录所有权迁移流程。

已完成：

- `nsfwtrack` UID/GID 固定为 `10001:10001`，应用与 HEALTHCHECK 均通过 Dockerfile `USER` 运行
- L7 只读根、零 capabilities、禁止提权、tmpfs 与最小写入边界保持不变
- CI 与 WSL 验证身份、HTTP / 安全头和 SQLite 重建持久化，Schema 保持 1
- v1.0.3 及更早部署在升级前停机、完成可验证备份，并将 data 迁移为 `10001:10001` / 0700

发布边界：

- 不修改业务逻辑、依赖、数据库、Schema、迁移、容器 UID/GID 或安全配置
- 不修改 v1.0.3 或更早 tag / Release，不部署到 N100

---

## 五、K1 审计后的项目状态

### Phase 2-K2：投入使用前边界收口

状态：已完成。

目标：只修复 K1 已确认的使用前边界和测试缺口。

必须完成：

- 收紧 `cover_path` / `avatar_path` 为真实可用的本地路径契约，禁止浏览器外部拉图
- 为所有批量写入补齐浏览器与服务端确认
- 为状态清除和关系解除建立一致的低风险 / 危险确认规则
- 拒绝 `.env.example` 中的已知密码和 Secret 占位值
- 补齐 F4 双语备份提示、确认模式和无问题空状态专项测试
- 增加首次安装、旧版本升级、备份和回滚的单一操作清单
- 运行全量测试和隔离 Docker 验收

优先级：

```text
高
```

---

### Phase 2-K3：目标部署验收（未开始，非当前开发任务）

说明：这是可选的目标主机操作验收清单，**不是**当前开发任务。
代码开发与 WSL 验收已完成至稳定版 `v1.0.5`。N100 / 目标主机部署尚未开始，
必须等待用户明确授权后才能执行。

授权后可参考的操作项：

- 在仓库外配置唯一强密码和随机 Secret
- 在目标 N100 / LAN 环境验证 build、启动、持久化、重启、登录和停止
- 使用真实浏览器完成桌面 / 移动端、JavaScript confirm 和访问记录 smoke
- 导出新 JSON 备份，先校验，再恢复到全新隔离实例并核对核心数量
- 确认只在受控局域网访问，不直接暴露公网
- 记录最终无 P0 / P1 阻断结论

当前状态：

```text
未开始 / 等待用户明确授权
```

---

### 已完成能力（不再列为剩余阶段）

#### 设置中心（v0.8.0 已发布）

目标：让常用偏好可配置。

计划：

- Phase 2-G1：基础设置中心（已完成：设置页、默认语言、默认每页数量、默认排序方式、默认首页入口）
- Phase 2-G6：危险操作偏好与确认流程统一（已完成：strict `CONFIRM`、备份提醒、结果详情和统一安全提示）

优先级：

```text
中
```

---

#### 维护与迁移（v0.9.0 已发布）

目标：提高长期升级稳定性。

发布范围：

- Phase 2-H1：数据库版本记录、旧库基线和启动结构预检（已发布）
- Phase 2-H2：显式 migration 框架、升级前备份确认、只读 dry-run 和失败整链回滚（已发布）
- Phase 2-H 发布范围已完成；当前没有虚构的 `1 -> 2` 生产迁移

优先级：

```text
中高
```

---

#### 性能与稳定性收尾

目标：为大量数据场景做收尾优化。

计划：

- Phase 2-I1：性能基线与数据库查询审查（已完成，随 v1.0.0 发布）
- Phase 2-I2：查询优化与分页收敛（已完成，随 v1.0.0 发布；未新增索引或迁移）
- Phase 2-I3：异常处理、日志与错误页面统一（已完成，随 v1.0.0 发布）
- Phase 2-I4：安全、兼容性与 v1.0.0 发布前总审查（已完成，随 v1.0.0 发布）
- 后续性能索引或大文件处理必须另行审批，且不阻塞当前本地单用户发布边界

优先级：

```text
中
```

---

## 六、历史路线归档

### v0.6.0 — Phase 2-E 使用效率增强（已完成）

已包含：

- E1：保存筛选视图 / 常用视图
- E2：最近访问 / 最近编辑
- E3：快捷操作入口 / 工作台增强

目标完成度：

```text
约 82% ~ 85%
```

---

### v0.7.0 — Phase 2-F 数据健康检查（已发布 F1 / F2 / F3）

已包含：

- 数据健康检查页（F1 已完成）
- 备份文件校验 / 恢复 dry-run / 导入 dry-run 增强（F2 已完成）
- 数据健康手动修复 / 低风险维护操作（F3 已完成）

K1 审计结论：

- F4 提示行为已存在，不再新增产品阶段；只在 K2 补齐专项验收

目标完成度：

```text
约 87% ~ 90%
```

---

### v0.8.0 — Phase 2-G 设置中心（已发布）

已包含：

- G1：基础设置中心
- 设置页
- 默认语言
- 默认排序
- 默认分页
- 默认首页视图
- JSON 备份 / 恢复兼容本地设置
- G6：危险操作偏好与确认流程统一

目标完成度：

```text
约 90% ~ 93%
```

---

### v0.9.0 — Phase 2-H 维护与迁移（已发布）

已包含：

- H1：数据库版本记录、旧库基线和启动升级预检
- H2：显式 migration 框架、连续路径解析和只读升级 dry-run
- 显式升级确认、升级前备份确认和事务失败整链回滚
- 启动时不自动迁移
- 当前 schema 版本保持 `1`，生产迁移注册表为空

目标完成度：

```text
约 93% ~ 95%
```

---

### v1.0.0 — 稳定版（已发布）

已包含：

- 性能审查
- 数据安全审查
- 全量测试审查
- Docker 验收审查
- 文档整理
- 发布说明整理
- 旧版本升级说明

目标状态：

```text
本地单用户管理系统稳定版
```

---

### v1.0.1 — 审计与边界收口（已发布）

已包含：

- K1 开发完成度审计
- K2 本地素材、确认流程和示例凭据边界收口
- F4 专项安全提示测试
- 安装、升级、备份和回滚清单

目标状态：

```text
稳定版补丁发布；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.2 — 维护与 CI 稳定性（已发布）

已包含：

- L1 / L2 测试兼容性、直接依赖版本基线和 `pip check`
- L3 最小浏览器安全响应头
- L4 / L5 / L6 Docker smoke、CI 最小权限 / concurrency 和镜像健康检查

目标状态：

```text
稳定维护版本；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.3 — Docker 运行时安全基线（已发布）

已包含：

- L7 只读根文件系统、全部 capabilities 移除和 `no-new-privileges`
- `/tmp` tmpfs、`/app/data` 持久化写入与 CI 实际边界检查
- rootful Docker 启动前数据目录权限准备及存量备份提醒

目标状态：

```text
稳定维护版本；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.4 — 固定非 root 容器用户（已发布）

已完成：

- 生产镜像创建固定 `nsfwtrack` UID/GID `10001:10001`，应用与健康检查通过 Dockerfile `USER` 以该身份运行
- CI 数据目录归 `10001:10001` 所有，并验证身份、L7 安全边界、写入边界和安全响应头
- CI 与 WSL 均验证 SQLite 创建后停止并重建容器仍持久化，Schema 保持 1
- README 记录首次安装和 v1.0.3 存量目录的停机、可验证备份、0700 权限迁移流程

边界：

- 不使用 root 启动脚本、sudo/gosu 容器入口、自动 `chown` 或 `chmod 777`
- 不修改业务代码、依赖、数据库、Schema、迁移、版本或旧 tag / Release
- 不部署到 N100

---

### Phase 3-A1 — 来源链接与本地书签导入（已随 v1.0.5 发布）

已完成：

- `item_sources` 支持一个条目多个来源，保存原 URL、规范化 URL、可选标题和创建时间
- 详情页查看 / 添加 / 确认删除来源；纯文本支持一行一 URL 和 `标题<TAB>URL`
- 使用 Python 标准库只解析用户上传的本地浏览器书签 HTML
- 批量导入先只读预览新增、重复、无效和冲突，再确认事务写入并在失败时回滚
- 多个已有条目的标题仅大小写不同或完全相同时明确标记目标歧义，预览与写入均不任意关联
- 全局规范化 URL 唯一约束，HTTP/HTTPS allowlist，无标题时生成本地可读占位标题
- JSON 备份/恢复与 CSV/JSON 条目导入导出同步来源，旧文件缺少来源表/字段仍兼容
- 真实显式 Schema 1 → 2 `create_item_sources` 迁移；旧条目和既有表不修改

网络与范围边界：

- 只保存用户提供的 URL，不请求 URL，不抓取远程标题、元数据或图片
- 不实现爬虫、adapter、自动同步、推荐、AI 或多用户能力
- 不修改 v1.0.4 tag / Release，不部署到 N100

---

### Phase 3-A2 — 本地媒体库（已随 v1.0.5 发布）

已完成：

- 安全扫描 `data/media`，跳过符号链接、非普通文件和不支持格式，并展示引用状态
- WebUI 单图 / 多图上传，限制每批 20 张和每张 10 MB，校验扩展名、MIME 与真实文件结构
- 使用 SHA-256 内容寻址和去重，上传文件保存在现有 `data/media/library`
- 上传先写同目录随机临时文件并 flush / fsync 后原子发布；批次失败回滚本批次全部临时文件和新文件
- 使用既有 `cover_path` / `avatar_path` 设置、替换和清除封面 / 头像，清除关联不删除文件
- 缺失、损坏、伪装或非法图片安全降级为空状态和 404，不导致页面 500

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、版本或旧 tag / Release
- 不请求外部 URL，不获取远程图片，不做识别、推荐、AI 或物理删除媒体
- 保持 fixed non-root、只读根、零 capability、no-new-privileges 与现有 data 挂载

---

### Phase 3-A3 — 本地媒体候选配对（已随 v1.0.5 发布）

已完成：

- 对有效且未使用的本地媒体、无封面条目和无头像创作者生成只读候选，不在 GET 或扫描时自动写入
- 使用 NFKC / casefold 精确名称与仅保留字母数字的规范化名称匹配，并支持 `cover` / `avatar` 分隔后缀限定目标类型
- 显示目标类型、匹配依据和置信等级；一媒体多目标或一目标多媒体均标记冲突并禁止应用
- 单项与当前 20 行候选页批量操作均需登录、POST、浏览器确认和服务端确认，strict 模式精确验证 `CONFIRM`
- 写入前重新扫描并拒绝陈旧、冲突、跨页、不可用或已有关系目标；批量选择在一个事务内提交或回滚
- 只填写既有 `cover_path` / `avatar_path`，不覆盖现有关系，不下载、识别、移动、重命名、覆盖或删除媒体文件

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不请求外部网络，不做 AI、图像识别、模糊相似度、自动关联、推荐或媒体物理操作
- 不部署到 N100

---

### Phase 3-A4 — 未匹配媒体快速建档（已随 v1.0.5 发布）

已完成：

- 从有效、未使用且没有 A3 配对的本地图片生成只读新条目候选；头像约定文件明确排除
- 文件名移除图片扩展名和封面约定后缀后生成默认标题，确认前可逐项编辑
- 默认标题显示无效、已有精确同名、已有规范化同名和候选间规范化同名冲突，允许编辑解决
- 单项和当前 20 行候选页批量确认均登录保护、仅 POST、浏览器与服务端确认，strict 精确验证 `CONFIRM`
- 提交时重新扫描、限制当前页、复核本地文件，并以最终标题重新检查已有与本批次冲突
- 任一陈旧、伪造、占用、标题、文件或数据库失败均拒绝整批并 rollback；成功时创建条目并设置既有路径为 `cover_path`
- 媒体文件字节和路径保持不变，不创建、下载、识别、移动、重命名、覆盖或删除文件

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不请求外部网络，不做 AI、图像识别、自动建档、推荐或媒体物理操作
- 不部署到 N100

---

### Phase 3-A5 — 媒体库检索与分页（已随 v1.0.5 发布）

已完成：

- 对完整媒体扫描结果按文件名 / 相对路径做 NFKC 大小写无关本地搜索
- 支持全部、可用、损坏 / 不可用、已使用、未使用状态筛选；使用状态来自现有封面 / 头像引用
- 支持文件名升降序和文件大小升降序，使用文件名 / 路径稳定打破并列
- 媒体卡片固定每页 20 条，非法、负数、非数字和越界页码安全回退或夹取
- `media_page`、`match_page`、`create_page` 与规范化后的 `media_q` / `media_status` / `media_sort` 在三套分页和返回媒体库的表单间保留
- 空扫描与筛选空结果分别显示；非法搜索、状态和排序参数安全回退，GET 零写入
- A3/A4 继续接收完整原始扫描，候选生成和确认逻辑未改变

范围边界：

- 不修改媒体文件或关联，不新增写操作，不请求外部网络，不使用 AI / 图像识别
- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不部署到 N100

---

### Phase 3-A6 — 本地媒体完整性审计（已随 v1.0.5 发布）

已完成：

- `/data-health` 增加 media 分类，审计条目封面和创作者头像的本地引用
- 将非法路径、路径越界、符号链接、缺失、损坏及不可用媒体根报告为问题
- 将 `.upload-*.tmp` 残留、不同路径 SHA-256 重复内容及扫描跳过项报告为警告
- 缺失根目录仅在存在有效本地引用时报告；正常未使用媒体不视为问题
- 使用既有全局 200 条明细限制，完整分类和问题总数不被截断
- 页面 GET、扫描和报告零写入；media 问题不提供任何修复、删除或引用清除入口
- 异常根目录安全降级，不请求外部 URL，不影响 A3/A4/A5 逻辑

范围边界：

- 不修改媒体文件或数据库引用，不增加 media fix type
- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 配置
- 不请求外部网络，不部署到 N100

---

### v1.0.5 — Phase 3-A1 至 A6（已正式发布）

发布范围：

- A1 来源链接、本地文本 / 书签导入和真实 Schema 1 → 2 显式迁移
- A2 本地媒体库、安全上传、SHA-256 去重和封面 / 头像关联
- A3 确定性媒体候选与手动确认关联
- A4 未匹配本地媒体手动确认建档
- A5 媒体搜索、筛选、排序和分页
- A6 `/data-health` 只读媒体完整性审计
- 来源同名歧义拒绝与媒体同目录临时文件、fsync、原子发布、竞态复核和批次回滚修复

发布结果与边界：

- 应用元数据统一为 1.0.5，CHANGELOG 冻结到 `2026-07-13` 并保留空 Unreleased
- 不修改功能、Schema 2、既有 1 → 2 迁移、依赖或 Docker 配置
- annotated tag object 为 `6a4def572e100198a446ad56353400138c573f66`
- peeled commit 为 `3c4fee62891ff2826f0b8bc97b33bf3a4d08aa73`
- 正式 Release 为 `https://github.com/choneer/nsfwtrack/releases/tag/v1.0.5`
- 不部署到 N100

---

### Phase 3-B1 — 重复媒体定位（已随 v1.0.6 发布）

已完成：

- 仅将不同路径下、可用且具有相同完整合法 SHA-256 的媒体构成重复组
- 媒体库汇总重复组数、涉及文件数，以及每组保留一份时可节省的字节数
- `media_status=duplicate` 只显示重复组成员；损坏、空 / 非法哈希和单文件不进入
- `media_q` 保留文件名与路径搜索，并支持大小写无关的完整 SHA-256 或前缀搜索
- 重复媒体卡片显示稳定的组内数量和其他媒体路径，原有四种排序与 20 条分页保持
- 三套页码及查询状态在分页、上传、关联、A3 配对与 A4 建档返回流程中继续保留
- GET 前后数据库、封面 / 头像引用、媒体字节及 A3/A4 候选保持不变
- 中英文、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试同步

范围边界：

- 只读定位，不删除、移动、重命名、覆盖媒体或自动迁移任何引用
- 不修改 A3/A4 候选逻辑，不新增表，不修改 Schema 2、迁移、依赖、版本或 Docker
- 不请求外部网络，不使用 AI / 图像识别，不创建 tag / Release，不部署到 N100

---

### Phase 3-B2 — 重复媒体组视图（已随 v1.0.6 发布）

已完成：

- 新增登录保护的只读 `/media-library/duplicates`，每个真实重复 SHA-256 只显示一组
- B1 与 B2 共用完整合法 SHA-256、不同路径去重和稳定成员排序服务
- 每组展示完整 SHA-256、成员数、单文件大小、总占用和可节省空间
- 每个成员展示媒体路径、可用状态、条目封面引用和创作者头像引用
- 支持文件名、路径和 SHA-256 前缀搜索，以及成员数 / 可节省空间 / SHA 双向稳定排序
- 每页固定 20 组，非法超长搜索、排序和页码安全回退或夹取
- 每组提供完整 SHA 与 `media_status=duplicate` 的 B1 精确筛选链接
- GET 前后数据库、引用、媒体字节及 A3/A4 候选不变；页面无业务 POST

范围边界：

- 不删除、移动、重命名或覆盖媒体，不迁移引用，不建议自动保留项
- 不改变 B1、A3/A4 行为，不新增表，不修改 Schema 2、迁移、依赖、版本或 Docker
- 不请求外部网络，不使用 AI / 图像识别，不创建 tag / Release，不部署到 N100

---

### v1.0.6 — Phase 3-B1 与 B2（已正式发布）

发布范围：

- B1 完整 SHA-256 重复媒体定位、统计、duplicate 筛选、SHA 搜索和同组路径
- B2 登录保护的只读重复组页、组指标、成员引用、搜索排序分页和 B1 精确链接
- B1 / B2 共用同一有效媒体完整 SHA-256 分组边界

发布边界：

- 只读展示，不删除、移动、重命名、覆盖或自动选择媒体
- 不清除或迁移封面 / 头像引用，不改变 A3/A4 候选逻辑
- 不修改 Schema 2、真实 1 → 2 迁移、依赖或 Docker/CI 安全配置
- 不请求外部网络，不使用 AI / 图像识别，不部署到 N100
- annotated tag object 为 `d4d5c31cd5b2fed9a90ad69742d54b4c9dbed0b4`
- peeled commit 为 `961a3d0cc169e82b261d83207b0ec802007e292b`
- 正式 Release 为 `https://github.com/choneer/nsfwtrack/releases/tag/v1.0.6`

发布验收：

- 全量 441 passed，`pip check` 无依赖冲突
- 隔离 Docker 双生命周期均 healthy、`/login` 200、应用版本 1.0.6、Schema 2
- 容器重建前后 SQLite 文件校验和不变，fixed non-root 与只读根保持
- 临时容器、镜像、凭据和数据已清理

---

### Phase 3-B3 — 重复媒体手动整理（Unreleased）

目标：

- 在 B2 重复组页要求用户明确选择唯一 keeper，不预选、不评分、不推荐
- 使用共享 B1/B2 完整合法 SHA-256 分组边界生成只读 GET 预览
- 预览逐路径列出条目封面、创作者头像迁移、待删除文件和预计释放空间
- POST 复用 standard / strict 危险确认并在提交时重新扫描完整组
- 删除前创建同文件系统已验证安全锚点，并在完整删除窗口让组内引用指向锚点
- 删除结束后将引用提交到仍有效的 keeper、无覆盖恢复的原路径或唯一恢复路径
- 删除失败时保留安全副本、报告路径与原因，并允许重新预览后重试

拒绝边界：

- 组成员扩张或缩减、哈希变化、缺失、损坏、符号链接、路径越界和伪造路径全部拒绝
- keeper 在首删前、删除中途或末次删除期间缺失 / 替换时，始终由锚点保留一份有效同哈希内容
- 原路径缺失时只做无覆盖恢复；路径被占用时不覆盖外部文件，改用唯一验证恢复路径
- 成功、异常和删除失败重试均清理临时锚点；无法清理时保留安全副本并明确报告
- 不删除 keeper，不处理其他重复组，不自动批量整理
- 不改变 A3/A4 候选逻辑，不请求网络，不使用 AI / 图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI 配置
- 不创建 tag / Release，不部署到 N100

---

### Phase 3-B4 — 媒体清理恢复中心（Unreleased）

目标：

- 新增登录保护、只读的 `/media-library/recovery`
- 仅按大小写敏感 basename 前缀识别 `.cleanup-anchor-*` 与 `recovered-*`
- 展示路径、实际字节、完整 SHA、合法性及条目封面 / 创作者头像引用
- 区分已引用、未引用、损坏安全锚点和正常恢复文件
- 支持路径 / SHA 搜索、状态筛选、稳定排序和每页 20 条
- 在 data-health 报告锚点残留、损坏和引用状态

隔离边界：

- 默认媒体扫描静默排除内部锚点，只有恢复中心与 data-health 使用显式内部扫描
- 锚点不进入普通媒体库、B1/B2、上传去重或 A3/A4 候选
- `recovered-*` 保持正常媒体身份，继续参与普通筛选、重复组和候选流程
- 目录前缀和仅在名称中包含关键字的普通文件不误判，非锚点候选 ID 不变
- 恢复中心与 data-health GET 零写入；B5 / B6 写操作仅通过各自独立预览和确认 POST，不提供移动、改名或自动修复
- 不改变 B1/B2 分组语义和 B3 整理流程，不请求网络，不使用 AI / 图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag 或 Release

---

### Phase 3-B5 — 安全锚点手动恢复（Unreleased）

目标：

- 在恢复中心为每个合法 cleanup anchor 提供独立、零写入 GET 预览
- 展示完整 SHA、路径、device、inode、size、mtime、ctime、全部引用和后果
- POST 复用 standard / strict 危险确认，并重新扫描核对完整身份快照
- 无覆盖发布唯一 `recovered-*`，完成文件与目录 fsync
- 单事务迁移全部封面 / 头像引用，再在零引用复核后身份删除原锚点

安全边界：

- 每次只恢复一个明确选择的合法锚点，不批量恢复、不直接丢弃内容
- 损坏、符号链接、错误扩展、缺失、陈旧、伪造、变化、普通与 `recovered-*` 请求全部拒绝
- 数据库失败整笔回滚，并身份清理本次新建恢复文件；原锚点不删除
- 原锚点删除失败时不回退已安全提交的引用，引用保持在合法同 SHA 恢复文件并报告残留
- 普通交互式封面 / 头像写入不能新建内部锚点引用；既有引用、备份恢复和 B3 内部流程保持兼容
- 不改变 B1/B2/A3/A4、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-B6 — 无引用安全锚点手动清理（Unreleased）

目标：

- 仅为合法且零引用 cleanup anchor 提供单项永久删除预览
- GET 展示路径、完整 SHA、MIME、size、device、inode、mtime、ctime 和不可撤销后果
- POST 复用 standard / strict 确认，并重扫核对完整身份快照
- 使用 SQLite `BEGIN IMMEDIATE` 锁内复核封面和头像引用均为零
- 最终身份验证后只删除目标并 fsync 目录

安全边界：

- 已引用、损坏、符号链接、错误扩展、普通、`recovered-*`、缺失、陈旧、伪造和变化请求全部拒绝
- 引用竞态在写锁内拒绝，不删除文件，不迁移、清除或修改任何数据库引用
- 删除失败保留目标并明确报告；unlink 已完成但目录同步失败时准确报告已移除警告
- 不创建恢复文件，不批量或自动清理，不操作任何其他锚点或普通媒体
- 不改变 B3/B4/B5、B1/B2/A3/A4、备份、Data Health fix、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C1 — 断裂媒体引用手动修复（Unreleased）

目标：

- 从 Data Health 为缺失、损坏、符号链接、非法 / 越界路径和损坏锚点引用提供登录保护的单项预览
- GET 展示对象、原引用、问题类型、对象快照与后果并保持数据库和文件零写入
- 只允许用户手动选择一个现有合法媒体替换，或明确清除当前单个引用
- 替代媒体按路径 / SHA 搜索、稳定路径排序并固定每页 20 条
- POST 复用 standard / strict 确认，在写锁内重验后条件更新一个 `cover_path` 或 `avatar_path`

安全边界：

- 候选必须是完整验证通过的普通媒体；`recovered-*` 可用，cleanup anchor 永远禁止作为新引用
- 提交时重验对象快照、原引用、当前问题及替代媒体 SHA / size / device / inode / mtime / ctime
- 对象、引用、问题或文件变化，健康对象、陈旧和伪造请求全部拒绝
- 替换身份在条件更新后再次验证；DB / commit 失败整笔回滚
- 不自动推荐、自动清除、批量修复或处理其他健康问题
- 不修改、删除、移动或重命名任何文件，不请求网络，不使用 AI / 图像识别
- 不改变 B3-B6、媒体库、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C2 — 上传残留文件手动清理（Unreleased）

目标：

- 从 Data Health 为 `media_upload_residue` 提供登录保护的单项删除预览
- GET 展示相对路径、size、device、inode、mtime、ctime、当前引用与不可撤销后果
- GET 保持数据库和文件零写入，且不读取、解析、恢复或复制临时文件内容
- POST 复用 standard / strict 确认，只处理用户明确选择的一个目标
- 在 SQLite `BEGIN IMMEDIATE` 写锁内复核封面和头像引用均为零
- 最终完整身份验证后按目录 fd unlink 目标并 fsync 所在目录

安全边界：

- 仅接受 basename 大小写精确匹配 `.upload-*.tmp` 的普通非符号链接文件
- 空中段、近似名称、目录、符号链接、非法 / 越界路径、缺失、陈旧、伪造和同路径替换全部拒绝
- 已引用目标只显示 C1 修复指引，不提供删除表单；引用新增竞态在写锁内拒绝
- 不迁移、清除或修改任何数据库引用，不创建 `recovered-*`，不触碰其他文件
- unlink 失败时文件和数据库不变；unlink 成功但目录 fsync 失败时明确报告已删除警告
- 不自动或批量清理，不请求网络，不使用 AI / 图像识别
- 不改变 C1、B3-B6、上传、Data Health、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C3 — 媒体扫描跳过项定位中心（Unreleased）

目标：

- 为普通媒体扫描增加确定性、去重且稳定排序的逐项 skip 记录
- 区分 `symlink`、`unsupported_extension`、`special_file`、`directory_unreadable` 和 `entry_error`
- 展示安全相对路径、扩展名及可安全取得的 size / device / inode / mtime / ctime
- 新增登录保护的只读 `/media-library/skipped` 页面
- 支持路径搜索、类型筛选、稳定路径 / 类型排序和固定每页 20 条
- Data Health 两个原扫描跳过汇总告警链接到对应筛选结果

安全边界：

- 目录通过 fd 和 `O_DIRECTORY|O_NOFOLLOW` 遍历；符号链接只做 lstat，目录替换竞态也不进入目标
- 媒体候选保存根目录、逐级父目录与文件的 dev / inode / size / mtime / ctime；读取时从根 fd 逐段重开并复核
- 最终文件只通过父目录 fd 与 `O_NOFOLLOW` 打开；读取后再次验证全部 fd 与当前路径映射，通过后才解析和哈希
- 父目录替换成 symlink、文件替换或身份漂移统一安全记录为 `entry_error`，不读取外部替换内容且不进入媒体列表
- 不打开、读取、解析、验证或哈希任何被跳过文件内容
- 单个目录 / 条目错误生成稳定原因并继续扫描其他兄弟项
- 只显示媒体根下安全转义的相对路径，不保留绝对路径、原始 OSError 或敏感信息
- `skipped_symlinks` 等于 symlink 明细数；`skipped_unsupported` 等于其他四类明细总数
- 页面无 POST、删除、移动、改名、恢复、关联、自动处理或网络请求
- 不改变 A3-A6、B1-B6、C1-C2、普通媒体、cleanup anchor、`recovered-*`、上传残留、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

验收证据：

- C3 专项已扩展到 `10 passed`，新增子目录 fd 打开后父路径 symlink 替换及同 inode 身份漂移的零读取 / 零哈希覆盖
- A3-A6、B1-B6、C1-C2、媒体库、上传、Data Health、备份与导入组合回归 `263 passed`
- 全量 `540 passed`，`pip check` 无依赖冲突
- 隔离 Docker image build 通过，Compose healthy，`/login` 200，未登录跳过项页 303，down 清理完成
- 功能提交 `c591ca4` 已推送 main，Actions run `29321642902` 的 test / Docker production smoke 均通过
- 父路径竞态修复提交 `c27676f` 已推送 main，Actions run `29332762558` 的 test / Docker production smoke 均通过

---

### Phase 3-C4 — 损坏媒体文件手动清理（Unreleased）

目标：

- Data Health 和媒体库为允许扩展名、普通非符号链接的损坏媒体提供单项预览入口
- GET 展示安全路径、原始 SHA、size、device、inode、mtime、ctime、引用与永久删除后果，保持零写入
- 已引用目标只显示 C1 修复指引，不显示删除表单
- POST 复用 standard / strict 确认，并重验原始 SHA、损坏状态和完整身份
- `BEGIN IMMEDIATE` 内重新确认封面与头像引用均为零，再按目录 fd unlink 并 fsync

安全边界：

- 只处理 Data Health 当前报告的单个损坏普通媒体；`recovered-*` 仍按普通媒体处理
- 有效媒体、cleanup anchor、上传残留、symlink、unsupported / special / entry-error 跳过项均排除
- 内容读取复用 C3 已验证 FD 链，不通过可重解析的 `Path.stat/read_bytes` 打开目标
- 父路径 / 同路径 / symlink 替换、SHA 或任一身份字段变化、文件变为有效图片均在 unlink 前拒绝
- 写锁内新增引用时拒绝；不迁移、清除或改写任何引用
- unlink 失败保留目标；unlink 成功但目录 fsync 失败时准确报告已删除警告
- 不创建恢复副本，不触碰其他媒体，不自动、批量或定时清理
- 不改变版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

验收证据：

- C4 专项 `17 passed`，覆盖双入口、零写入、排除项、standard / strict、完整身份与 SHA、父路径 / symlink / 有效图片替换、引用竞态及锁 / 查询 / unlink / fsync 失败
- B3-B6、C1-C3、媒体库、上传、恢复、Data Health、备份与导入组合回归 `280 passed`
- 全量 `557 passed`，`pip check` 无依赖冲突
- Docker image build 通过，Compose healthy，`/login` 200，down 后容器与网络清理完成
- 功能提交 `1e686f3` 已推送 main，Actions run `29336790587` 的 test / Docker production smoke 均通过

---

### Phase 3-C5 — 媒体根目录诊断与安全初始化（Unreleased）

目标：

- 为 `media_root_unavailable` 增加登录保护的只读诊断入口
- 仅展示逻辑 `/media/`、安全状态、父 / 根身份、封面 / 头像引用数和处理后果
- 仅真实 missing 且父链安全时提供手动初始化
- POST 复用 standard / strict 确认，从工作目录 FD 安全打开父链并原子创建最后一级目录
- 创建后 fsync 新目录与父目录，根问题消失，断裂引用继续由 C1 处理

安全边界：

- GET 不写数据库或文件系统，不展示绝对路径、原始异常、UID 或敏感挂载信息
- 父链逐段使用 `O_DIRECTORY|O_NOFOLLOW`，重验完整身份和当前名称映射
- symlink、not_directory、unreadable、scan_failed、ready、危险配置和父目录缺失均无初始化表单
- 目标抢占、symlink 竞态、父目录替换、身份变化、伪造快照和 mkdir 失败均拒绝
- 只调用一次 `mkdir(dir_fd=...)` 创建配置末级，不递归创建、覆盖、移动、chmod 或 chown
- 不修改引用，不创建、恢复、复制或下载媒体文件；不自动或批量处理
- 不改变版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

当前验证：

- C5 专项 `16 passed`，覆盖零写入、状态隔离、standard / strict、父链 / 目标竞态、mkdir 期间父路径替换及 fsync 失败
- C1-C4、上传、扫描、Data Health、恢复、备份校验与导入组合回归 `240 passed`
- 全量 `573 passed`，`pip check` 无依赖冲突
- Docker image build、Compose healthy、`/login` 200 与 down 清理通过
- 独立非 root / read-only 容器在 named volume 内完成 missing 初始化；容器重建后空目录保持，诊断返回 root available 且不再提供初始化表单，临时资源已清理
- 功能提交 `9a3a546` 已推送 main，Actions run `29343264820` 的 test / Docker production smoke 均通过
- C4 指定组合回归文档已从 281 更正为 280

---

### Phase 3-D1 — Unreleased 集成总审查与开发冻结

目标：

- 对 B3-B6 与 C1-C5 的路由、服务、模板、导航和状态闭环做最终审查
- 为每类 Data Health finding 核对直接入口、安全拒绝或明确只读说明
- 核对 GET 零写入以及写操作登录、确认、事务、身份、引用和失败报告
- 验证备份、导入、Schema 2、设置、i18n、Docker 与 CI 无回归

确认修复：

- Data Health 根目录、未扫描引用和上传残留不再独立按可替换路径遍历，统一使用 `O_NOFOLLOW` 目录 fd 或 C3 已验证扫描记录
- `media_duplicate_content` 现在按完整 SHA-256 直接进入唯一 B2 重复组
- 认证媒体响应在验证 fd 链内读取并直接返回受限字节，不再验证路径后由 `FileResponse` 二次打开
- B3-B6 的验证、锚点创建、恢复发布和身份删除保留根 / 父目录 fd 身份并复核当前映射
- create 最终返回的新锚点与 publish 最终返回前的刷新锚点 / 目标均绑定原 root、逻辑父路径和逐级目录类型 / dev / inode 身份链，并再次复核当前映射
- C2 保留上传残留父目录链身份，在 unlink 前复核父链和最终文件映射
- 父目录改名并替换为外部 symlink，或替换为含同 inode 硬链接的普通外部目录等注入竞态均安全拒绝，不读写或删除外部目录项

当前验证：

- 19 个 B3-C5/Data Health 相关路由全部包含登录依赖
- 110 个注册路由与 142 个模板字面量链接静态核对，缺失目标为 0
- 最终 create / publish 精确竞态 `2 passed`；B3-B6/C1/C2/C4、媒体响应与 Data Health 核心回归 `177 passed`
- B3-C5、媒体响应、备份、导入、Schema 2、迁移、设置与 i18n 组合回归 `365 passed`
- 全量 `584 passed`，`pip check` 无依赖冲突
- Docker image build、隔离 Compose healthy、`/login` 与五个认证媒体/Data Health 页面 HTTP 200，资源已清理
- 完整矩阵和结论见 `PHASE3_COMPLETION_AUDIT.md`；最终父链修复提交 `db0048d` 的 Actions run `29386547600` 两个 job 均成功
- 保持应用版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 与 N100 状态不变

---

### Phase 4-A1 — 本地媒体单文件详情页

目标与实现：

- 新增登录保护的 `/media-library/detail` 普通媒体只读详情页，不新增 POST 或写操作
- 只接受规范化 `/media/` 路径和普通扫描中的精确记录，拒绝外部 / 转义 / missing / symlink / 特殊文件 / cleanup anchor
- 文件事实直接复用现有逐级目录 FD、文件 FD、内容哈希和当前映射复验结果，不通过目标 `Path.stat` / `Path.read_bytes` 二次打开
- 展示逻辑路径、文件名、扩展名、MIME、size、完整 SHA、有效 / 损坏、recovered、引用与重复状态
- 精确查询并链接全部 item cover / creator avatar 引用；按完整 SHA 展示组内数量、单文件 / 总占用 / 可释放空间和准确重复组入口
- 损坏媒体只链接现有 C4 预览，损坏引用只链接现有 C1 单项修复
- 媒体库、重复组和恢复中心 recovered 普通媒体入口保留各自规范化筛选、排序与分页返回状态

当前验证：

- A1 专项 `17 passed`；媒体、恢复、C1/C4、Data Health、备份、页面、响应式与 i18n 组合回归 `252 passed`
- GET SQL 写语句为 0；目标 / 其他媒体、根 / 父目录身份和目录项前后不变
- 父目录替换竞态只读取原 FD 内容后 404，不读取外部目标；目标 `Path.stat` / `Path.read_bytes` 禁用回归通过
- 全量 `601 passed in 91.96s`，`pip check` 无冲突
- Docker image build、隔离 Compose healthy；`/login` 200、匿名详情 303、认证详情 / 媒体库 200，临时资源已清理
- 实现提交 `c8cfb99` 已推送；Actions run `29389862206` 的 `test` 与 `Docker production smoke` 均为 success
- 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 不变

---

### Phase 4-A2 — 普通媒体安全重命名

目标与实现：

- A1 详情页为有效普通 / recovered 媒体提供同目录 basename 输入和零写入 GET 预览
- 目标必须保留原扩展名与大小写，并拒绝路径段、控制字符、百分号、首尾空白、保留前缀、过长和未变化名称
- 排除 anchor、上传残留、damaged、missing、skip、symlink、目录 / FIFO；任何目标对象、同 inode hardlink 或已有目标引用均阻止执行
- 预览展示两条逻辑路径、MIME、完整 SHA、mode / size / device / inode / mtime / ctime、全部引用和后果
- confirmed POST 复用 standard / strict `CONFIRM`，在 `BEGIN IMMEDIATE` 内重验完整源身份、目标不存在且零引用和全部源引用 ID
- 保持已验证父目录 / 源 FD，通过 `os.link(..., follow_symlinks=False)` no-overwrite 创建并持有目标 FD
- 精确迁移全部 cover / avatar 引用并复核 rowcount、源零引用、目标引用集合与源 / 目标 / 父链身份后提交
- 提交前失败 rollback 并按 held-FD inode 清理自建目标；`db.commit()` 抛错后先由独立 Session 重查两条路径的全部引用，仅确认未提交时清理 target
- commit 已实际落盘时保留 target / source 并报告 `committed_source_retained`；混合、无引用歧义或查询失败保留双路径并报告 `commit_outcome_unknown`
- 源删除失败时有效目标和引用保持，按实际状态报告源 / 双路径；成功携带来源状态返回新详情

当前验证：

- A2 专项 `43 passed`，覆盖有 / 无引用、recovered、strict、全身份 / 引用伪造、目标抢占、同 inode link、源 / 目标 / 普通目录 / symlink 替换、commit / unlink / fsync 失败
- SHA、内容、inode 和完整 SHA 重复组保持；目标 `Path.stat` / `Path.read_bytes` 禁用回归通过
- local-media、B3、B5、C1/C2/C4、A1 与 i18n 回归 `144 passed`；媒体 / Data Health / 备份 / 页面 / 响应式 / i18n 组合 `309 passed in 56.52s`
- 全量 `644 passed in 119.82s`，`pip check` 无冲突
- Docker image build、隔离 Compose healthy；user `10001:10001`、read-only root、`cap_drop: ALL`、`no-new-privileges` 保持，`/login` 200、匿名 rename 303、API login / 认证媒体库 200，临时资源已清理
- 实现提交 `b32e848` 已推送；Actions run `29396021693` 的 `test` 与 `Docker production smoke` 均成功
- commit 歧义修复后 A2 / i18n 专项 `50 passed`、核心媒体链 `193 passed in 27.83s`、广泛组合 `315 passed in 46.38s`、全量 `650 passed in 106.83s`，pip check 与隔离 Docker / HTTP 通过；修复提交 `09be556` 与 Actions run `29399210087` 两个 job 均成功
- 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 不变

---

### Phase 4-M2 — 批量整理与别名归一化

目标与实现：

- 媒体库 / 目录页仅多选当前页有效普通媒体，单批最多 20 项，无跨页全选
- GET 预览服务端重算当前页并重扫全部路径、身份和引用，使用 HMAC 签名完整快照且零写入
- 批量移动只到现有普通目录，逐项可修改 basename；批量重命名仅同目录并保持扩展名原样
- 拒绝重复源 / 目标、占用、交换、循环、非法媒体、越页路径、父目录替换和伪造快照
- 每项独立复用 M1 FD、hardlink、引用事务、commit outcome 与身份删除，逐项报告真实状态
- alias 按完整 dev/inode 重验，用户明确选择 keeper；引用提交并复核后才删除零引用 alias
- commit 未知、查询失败或混合引用时保留全部路径；同 SHA 不同 inode 独立文件永不参与
- 不新增任务表、Schema、迁移、依赖、版本、tag、Release、N100、网络或自动合并

当前验证：

- M2 服务与 HTTP 专项 `21 passed`，含 i18n 为 `22 passed`
- 目标抢占、父目录替换、引用漂移、commit unknown / mixed / query failure、fsync / unlink 故障均有覆盖
- 核心组合 `165 passed`，全量 `700 passed in 107.28s`，pip check 无冲突
- Docker image build、Compose healthy、`/login` 200 与 down 清理通过
- 实现提交 `a6b2d7b` 已推送；Actions run `29432471537` 的 `test` 与 `Docker production smoke` 均成功

---

### Phase 4-M1 — 媒体管理增强包

目标与实现：

- 新增现有普通媒体目录浏览，提供面包屑、子目录、当前目录统计、筛选、排序、分页和受限返回状态
- 安全目录记录保留完整父链身份；移动目标拒绝越界、missing、symlink、文件及 cleanup / upload 内部目录
- 将 A2 hardlink 路径变更抽象扩展为独立源 / 目标父目录 FD 链，同目录重命名和跨目录移动共享事务与故障语义
- 支持跨目录保持原名或同扩展名 basename，禁止覆盖并精确迁移全部 item cover / creator avatar 引用
- 详情页提供单个 `cover_path` / `avatar_path` 的 set / replace / clear 预览，POST 只更新目标字段并复用 standard / strict `CONFIRM`
- 新增按 dev/inode 聚合的零写入硬链接别名审计，逐路径列出引用并区分相同 SHA 的独立文件
- 失败 / unknown 保留有效原路径或双路径，不删除竞态抢占者、外部对象或任何非本操作创建的对象
- 不创建 / 删除 / 重命名目录，不做批量、keeper、自动合并、Schema 3、索引、版本发布或 N100

当前验证：

- M1 目录 / 移动 / 单项引用 / 别名四组专项 `29 passed`，直接覆盖源 / 目标目录替换、目标抢占、引用变化、strict 拒绝、commit / 查询 / fsync / unlink 故障
- local-media、A2、A1 详情、M1 四组与 i18n 核心组合 `140 passed`
- 最终全量 `679 passed in 113.51s`，`pip check` 无冲突
- Docker image build、Compose healthy、`/login` 200 与 down 清理通过
- 实现提交 `4e350bf` 已推送 main；Actions run `29405923933` 的 `test` 与 `Docker production smoke` 均成功
- 保持应用版本 1.0.6、Schema 2、迁移注册、依赖、Docker/CI、旧 tag / Release 与 N100 不变

---

## 七、Phase 5 执行顺序

当前顺序：

```text
1. Phase 5-P1 v1.2.0 规划已完成
2. Phase 5-N1 受控 HTTP 与 adapter 基础已完成
3. Phase 5-N2 Schema 4 来源追踪与 backup v2 已完成
4. Phase 5-P2 长期产品原则与路线对齐（已完成）
5. Phase 5-N3 核心 Provider 合同、认证、内容与下载需求规划；已完成，不选择 Provider
6. Phase 5-N4A Provider 基础设施与 Fixture-only Reference Provider；已完成
7. Phase 5-N4B Provider Approval Validator 与 Asset ID 契约强化；已完成
8. Phase 5-N4C 三类 Provider 静态研究与 Approval 草案；已完成
9. Phase 5-N4D 首个影视元数据 Provider；等待完整 Approval
10. Phase 5-N4E 订阅目录管理；等待固定订阅格式与 Catalog Approval
11. Phase 5-N4F 在线播放 Provider；等待独立 Streaming Approval
12. Phase 5-N4G 漫画 Provider；等待固定 Python Adapter Approval
13. Phase 5-N5A Provider-neutral Search Orchestration Service；已完成
14. Phase 5-N5B Search/detail empty-state 与 approved-provider UI
15. Phase 5-N5C Signed preview 与 manual apply plan/write gate
16. Phase 5-N6 用户明确确认的受控资源保存与下载
17. Phase 5-N7 多来源更新、受控同步和推荐
18. Phase 5-I1 完整集成冻结
19. Phase 5-R1 唯一一次 Hermes 最终独立验收
20. Phase 5-R2 v1.2.0 正式发布
21. N100 / 目标主机部署仍未授权，不属于本路线
```

已完成依据：

- Phase 2-F1 已完成只读 `/data-health` 页面和基础健康报告
- Phase 2-F2 已完成备份文件校验、恢复 dry-run 和导入 dry-run 报告
- Phase 2-F3 已完成低风险手动修复，修复范围限定在关系表和辅助记录
- Phase 2-G1 已完成本地基础设置中心，覆盖默认语言、分页、排序和首页入口
- Phase 2-G6 已完成 strict `CONFIRM`、备份提醒、结果详情和危险操作提示统一
- Phase 2-H 已随 v0.9.0 完成发布，启动预检、显式升级、备份确认和失败回滚边界已经建立
- Phase 2 结束时 schema 为 1 且生产迁移注册表为空；Phase 3-A1 现已增加唯一真实的 1 → 2 来源表迁移
- Phase 2-I1 已使用 100 / 1,000 / 10,000 条隔离数据完成列表、工作台、统计、维护页和文件 dry-run 基线
- I1 已确认列表与 cleanup 查询放大、合集详情 N+1、元数据 / 候选页无分页和统计重复扫描，未直接修复
- Phase 2-I2 已完成按需关系加载、metadata / candidate 分页、合集双分页、settings 复用、stats 聚合和 data-health 明细上限
- I2 在 10,000 条基线中将 items / cleanup / collection detail / stats 查询数分别从 258 / 249 / 165 / 28 降至 11 / 4 / 9 / 11
- Phase 2-I3 已统一页面 / API 错误、request_id 和脱敏请求日志，并保持高风险事务与确认边界
- I3 静态审查收紧外部 request_id 为 UUID / UUID hex，未匹配路由日志固定为 `/[unmatched]`
- Phase 2-I4 已完成登录与 session、同源写请求、服务端确认、输入输出、rollback、五类数据库和兼容性总审查
- I4 三档性能矩阵保持 I2 查询上限且无 N+1 回归，没有为剩余扫描新增索引或虚构迁移
- Phase 2-I 已随 v1.0.0 发布；任何后续索引仍需单独审批真实迁移
- Phase 2-K1 已确认没有真实 TODO、占位路由或失效入口，并将当时剩余工作限定为 K2 / K3
- Phase 2-K2 已关闭本地素材、批量 / 清除 / 解除确认、示例凭据、F4 专项测试和运维清单缺口
- K2 全量测试 347 passed，隔离 Docker build / up / `/login` 200 / 登录后本地媒体 200 / down 通过并已清理
- Phase 2-L4 已增加独立 Docker 生产冒烟 job、失败日志和始终执行的资源清理，并保留 pytest / pip check
- Phase 2-L5 已将 CI 权限限定为 `contents: read`，同一 workflow / ref 的过时运行由 concurrency 自动取消
- Phase 2-L6 已用 Python 标准库为生产镜像增加 `/login` 健康检查；CI 在执行原有 HTTP / 安全头检查前等待容器 `healthy`
- Phase 2-L7 已为生产与 CI Compose 增加只读根文件系统、`cap_drop: ALL`、`no-new-privileges` 和 `/tmp` tmpfs，并保留 `/app/data` 写入
- Phase 2-L8 已将应用与健康检查切换为固定 UID/GID `10001:10001`，并验证安全边界和 SQLite 重建持久化
- Phase 3-A1 已完成来源 CRUD、本地文本 / 书签预览导入、备份兼容和显式 Schema 1 → 2 升级
- Phase 3-A1 来源导入已补齐同名条目歧义保护，混合批次只写入可唯一确定目标的正常记录
- Phase 3-A2 已完成安全扫描、多图上传、SHA-256 去重、封面 / 头像关联和损坏文件降级
- Phase 3-A2 上传落盘已补齐临时文件、fsync、原子发布、竞态复核和批次失败清理
- Phase 3-A3 已完成确定性文件名候选、双向歧义冲突、单项 / 当前页事务确认及不覆盖保护
- Phase 3-A3 专项覆盖预览零写入、伪造冲突、strict 确认、跨页拒绝、陈旧目标和提交时条件更新，全量 407 passed
- Phase 3-A4 已完成未匹配图片建档、可编辑标题、现有 / 批次冲突拒绝、当前页事务写入和媒体不变保护
- Phase 3-A4 专项覆盖后缀过滤、预览零写入、标题编辑、strict 确认、冲突 / 跨页 / 陈旧 / 伪造拒绝和数据库失败整批回滚，全量 416 passed
- Phase 3-A5 已完成路径搜索、状态筛选、稳定排序、20 条媒体分页、三套页码状态保留和非法参数零写入回退
- Phase 3-A5 专项覆盖 Unicode 路径搜索、五种状态、四种排序、页码夹取、三套分页 URL、空结果、重定向状态和 A3/A4 候选不变，全量 424 passed
- Phase 3-A6 已完成封面 / 头像断裂引用、不可用媒体根、上传残留、SHA-256 重复内容和扫描跳过项的只读审计
- Phase 3-A6 专项覆盖正常未使用媒体、五类引用异常、三类根目录异常、告警汇总、200 条明细上限、GET 零写入和媒体修复拒绝，全量 433 passed
- Phase 3-B1 已完成完整 SHA-256 稳定分组、三项重复统计、duplicate 筛选、SHA 前缀搜索和同组路径展示
- Phase 3-B1 专项覆盖无效 / 单独媒体排除、排序分页状态、GET 零写入及 A3/A4 候选不变，全量 435 passed
- Phase 3-B2 已完成共享分组服务、组指标与引用、三类双向排序、20 组分页和 B1 精确链接
- Phase 3-B2 专项覆盖登录 / 405、边界复用、六种排序、非法参数、分页状态、GET 零写入及双语，全量 441 passed
- v1.0.6 已正式发布且范围仅为 B1 / B2；旧 tag / Release 未移动
- v1.0.6 发布前全量 441 passed、pip check 和隔离 Docker 双生命周期已通过
- Phase 3-B3 已完成显式 keeper、零写入预览、提交重扫、引用先迁移和安全删除实现
- Phase 3-B3 专项覆盖 strict 确认、陈旧 / 伪造 / 越界 / 文件异常拒绝、提交失败零删除及删除失败安全重试
- Phase 3-B3 keeper 竞态修复后全量 459 passed、pip check 与隔离 Docker 双生命周期已通过，SQLite 重建校验和不变且临时资源已清理
- Phase 3-B4 专项 16 passed、完整媒体链 120 passed、全量 474 passed 且 pip check 无冲突
- Phase 3-B4 隔离 Docker 双生命周期均 healthy，登录 / 恢复中心 / 普通媒体 / data-health 200，SQLite 校验和不变且资源已清理
- Phase 3-B5 已完成零写入预览、完整身份重验、无覆盖恢复发布、事务引用迁移、数据库失败补偿和锚点残留报告
- Phase 3-B5 专项覆盖 standard / strict、已引用 / 未引用、损坏 / 符号链接 / 错误扩展 / stale / forged / recovered 拒绝、目标碰撞、文件 / 目录 fsync、DB 回滚清理、删除失败和普通入口隔离
- Phase 3-B5 专项 12 passed、全量 486 passed 且 pip check 无冲突；隔离 Docker 双生命周期 healthy，登录 / 认证 / 恢复中心 / 单项预览 200，SQLite 校验和不变且临时资源已清理
- Phase 3-B5 功能提交 `9e19509` 已推送 main，Actions run `29306074275` 的 test / Docker production smoke 均通过
- Phase 3-B6 已完成零写入预览、完整身份重验、`BEGIN IMMEDIATE` 零引用复核、身份删除、目录 fsync 和失败状态报告
- Phase 3-B6 专项 15 passed，竞态注入、unlink / fsync / 写锁 / 引用查询失败和 B3-B5 完整媒体链回归 156 passed
- Phase 3-B6 全量 501 passed 且 pip check 无冲突；最终工作树隔离 Docker 双生命周期 healthy，登录 / 认证 / 恢复中心 / 删除预览 / 确认删除 200，SQLite 校验和不变且临时资源已清理
- Phase 3-B6 功能提交 `b70e18e` 已推送 main，Actions run `29309167659` 的 test / Docker production smoke 均通过
- Phase 3-C1 已完成 Data Health 单项入口、零写入预览、替代媒体路径 / SHA 搜索与 20 条分页、显式替换 / 清除和条件更新
- Phase 3-C1 提交在 `BEGIN IMMEDIATE` 内重验对象、原引用、问题与替代文件完整身份；陈旧 / 伪造 / cleanup anchor 请求拒绝，DB 失败整笔回滚且不操作文件
- Phase 3-C1 专项 7 passed、B3-B6 / 媒体库 / Data Health / 备份 / 导入组合回归 232 passed、全量 508 passed 且 pip check 无冲突
- Phase 3-C1 隔离 Docker 双生命周期 healthy，登录 / 认证 / Data Health / 预览 / 替换 / 清除 200，引用持久化、媒体 SHA 和 SQLite 重建校验和验收通过
- Phase 3-C1 功能提交 `05adaf7` 已推送 main，Actions run `29314452641` 的 test / Docker production smoke 均通过
- Phase 3-C2 已完成 Data Health 单项入口、零写入且不读内容的完整身份预览、已引用 C1 指引、`BEGIN IMMEDIATE` 零引用复核、身份删除和目录 fsync
- Phase 3-C2 专项覆盖精确 / 近似名称、目录 / 符号链接 / FIFO、非法 / 缺失 / 陈旧 / 伪造 / 同路径替换、standard / strict、引用与身份竞态、写锁 / 查询 / unlink / fsync 失败
- Phase 3-C2 专项 22 passed、C1 / B3-B6 / 上传 / Data Health / 备份 / 导入组合回归 253 passed、全量 530 passed 且 pip check 无冲突
- Phase 3-C2 Docker image build 通过，Compose healthy、`/login` 200，并已完整 down 清理
- Phase 3-C2 功能提交 `ab373b3` 已推送 main，Actions run `29317914417` 的 test / Docker production smoke 均通过
- Phase 3-C4 已完成损坏普通媒体 finding、媒体库 / Data Health 双入口、零写入完整身份预览、C1 引用指引、锁内零引用重验、身份删除和目录 fsync
- Phase 3-C4 专项 17 passed、媒体链与数据回归 280 passed、全量 557 passed 且 pip check 无冲突；Docker build、healthy Compose、`/login` 200 与 down 清理通过
- Phase 3-C4 功能提交 `1e686f3` 已推送 main，Actions run `29336790587` 的 test / Docker production smoke 均通过
- Phase 3-D1 已完成 B3-C5 finding / 导航 / 身份 / 引用 / GET / POST / 失败状态总审查，完整证据见 `PHASE3_COMPLETION_AUDIT.md`
- Phase 3-D1 修复 Data Health 路径重走、重复 finding 缺少直接入口、B3-B6 共享验证媒体父路径重解析及 C2 父链身份丢失四类真实问题
- Phase 3-D1 最终父链精确竞态 2 passed、核心回归 177 passed、组合回归 365 passed、全量 584 passed，pip check 与隔离 Docker healthy / HTTP 验收通过；修复提交 `db0048d` 的 Actions run `29386547600` 两个 job 均成功，已重新记录最终冻结
- Phase 4-A1 已完成安全只读详情聚合、全部引用与完整 SHA 重复组展示、三类来源状态返回、C1/C4 复用及外部路径 / symlink / 特殊文件 / anchor / 竞态拒绝；专项 17 passed、媒体链组合 252 passed、全量 601 passed、pip check 与隔离 Docker / HTTP 通过；提交 `c8cfb99` 与 Actions run `29389862206` 两个 job 均成功
- Phase 4-A2 已完成同目录 basename 预览、完整身份 / 引用快照、写锁重验、verified-parent-FD no-overwrite hardlink、事务引用迁移与 commit 后身份删除；commit 歧义修复改为独立 Session 复核后才决定清理或保留双路径，修复后专项 50 passed、广泛组合 315 passed、全量 650 passed、pip check 与隔离 Docker / HTTP 通过；修复提交 `09be556` 与 Actions run `29399210087` 两个 job 均成功
- Phase 4 已随 v1.1.0 发布；Phase 5-N1/N2 已完成且 N2 Actions 成功，当前
  为 P2 产品原则对齐，N100 部署继续等待单独授权

---

## 八、受控网络、阶段授权与长期禁止项

外部网络默认禁止。只有当前 GOAL 与用户共同批准的 Provider Adapter，才可
通过共享 `OutboundHttpClient` 在登录用户主动操作后访问代码固定的 HTTPS
Host/Endpoint。该例外不开放任意 URL 能力。

永久禁止：

- 任意 URL fetch、用户自定义 Host/协议/端口/base URL/路径
- 无限制 crawler、整站遍历和递归发现未知链接
- 权限、年龄、付费、订阅、地区或账号限制绕过
- 凭据窃取、隐藏提取、泄漏、跨 Provider 共享或越权读取
- 隐藏网络与未经确认的大量写入、覆盖或下载
- 默认上传本地收藏、用户记录或推荐偏好

默认拒绝但可由未来独立 GOAL 授权：

- Provider 的 OAuth、API Token、用户名/密码或用户主动提供的 Session Cookie
- Provider-specific 结构化或 HTML 解析
- 封面、预览和媒体下载
- 第二 Provider 与多来源聚合
- 默认关闭且可见、可控、可撤销的后台同步
- 本地推荐、可选 AI、下载队列和定时检查

搜索、预览、数据库写入和下载必须分离。认证秘密按 Provider 本地隔离；
下载和写入必须分别预览并获得用户明确确认。

本地来源导入继续只保存用户 URL、解析本地书签 HTML / 纯文本清单，始终
零网络。备份、恢复、CSV / JSON 导入也始终零网络。完整边界以 RULE.md 和
当前 GOAL.md 为准。

---

## 九、开发阶段完成标准

每个阶段完成前必须确认：

- 功能在 GOAL.md 范围内
- 未触碰 RULE.md 禁止项
- targeted 与相关回归通过，`pip check` 通过
- Schema / 备份、跨模块大型阶段、I1 或 release candidate 按要求运行全量测试
- 只有风险需要时使用独立临时目录或隔离 volume 完成 Docker 验收
- 测试和 Docker 均未使用既有 `data/`
- i18n key 对称
- README 更新
- TASKS 更新
- REVIEW 更新
- CHANGELOG 写入 Unreleased
- 工作区干净
- 已提交并推送，Actions 的 `test` / `Docker production smoke` 通过
- 云端 diff 复核完成；R1 前绝不调用 Hermes

---

## 十、发布标准

发布版本前必须确认：

- 当前阶段已通过审查
- 完整测试通过
- Docker 验收通过
- CHANGELOG 从 Unreleased 整理到新版本段
- README 当前版本号更新
- TASKS / REVIEW 同步更新
- 不修改旧 tag
- 创建 annotated tag
- 推送 main 和 tag
- 创建 GitHub Release
- Release 内容与 CHANGELOG 一致
