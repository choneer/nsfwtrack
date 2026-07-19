# Phase 5-N4D-D-A — Provider Approval Artifact v1 与离线装载门禁

## 完成摘要

Phase 5-N4D-D-A 已完成本地实现与验证。起始基线为
`4a10e194a1072169e563a8ad7ce4fb527094e73d`，分支为 `main`。应用版本保持
`1.1.0`，Schema 保持 `4`，备份格式保持 `nsfwtrack.backup.v2`，
Production Registry 仍为 `EndpointRegistry(())`。

本阶段只新增 Provider-neutral、纯本地、不可执行的 Approval Artifact 和装载门禁。
没有选择、推荐、命名、研究、访问、实现或注册任何真实 Provider，也没有增加真实
Provider key、Host、Endpoint、Header、URL、响应 fixture、凭据或网络权限。

## Artifact v1 合同

`app/source_adapters/artifact.py` 新增固定：

```text
format = nsfwtrack.provider-approval
version = 1
attestation algorithm = sha256
```

新增 frozen/slots typed 合同：

- `ProviderArtifactHeader`；
- `ProviderArtifactAdapterRef`；
- `ProviderArtifactAttestation`；
- `ProviderApprovalArtifact`；
- `ProviderAdapterFactoryBinding`；
- `ProviderAdapterFactoryRegistry`；
- `ProviderArtifactError` 与 `ProviderArtifactErrorCode`。

Artifact 精确表达现有 `ProviderApproval`、`ProviderCapabilities`、
`ProviderEndpoint`、`ProviderEvidenceManifest`、fixture digest catalog 和
opaque Adapter binding reference。所有 tuple 在 JSON 中显式为 array，optional
字段必须显式为 null，deny-safe 默认字段不得省略。

Header 绑定 artifact ID、Provider key、scope、UTC creation time 和 review revision；
loader 要求其 Provider/scope/revision/time 与 Approval/Evidence 精确一致。
Adapter Ref 只保存 opaque `binding_id`、bounded Adapter kind 和 ordered
operations，不保存 Adapter、callable、module/class path 或 import surface。

## Strict bytes-only parser

`parse_provider_artifact` 只接受 exact `bytes`；`str`、`Path`、
`bytearray`、`memoryview` 和 bytes subclass 全部以稳定错误拒绝。

固定资源上限：

```text
MAX_ARTIFACT_BYTES = 262144
MAX_ARTIFACT_DEPTH = 32
MAX_ARTIFACT_NODES = 20000
MAX_ARTIFACT_STRING_LENGTH = 8192
MAX_ARTIFACT_ARRAY_ITEMS = 512
```

parser 的顺序为：

1. exact bytes type；
2. total byte size；
3. strict UTF-8；
4. JSON parse 与任意层级 duplicate-key detection；
5. depth/node/string/array resource audit；
6. dataclass-derived exact strict schema；
7. unknown-field rejection；
8. missing-field rejection；
9. fixed format；
10. supported version；
11. raw canonical attestation verification；
12. typed Header；
13. typed Approval；
14. typed Capabilities；
15. typed Endpoint；
16. typed Evidence；
17. typed fixture digest catalog；
18. typed Adapter Ref 与 Attestation；
19. normalized typed/raw equality。

标准 `json.loads` 的 duplicate overwrite 行为通过 `object_pairs_hook` 封闭；
NaN、Infinity、`-Infinity` 和 overflow-to-infinity number 均拒绝。所有层级字段
必须与 typed dataclass 精确一致，既不忽略 unknown field，也不猜测 missing/default。
资源审计在任何 typed object 构造前完成。

## Canonical serialization 与 attestation

`serialize_provider_artifact` 和 `canonical_provider_artifact_bytes` 使用：

- object key 稳定排序；
- 紧凑 `,` / `:` 分隔符；
- `ensure_ascii=False` 的稳定 Unicode；
- 禁止非有限数字；
- timezone-aware UTC `Z` 时间；
- exactly one terminal LF 的固定 Artifact framing。

