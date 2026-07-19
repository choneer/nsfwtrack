# Phase 5-N4D-A - Approval 合同闭环完成摘要

## 完成状态

Phase 5-N4D-A 已完成本地实现、合同文档、测试和范围审计。本阶段只补齐首个真实
Provider 前的 Provider-neutral Approval 合同，没有选择、命名、研究、实现、访问
或注册任何真实 Provider。

起始基线：

```text
branch: main
start: 88de1a9bf047605f735595441f280366420dfa0c
application: 1.1.0
schema: 4
backup: nsfwtrack.backup.v2
production registry: EndpointRegistry(())
pytest baseline: 965 passed
```

## 修改文件

```text
GOAL.md
PLAN.md
TASKS.md
REVIEW.md
CHANGELOG.md
PROVIDER_CONTRACT.md
PROVIDER_APPROVAL_TEMPLATE.md
docs/provider-research/video-metadata-approval-draft.md
app/source_adapters/approval.py
app/source_adapters/__init__.py
tests/test_phase5_n4b.py
tests/test_phase5_n4d_a.py
```

未修改 `README.md`，因为现有顶层产品状态不需要重复 N4D-A 的实现细节。

## 固定非敏感 Header typed 合同

新增 frozen、slots、typed：

```text
ApprovedFixedHeader
ApprovedOperation.fixed_headers
```

`ApprovedFixedHeader` 要求：

- name 使用与 `EndpointOperation.fixed_headers` 相同的有界 Header 语法；
- value 非空、最多 512 字符、只允许 printable ASCII；
- CR、LF、NUL、DEL 和其他控制字符拒绝；
- value 不进入 dataclass repr；
- `ApprovedOperation.fixed_headers` 必须是 immutable typed tuple；
- 同名 Header 按大小写不敏感规则拒绝重复；
- 默认值为空，保持既有 Approval deny-safe 兼容。

继续拒绝现有 forbidden Header，并额外拒绝 credential-like Header name，包括：

```text
Authorization
Cookie
Set-Cookie
X-API-Key / API-Key
Auth Token
Access Token
Refresh Token
Client Secret
credential / password / session / token forms
```

固定 Header value 拒绝大小写不敏感的认证前缀：

```text
Bearer
Basic
Token
ApiKey
```

固定 Header 不是认证、Cookie、Token 或 Secret Vault 注入通道。

## Header canonical exact-match

`validate_approval_against_endpoint()` 将 Approval 与
`EndpointOperation.fixed_headers` canonical 化为：

```text
(header_name.casefold(), exact_header_value)
```

并排序后精确比较：

- Header name 大小写不敏感；
- Header value 大小写敏感；
- Header 顺序不影响结果；
- runtime 增加、减少、改名或改值均返回
  `approval_operation_mismatch`；
- runtime 是 Approval 子集时也失败，不允许静默收缩；
- 错误和日志只包含稳定错误码，不回显 Header value marker 或完整对象 repr。

N4B synthetic Approval/Endpoint 已最小同步，精确批准既有 N4A fixture search 的
`X-Fixture-Contract: n4a`，没有改变 N4A runtime Fixture 行为。

## Timeout typed 合同

新增：

```text
ApprovedTimeoutPolicy
ApprovedOperation.timeout_policy
```

规则：

- 数值必须有限且大于零，拒绝 `bool`、NaN、Infinity、零和负数；
- connect 上限 60 秒，total 上限 300 秒；
- total 不得小于 connect；
- 当前 Validator 精确绑定共享客户端实际常量：
  - `CONNECT_TIMEOUT_SECONDS = 3.0`
  - `TOTAL_TIMEOUT_SECONDS = 10.0`
- 任何常量 mismatch 返回 `approval_operation_mismatch`；
- 未修改 Outbound Client 常量、deadline、并发、重试或网络行为。

## Stable error mapping

新增 bounded enum：

```text
ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1
ApprovedOperation.error_mapping_profile
```

当前只允许：

```text
shared_outbound_v1
```

