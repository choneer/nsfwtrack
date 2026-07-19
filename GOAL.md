# Phase 5-N5A — Provider-neutral Search Orchestration Service

## 完成摘要

Phase 5-N5A 已在基线
`a73d5968edc15ec69a9356f02f9ada1803ea7014` 上完成本地实现与验证。

本阶段新增 Provider-neutral、零网络、零数据库写入、零文件写入的 Search
Orchestration Service。它只消费已经通过现有 N4D-C Package 门禁的 Video
Metadata Package，不选择、不命名、不加载或访问真实 Provider。

应用版本保持 `1.1.0`，Schema 保持 `4`，Backup 保持
`nsfwtrack.backup.v2`。Production Registry 仍为 `EndpointRegistry(())`，
Production Search Packages 与 Production Search Providers 均为 `()`。

## 实现产物

新增：

```text
app/source_search/__init__.py
app/source_search/contracts.py
app/source_search/service.py
tests/test_phase5_n5a.py
```

更新：

```text
GOAL.md
PLAN.md
TASKS.md
REVIEW.md
CHANGELOG.md
PROVIDER_CONTRACT.md
docs/provider-research/provider-roadmap.md
```

没有修改 `app/source_adapters/registry.py`、
`app/services/outbound_http.py`、Docker、Compose、CI、依赖、Schema、Migration、
Backup、路由、模板、i18n 或数据库模型。

## Immutable Search 合同

新增 frozen/slots：

```text
SearchProviderDescriptor
VideoSearchRequest
VideoDetailRequest
VideoAssetListRequest
VideoSearchEnvelope
VideoDetailEnvelope
VideoAssetListEnvelope
ProviderSearchServiceError
```

Request 固定 Provider selection、query、page/page_size 与 opaque external ID
边界，拒绝 bool/int 混淆、控制字符、空 query、URL scheme、slash、backslash 和
dot segment。Envelope 在成功返回前验证 exact DTO 类型、Provider identity、
external identity、query、page/page_size、UTC received time、asset tuple 硬上限
与 duplicate asset identity。

DTO 不保存 raw Mapping、raw JSON、HTTP response、URL、Host、Header、Cookie、
Token、Adapter repr、异常文本或 fixture path。

## ProviderSearchService

新增：

```text
list_providers
search
detail
asset_list
build_production_search_service
```

构造门禁：

- packages 必须是 exact tuple；
- 每个元素必须是 exact `ProviderPackage`；
- 每个 Package 必须先通过 `validate_provider_package`；
- 只接受 `ProviderAdapterKind.VIDEO_METADATA`；
- Provider key 唯一并稳定排序；
- 构造阶段不调用任何 Adapter operation；
- 不从目录、entry point、环境变量、Artifact 或动态 import 发现 Package。

Operation authority 只来自 `ProviderAdapterBinding.operations`，并通过
`ProviderAdapterBinding.handler_for` 获取 handler。`search`、`detail`、
`asset_list` 严格独立，各自只调用对应 Adapter operation 一次；capability 缺失
在 Adapter 调用前稳定拒绝，不自动调用下一操作、resolve、download 或数据库写入。

## 稳定错误与取消

新增稳定错误 code：

```text
invalid_request
provider_not_available
operation_not_approved
adapter_mismatch
invalid_result
provider_error
cancelled
unknown
```

`str`/`repr` 只包含稳定 code 与可选稳定 cause code，不回显 query、external ID、
Provider payload、Host、Path、Header、Adapter repr 或原始异常文本。
`ProviderAdapterError` 只保留稳定 `ProviderErrorCode`；未知异常映射为 `unknown`；
失败不伪装为空结果或成功；`asyncio.CancelledError` 原样传播。

## Production 空服务

`PRODUCTION_SEARCH_PACKAGES` 固定为 `()`。Production Service：

- `list_providers()` 返回 `()`；
- 任意合法 Provider request 返回 `provider_not_available`；
- 不加载 tests-only synthetic Provider；
- 不修改或替换 `PRODUCTION_ENDPOINT_REGISTRY`；
- import、构造、catalog 与前置拒绝路径不执行网络、DNS、Outbound、数据库、
  文件读写、Adapter operation 或 dynamic import。

N5A 不绕过 N4D-D-B 的真实 Provider Approval。N5B 后续负责 search/detail
empty-state 与 approved-provider UI；N5C 后续负责 signed preview 与 manual apply
plan/write gate。

## 测试与验证

```text
N5A focused: 33 passed
N4A/N4B/N4D-A/N4D-B/N4D-C/N4D-D-A/N5A/Adapter/Outbound: 376 passed
Full pytest: 1194 passed
pip check: No broken requirements found.
git diff --check: passed
```

测试覆盖 immutable/slotted/tuple 合同、request 边界、Package 构造门禁、Provider
排序、operation exactly-once 分离、pre-call capability 拒绝、返回 identity/type/
page parity、duplicate/overflow asset、stable provider/unknown/adapter mismatch errors、
cancellation 和 production empty service。零副作用测试禁止 socket、httpx2、
Outbound Client、SQLAlchemy execute/commit、Path read/write 与 dynamic import。

## 安全与范围结论

- 未添加真实 Provider、Host、Endpoint、URL、response 或 fixture；
- 未实现真实网络、认证、Cookie、Token、Vault、UI、导入、下载、播放、后台同步、
  推荐或 AI；
- 未新增依赖、Schema、Migration、Backup、Docker、Compose 或 CI 变化；
- 未调用或编写 Hermes；
- 未创建 tag 或 Release；
- 未部署 N100；
- 既有未跟踪 `data/` 未读取、枚举、进入、复制、修改、移动、删除、暂存或提交；
- 本阶段使用唯一提交信息 `Add provider search orchestration service`。