同一 typed Artifact 始终输出相同 bytes；非 canonical key order/whitespace 可解析，
但 parse → serialize 必须收敛为同一 canonical bytes。Unicode、null、nested tuple
均精确 round trip。

`compute_provider_artifact_sha256` 只计算删除 top-level `attestation` 后的紧凑
canonical payload bytes。`verify_provider_artifact_attestation` 使用稳定比较，
mismatch 只返回 `artifact_attestation_mismatch`，不回显实际或预期 digest。

该 SHA-256 只证明本地 canonical payload 完整性，不代表批准、真实性或远程信任；
本阶段没有签名、HMAC、密钥、PKI、证书、远程校验或信任链。

## Code-owned Adapter Factory Registry

`ProviderAdapterFactoryRegistry` 由调用方以 immutable tuple 显式构造。
`ProviderAdapterFactoryBinding` 精确绑定：

```text
binding_id
provider_key
adapter_kind
operations
factory
```

`binding_id` 仅接受小写 opaque ID，禁止点号模块路径、class path、冒号、正反斜杠
和 URL scheme。Artifact 不能提供 callable，也不能决定 Python import。

生产模块不导入或调用 `importlib`，不读取 entry points、环境变量、配置文件或目录，
不扫描/发现 factory。duplicate binding ID 在 registry 构造时拒绝。

factory 只有在 Artifact parser、format/version、attestation、typed construction、
cross-component parity、binding lookup 和 factory metadata parity 全部通过后才调用。
前置失败调用次数为 0；成功路径调用恰好 1 次；异常转为
`artifact_factory_failed`，不输出异常文本或 factory repr。

## Artifact → ProviderPackage loader

`load_provider_package_from_artifact(artifact_bytes, factory_registry)` 的完整顺序为：

1. 完成 strict parser、format/version、attestation 和 typed construction；
2. 精确验证 Header/Approval/Capabilities/Endpoint/Evidence/fixture/Adapter Ref；
3. 验证 Provider identity、display/content scope、scope、review revision/time、
   Approval ID 和 ordered operations；
4. 验证 fixture digest catalog 与 Evidence 精确一致；
5. 拒绝审查文本中的环境模板、动态执行、URL、凭据赋值和 raw-response 形式；
6. code-owned binding lookup；
7. factory provider/kind/operations metadata parity；
8. factory 调用一次；
9. 构造 `ProviderAdapterBinding`；
10. 构造 `ProviderPackage`；
11. 调用既有 `validate_provider_package`；
12. 返回完整 Package。

factory 返回 Adapter 后仍必须通过 N4D-C 的 explicit authority、Source/Video Protocol、
identity 和 Package validation。构造/parse/serialize/attestation/load 均不执行
search/detail/asset_list，也不构建或修改 Production Registry。

包装 `ProviderPackageError` 时，Artifact error 固定为
`artifact_package_invalid`，并只保留稳定 `ProviderPackageErrorCode` cause。

## 稳定错误模型

十六个稳定错误码：

```text
artifact_invalid
artifact_too_large
artifact_invalid_utf8
artifact_duplicate_key
artifact_resource_limit
artifact_unknown_field
artifact_missing_field
artifact_format_mismatch
artifact_version_unsupported
artifact_attestation_mismatch
artifact_provider_mismatch
artifact_operation_mismatch
artifact_binding_not_found
artifact_binding_mismatch
artifact_factory_failed
artifact_package_invalid
```

`str(error)` 只输出 code；`repr(error)` 只输出 code 与可选 stable package cause。
错误不保存或输出 Artifact bytes、JSON 片段、Host、Header、路径、digest、binding、
factory/Adapter repr、异常文本或 synthetic marker，也不写日志。

## Tests-only synthetic Artifact

`tests/provider_artifact_fixture.py` 基于 N4D-C `VIDEO_PACKAGE` 构造 tests-only
Artifact 与 factory registry，只使用 `fixture_video`、现有 `.invalid` Host 和六份
Video Metadata fixture digest。

固定 canonical fixture：

