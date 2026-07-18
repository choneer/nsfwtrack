# Phase 5-N4A 完成摘要：Provider 基础设施与 Fixture-only Reference Provider

## 阶段结论

Phase 5-N4A 已完成本地实现与验证。本阶段只将 N3 合同落为 provider-neutral
基础设施，并增加测试专用的 synthetic Reference Provider；没有选择、命名、
访问、批准或实现任何真实 Provider。

真实 Phase 5-N4 仍必须等待用户逐项填写并明确批准
`PROVIDER_APPROVAL_TEMPLATE.md`。N4A 的 Fixture Provider 不能作为真实 Provider
批准，也不能绕过 Host、Endpoint、认证、法律、归属、Fixture、依赖或 Schema
门禁。

## 基线与不变量

- 起始 SHA：`ec81eb44a190125fc75c38f76a2d0683a239b4b4`
- 分支：`main`
- 应用版本：`1.1.0`
- Schema：`4`
- Backup：`nsfwtrack.backup.v2`，继续接受 v1
- Production Provider Registry：`EndpointRegistry(())`
- 真实 Provider：无
- 真实认证或 Secret Vault：无
- UI、数据库入库、下载、推荐、同步：无
- 新依赖或配置：无
- Hermes：未调用、未编写
- tag、Release、N100：未创建、未部署

既有 `data/` 只属于用户本地数据。本阶段未读取、枚举、复制、修改、删除、
移动、格式化、暂存或提交其中任何内容；pytest 只使用 conftest 创建的独立临时
数据库、媒体目录和锁目录。

## Provider capability 基础

`app/source_adapters/contracts.py` 现已实现 immutable、code-owned 的：

```text
ProviderCapabilityLayer
ProviderOperation
ProviderCapabilities
MetadataCapabilities
AuthCapabilities
DiscoveryCapabilities
AssetCapabilities
DownloadCapabilities
```

Operation 固定属于五层：

- Metadata：`search`、`detail`
- Auth：`auth_test`、`auth_login`、`auth_refresh`、`auth_revoke`、`auth_logout`
- Discovery：`discover`
- Asset：`asset_list`、`asset_resolve`
- Download：`download`

每层只接受对应 enum；tuple 必须 immutable、无重复，Asset/Download operation
必须与 asset kinds 同时声明。`ProviderCapabilities` 必须有合法 Provider key、
bounded display/content scope 和至少一个 operation。`supports()` 只接受 typed
operation；`require()` 对缺失 capability 抛出稳定 `capability_not_supported`，
不推测或回退到其他 operation。

## 能力分层 Protocol

现有 runtime-checkable Protocol：

```text
SourceMetadataAdapter
ProviderAuthAdapter
ProviderDiscoveryAdapter
ProviderAssetAdapter
ProviderDownloadAdapter
```

`SourceAdapter` 保留为 `SourceMetadataAdapter` alias，以兼容 N1 名称。所有 Adapter
必须显式携带 `key`、`display_name` 和 `ProviderCapabilities`。N4A 只实现 test-only
Metadata+Asset Adapter；Auth、Discovery、Download 只有类型合同，没有真实行为。

## SourceAsset、Auth 和错误模型

`SourceAsset` 为 frozen DTO，固定：

```text
provider_key / external_id / opaque asset_id / kind / display_name
mime_type / size_bytes / checksum_algorithm / checksum_value
requires_auth / downloadable
```

Asset kind 只允许 cover/preview/media/attachment。asset ID 不能是 URL、网络位置、
路径或含空白的 Locator；MIME 必须 canonical lowercase，size 非负，checksum
algorithm/value 必须同时存在且长度/hex 格式一致。Fixture mapping 还会拒绝响应
通过 `requires_auth` 或 `downloadable` 扩大未声明 capability。

AuthMode 固定为：

```text
none / api_token / oauth / username_password / session_cookie
```

AuthState 固定为：

```text
not_configured / configured / valid / expired / invalid / revoked / unknown
```

`ProviderAuthStatus` 要求非 not-configured 状态绑定 typed mode，credential 状态
不能使用 `none`，时间必须 timezone-aware，valid 需要 checked_at，expired 需要
expires_at，expiry 不能早于 check。

`ProviderErrorCode` 覆盖 capability、auth、provider、rate、payload、asset、
locator、download 和 outcome-unknown 稳定类别。`ProviderAdapterError.__str__()`
只返回稳定 code，不包含 Provider payload、External ID、URL、Host、凭据或原始异常。

## Typed Endpoint Operation

`app/source_adapters/registry.py` 的 `EndpointOperation` 不再接受自由 operation
名称，而使用 `ProviderOperation`。每项定义固定：