该 profile 固定使用共享 `OutboundErrorCode`/状态映射，不允许 Provider payload、
动态字符串或原始异常定义错误策略。Unsupported/mismatch 使用稳定
`approval_operation_mismatch`。

## Raw payload retention

新增 bounded enum：

```text
ApprovedRawPayloadRetention.DISCARD
ApprovedRawPayloadRetention.TEST_FIXTURE_ONLY
ApprovedOperation.raw_payload_retention
```

规则：

- production Approval 只能使用 `discard`；
- production 使用 `test_fixture_only` 时，纯本地 Validator/activation 返回
  `approval_incomplete`；
- `test_fixture_only` 只允许 `test_fixture` scope；
- 测试 fixture 必须继续为静态、脱敏、受审查内容；
- 未实现或授权任何生产 raw payload 数据库、文件、日志、异常或普通 Backup 持久化。

## Approval format 兼容决策

```text
APPROVAL_FORMAT_VERSION = 1
```

不需要升级版本。当前没有持久化或已批准的生产 Approval；新字段是代码级合同闭环，
并使用 deny-safe 默认值：

```text
fixed_headers = ()
timeout_policy = ApprovedTimeoutPolicy(3.0, 10.0)
error_mapping_profile = shared_outbound_v1
raw_payload_retention = discard
```

现有 N4A/N4B 行为和稳定 Approval 错误码保持兼容。

## 文档同步

已更新：

- `PROVIDER_CONTRACT.md`：Header exact-match、timeout、error profile、raw retention；
- `PROVIDER_APPROVAL_TEMPLATE.md`：typed 字段及当前唯一允许策略；
- `video-metadata-approval-draft.md`：placeholder-only N4D-A 字段；
- `PLAN.md`、`TASKS.md`、`REVIEW.md`、`CHANGELOG.md`：阶段状态与门禁证据。

视频 Approval 草案仍为 `draft / not approved`，没有真实 Provider、Host、Endpoint、
Header、凭据、payload 或 Fixture。

## 测试结果

```text
N4D-A focused:
64 passed in 11.16s

N4A + N4B + N4D-A + Adapter + Outbound:
211 passed in 29.85s

Full pytest:
1029 passed in 184.65s

pip check:
No broken requirements found.

git diff --check:
passed
```

测试覆盖：

- frozen/slots/typed/default Header；
- Header grammar、case/order、duplicate、empty/long/control/CRLF/NUL；
- 全部 forbidden/credential-like name；
- Bearer/Basic/Token/ApiKey value；
- runtime add/remove/rename/value mismatch 与 marker redaction；
- timeout valid/bool/zero/negative/NaN/Infinity/upper bound/ordering/constant mismatch；
- bounded error profile；
- production/test fixture raw retention 与 activation；
- zero DNS/network、空 Production Registry 和 unchanged outbound constants；
- N4A/N4B/Adapter/Outbound 完整回归。

## 保持的边界

静态复核确认：

- Application 仍为 `1.1.0`；
- `CURRENT_SCHEMA_VERSION` 仍为 `4`；
- Backup 仍为 `nsfwtrack.backup.v2`；
- Production Registry 仍为 `EndpointRegistry(())`；
- `CONNECT_TIMEOUT_SECONDS` 仍为 `3.0`；
- `TOTAL_TIMEOUT_SECONDS` 仍为 `10.0`；
- Provider concurrency 仍为 `1`；
- automatic retry 仍为 `0`；
- `app/source_adapters/registry.py` 未修改；
- `app/services/outbound_http.py` 未修改；
- 未新增依赖或修改 Schema、Migration、Backup、Docker、Compose、CI；
- 未实现真实 Provider、认证、Vault、UI、Asset Resolve、播放或下载；
- 未添加真实 Host、Endpoint、Header 或 Fixture；
- 未调用 Hermes；
- 未创建 Tag/Release；
- 未部署 N100；
- 既有 `data/` 未读取、枚举、进入、复制、修改、移动、删除、暂存或提交。

## 提交门禁

唯一提交信息：

```text
Close provider approval policy gaps
```

推送后等待 GitHub Actions `test` 与 `Docker production smoke` 均成功。