```text
tests/fixtures/provider_artifact/synthetic_video_artifact.json
bytes = 9279
canonical_sha256 = d3d82efe2760808ad1c5032980936ac17ec08350082f63e81710b6177612189b
binding_id = synthetic_video_adapter_v1
```

磁盘 fixture bytes、typed serializer bytes 和 parse → serialize bytes 完全一致。
fixture 文件只由测试在进入 production loader 前显式读取；生产模块不含 Path/file API，
不读取 fixture 或扫描目录。该 Artifact/Factory 不进入生产常量或 Registry。

## 测试与文档

`tests/test_phase5_n4d_d_a.py` 覆盖：

- frozen/slots、tuple-only、无动态属性、duplicate binding ID；
- opaque binding ID 与 module/class/path/URL rejection；
- exact bytes、UTF-8、duplicate key、unknown/missing field；
- bool/int 混淆、NaN/Infinity、depth/node/string/array/byte limits；
- deterministic canonical bytes、Unicode/null/tuple round trip；
- attestation excludes itself、mismatch/algorithm/grammar/redaction；
- Provider/operation/evidence parity 与 policy text fail-closed；
- binding not found、factory metadata mismatch、pre-factory zero calls；
- factory success exactly once、factory failure redaction；
- wrong Adapter 的 stable Package cause；
- Adapter operation 不执行；
- parser/serializer/attestation/loader 在 DNS/HTTP/SQLAlchemy/Path/importlib/
  Adapter operation forbidden 时仍通过；
- Production Registry 对象和值始终为空。

`PLAN.md`、`TASKS.md`、`REVIEW.md`、`CHANGELOG.md`、
`PROVIDER_CONTRACT.md`、`PROVIDER_APPROVAL_TEMPLATE.md`、Provider roadmap 和
video approval draft 已同步路线：

```text
N4D-A   Approval policy closure
N4D-B   Video Metadata DTO / fixture / merge framework
N4D-C   Provider Package binding and offline activation gate
N4D-D-A Provider Approval Artifact v1 and offline loader
N4D-D-B One explicitly approved Provider Artifact and Adapter
```

N4D-D-B 仍需用户单独明确提供并批准 Provider identity、合法访问/条款、精确
Host/Endpoint/Header/Operation、脱敏 fixture、canonical production Artifact、
SHA-256 完整性值和 code-owned binding metadata。

## 长期边界

- 未修改 `app/source_adapters/registry.py`、`app/services/outbound_http.py`、
  Production Registry、ORM、路由、UI、认证、Vault、Schema、Migration、Backup、
  Docker、Compose、CI 或依赖。
- 不实现真实网络请求、DNS、数据库写入、Asset Resolve、播放、下载、同步、后台任务、
  推荐、AI 或任意 URL/Host/Path 输入。
- production parser/serializer/attestation/loader 零网络、零 DNS、零数据库、零文件
  读写；测试只读取明确授权的 synthetic Artifact fixture。
- 不使用 importlib、动态 import、entry points、环境/config/目录发现。
- 不调用 Hermes，不创建 tag/Release，不部署 N100。
- 既有未跟踪 `data/` 未读取、枚举、进入、复制、修改、移动、删除、暂存或提交。

## 验收记录

最终本地门禁：

- N4D-D-A focused：`58 passed`；
- N4A/N4B/N4D-A/N4D-B/N4D-C/N4D-D-A/Source Adapter/Outbound targeted：
  `343 passed`；
- full pytest：`1161 passed`；
- `pip check`：`No broken requirements found`；
- canonical fixture/attestation/round-trip：通过；
- Application：`1.1.0`；
- Schema：`4`；
- Backup：`nsfwtrack.backup.v2`；
- Production Registry：`EndpointRegistry(())`；
- `git diff --check` 与 14-file allowlist 审计：通过。

唯一提交信息为：

```text
Add provider approval artifact loader
```

推送后仍需等待并记录 GitHub Actions `test` 与
`Docker production smoke` 均成功。不得创建 corrective commit、tag 或 Release；
最终工作区只允许保留既有 `?? data/`。