```text
path/path parameter
query/body business-parameter mapping
required parameters
GET or POST
none/json/form request encoding
auth requirement
cookie policy
JSON/HTML/file response kind
allowed content types
response/page limits
fixed non-secret headers
redirect policy/exact hosts/hop limit
exact Asset Host allowlist
```

GET 禁止 body；JSON/form body 只从 `BusinessParameter` mapping 生成。Query、Body、
Path 不能重复映射同一 business parameter，remote field name 必须 fixed/bounded。
Authorization、Cookie、Host、Content-Length、Content-Type、Accept、Connection 等
安全关键 Header 不能作为 fixed header。Asset/redirect Host 必须 exact lowercase
ASCII hostname，拒绝 wildcard、IP literal、scheme、port、path 和 suffix rule。

每个 `ProviderEndpoint` 必须绑定同 Provider key 的 `ProviderCapabilities`，typed
endpoint operation set 与 manifest operation set 必须完全一致，auth/cookie policy
必须被 manifest auth modes 声明。Production Registry 保持精确为空。

## Shared Outbound 扩展

`OutboundRequest` 公共字段仍精确为：

```text
provider_key / operation / query / external_id / page / page_size
```

没有 URL、Host、port、base URL、Path、Method、Body、Header、Cookie、Token、
Password 或 Locator 输入。Shared client 只根据 Registry-owned mapping 生成 GET/
POST、canonical JSON 或 form body 和 fixed safe headers。

N4A 未实现 auth/cookie、non-JSON response 或 approved redirect execution；对应
policy 在 DNS 前稳定返回 `auth_not_configured` 或
`operation_policy_not_supported`。现有 `trust_env=False`、HTTP/1.1、无 proxy/
retry、完整 DNS set、numeric-IP pinning、TLS hostname/SNI/Host、TCP/TLS peer、
3s connect/10s total、1 MiB stream、bounded concurrency、cancellation、immutable
JSON 和日志脱敏全部保留。

## Fixture-only Reference Provider

Reference Provider 只存在于：

```text
tests/fixture_provider.py
tests/fixtures/reference_provider/search.json
tests/fixtures/reference_provider/detail.json
tests/fixtures/reference_provider/assets.json
tests/test_phase5_n4a.py
```

它使用保留的 synthetic `.invalid` hostname/path/content，只实现：

```text
search / detail / asset_list
```

它没有 Auth、Discovery、Asset Resolve 或 Download capability。所有响应来自静态
Fixture；Fake Resolver、Fake Clock、MockTransport 和 Fake Network Backend 保证
零真实 DNS/Provider/remote-media 请求。Fake Backend 路径仍执行 production
PinnedAsyncTransport 的 selected IP、SNI、Host、peer 和 stream 验证接口。

Fixture payload 故意包含未批准 operation、Host、Endpoint、Locator 和
downloadable 建议。Adapter 只读取 DTO allowlist 字段，Registry/capability 保持
不变，所有 request 只到 synthetic metadata Host；`downloadable=true` 在缺失
Download capability 时作为 invalid payload 拒绝。

## 验证结果

- 初始 N4A focused：`17 passed`
- N4A + N1 contracts/outbound：`116 passed`
- N2 + sources regression：`46 passed`
- 初始全量 pytest：`934 passed in 237.22s`
- 最终安全复核后 N4A focused：`21 passed in 3.78s`
- 最终安全复核后全量 pytest：`938 passed in 167.61s`
- `pip check`：`No broken requirements found.`
- `git diff --check`：通过

验证确认：

- Production Provider Registry 仍为 `EndpointRegistry(())`
- Fixture Provider 不被 app import
- response 不能扩大 capability、operation、Host、Locator 或 Download
- logs 不含 query、External ID、payload marker、URL、Host 或 IP
- 既有 N1 DNS/IP/TLS/peer/timeout/stream/concurrency/cancellation tests 继续通过
- Schema 4 来源、Backup v2/v1 restore 和零网络回归继续通过
- 应用版本、Schema、Backup、依赖、配置、Docker、Compose 和 CI 未变化

## N4 交接

真实 N4 开始前，用户仍必须提交完整 Provider Approval，逐项批准 Provider 身份、
NSFW-core relevance、合法/条款/归属依据、每个 Metadata/Auth/Asset Host、每个
Endpoint/Method/Encoding/Response/Content-Type/Size/Rate/Redirect、认证生命周期、
Search/Detail/Asset mapping、Fixture/fault matrix、依赖、Schema、Migration 和
Backup 影响。

任何真实信息缺失时必须停止，不得使用 N4A Fixture 值、搜索结果或响应建议代替。
N4A 不授权真实网络、认证、Vault、UI、入库、下载、推荐或同步。
