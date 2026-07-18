# Phase 5-N4B — Provider Approval Validator 与 Asset ID 契约强化（已完成）

## 完成状态

Phase 5-N4B 已在起始提交
`40c933ee2cbcf884f6ec423118ee9876d640e95f` 上完成本地实现与验证。

本阶段只新增 Provider-neutral Approval 合同、纯本地一致性 Validator、
`SourceAsset.asset_id` opaque identifier 强化及确定性测试。没有选择、命名、
批准、访问或注册任何真实 Provider。

稳定边界保持：

- 应用版本：`1.1.0`
- Schema：`4`
- Backup：`nsfwtrack.backup.v2`
- Production Provider Registry：`EndpointRegistry(())`
- 真实 Provider、Host、Endpoint、凭据：无
- 认证、Secret Vault、UI、入库、Asset Resolve、下载、推荐、同步：未实现
- 依赖、配置、Schema、Migration、Backup、Docker、CI：未修改
- Hermes、tag、Release、N100：未执行
- 既有 `data/`：未读取、枚举、修改或暂存

## Approval 数据模型

`app/source_adapters/approval.py` 新增 frozen、slots、typed 模型：

- `ProviderApproval`
- `ProviderApprovalScope`
- `ApprovedHost` / `ApprovedHostPurpose`
- `ApprovedOperation`
- `ApprovedRatePolicy`
- `ApprovedAuth`
- `ApprovedAssetPolicy`
- `ApprovedDownloadPolicy`
- `ApprovalAttributionPolicy`
- `ApprovalValidationError` / `ApprovalValidationErrorCode`

`ProviderApproval` 固定并验证：

- 有界 `approval_id` 与格式版本 `1`
- Provider key、display name、content scope、产品定位、合法访问和条款依据
- attribution policy
- 完整 capability operation 集合
- exact Host 表及 metadata/auth/asset purpose
- 每个独立 operation 的 Host、path、typed parameter mapping、method、encoding、
  auth、cookie、response、content type、limit、redirect、rate 与 Asset Host
- Auth mode、credential Host、OAuth state/PKCE 和密码长期保存政策
- Asset kind/Host/数量/locator-resolution policy
- Download kind/Host/文件数/字节/checksum policy
- explicit exclusions

所有模型均 immutable、无动态属性、不接受任意附加字段。Host 只接受 lowercase
ASCII exact hostname 和端口 443；拒绝 wildcard、suffix 表达、IP literal、scheme、
path、query 和 fragment。同一 hostname 只有通过不同 Host ID 和 purpose 逐项批准
才能承担多个职责。

测试 Approval 明确标记 `test_fixture`，并强制全部 Host 使用保留的 `.invalid`
域名；production scope 反向拒绝 `.invalid` Host。

## 纯本地 Validator

新增无网络、无 DNS、无数据库、无文件、无 Vault 副作用的函数：

```python
validate_provider_approval(approval)
validate_approval_against_capabilities(approval, capabilities)
validate_approval_against_endpoint(approval, endpoint)
validate_approval_for_activation(approval, capabilities, endpoint)
validate_approval_secret_fields(payload)
```

Validator 精确验证：

- Provider key、display name、content scope 和 attribution policy
- Approval、`ProviderCapabilities`、`ProviderEndpoint` 的 operation 集合
- capability layer、Auth mode、Asset kind、Download kind
- Host ID 到 exact hostname/443/purpose/credential policy 的映射
- path template、path/query/body typed mapping、required parameters
- GET/POST、none/JSON/form encoding
- Auth requirement、session-cookie policy
- JSON/non-JSON response kind、top-level shape、content types
- response/page/asset/download limits 不超过批准上限
- runtime Provider concurrency `1` 与 automatic retry `0`
- redirect policy、exact redirect Host 和 hop limit
- exact Asset Host allowlist
- explicit exclusions 不被 runtime 违反

Approval 与 runtime 保持单向审查关系。模块不提供 Approval 到
`ProviderEndpoint`、`EndpointRegistry` 或 Production Registry 的生成/注册函数，
也不读取 Approval 文件、环境变量、URL、Python 模块或远程响应。

Activation gate 在一致性验证后继续 fail closed：

- 当前只承认 shared client 已实现的 `search`、`detail`、`asset_list`
- auth/cookie/non-JSON/redirect、Auth/Discovery/Asset Resolve/Download 等未实现
  策略返回 `approval_incomplete`
- `test_fixture` Approval 返回 `approval_invalid`，不能作为真实 N4 Approval

稳定错误仅输出 bounded code：

```text
approval_invalid
approval_incomplete
approval_provider_mismatch
approval_capability_mismatch
approval_operation_mismatch
approval_host_mismatch
approval_auth_mismatch
approval_asset_policy_mismatch
approval_download_policy_mismatch
approval_contains_secret
```

Secret-field boundary 递归、有深度和节点上限，拒绝 secret/password/token/cookie
value 类字段、非有限数和非 JSON-compatible 对象；错误和日志不包含 synthetic
marker、完整 Approval repr、URL、凭据或原始异常。

## Asset ID 强化

`SourceAsset.asset_id` 现在只接受有界 ASCII opaque identifier：

```text
A-Z a-z 0-9 - _ . ~
```

附加规则：

- 首尾不能为 `.`
- 不能包含连续 `..`
- 拒绝空值、空白、控制字符和非 ASCII
- 拒绝 URL/URI、scheme、network path、绝对路径、相对路径、drive path
- 拒绝 `/`、`\` 和任何 dot segment/path 形式

`external_id` 的既有兼容校验未改变。复杂 Provider remote ID 必须由未来 Adapter
映射为安全 opaque ID，不能放宽全局 DTO 边界，也不能把 asset ID 当作文件名。

## 确定性测试

新增 `tests/test_phase5_n4b.py`，只使用内存静态对象、synthetic marker 和
`.invalid` Host，不创建 Resolver 或 Transport，不访问 DNS、互联网或既有
`data/`。

覆盖：

- frozen/slots/type/版本/字段边界
- duplicate Host/operation、cross-layer、空 capability、无 Metadata operation
- wildcard/IP/scheme/path/non-443 Host
- Auth/OAuth/PKCE/password-storage/session-cookie policy
- unapproved Host/redirect/Asset Host 和 explicit exclusion
- Approval 与 Capability/Endpoint 完全一致及多项/少项/mismatch
- Provider/Host/Method/Encoding/Response/Auth/Cookie/Asset/limit/rate mismatch
- fixture activation 拒绝和未实现 capability 阻断
- secret marker 不回显、不记录 Approval repr
- 全部禁止 Asset ID 形式及正常 opaque ID
- `external_id` 兼容语义保持
- Production Registry 继续为空

本地最终结果：

- N4B focused：`27 passed`
- N4A + Adapter + Outbound regression：`120 passed`
- full pytest：`965 passed in 186.18s`
- `pip check`：`No broken requirements found.`
- `git diff --check`：通过

## 交接边界

N4B machine-checkable gate 不批准任何真实 Provider。真实 N4 仍必须由用户完整
填写并明确批准 `PROVIDER_APPROVAL_TEMPLATE.md`，再由未来代码定义 production
scope Approval 和同一 Provider 的 code-owned Capability/Endpoint；缺失或不一致
事实必须阻止启用。

本阶段唯一提交信息：

```text
Add provider approval validation
```

提交和推送后必须等待 GitHub Actions 的 `test` 与
`Docker production smoke` 均成功；不得创建 corrective commit。
