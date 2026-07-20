# Phase 5-N5C-A — Signed Provider Apply Plan Foundation

## 完成状态

Phase 5-N5C-A 已完成本地实现与验证。N5C-B 数据库重验和事务写入尚未实现。

保持不变：

```text
Application: 1.1.0
Schema: 4
Backup: nsfwtrack.backup.v2
Production Registry: EndpointRegistry(())
Production Search Packages: ()
Production Search Providers: ()
```

## 已完成实现

- 新增 `app/provider_apply/contracts.py`：
  - frozen/slots `ProviderApplyAction`、`ProviderApplyFieldPolicy`；
  - immutable Item/ItemSource snapshot、field change、duplicate-title hints；
  - immutable create/update `ProviderApplyPlan`；
  - stable redacted `ProviderApplyErrorCode` / `ProviderApplyError`。
- 新增只读 `build_provider_apply_plan`：
  - 只接受 exact `VideoDetailEnvelope`；
  - 重新验证 descriptor/request/detail identity；
  - canonical URL 必须存在且只使用现有 `normalize_source_url` 的结果；
  - 不访问或跟随 URL，不保存 raw URL；
  - 只执行 Provider identity source、normalized URL source、linked Item、exact-title
    Item IDs 四类 SELECT；
  - 显式禁用并恢复 Session autoflush；
  - 不调用 add/add_all/delete/flush/commit/rollback，不执行 SQL mutation。
  - identity source 与 normalized URL source 查询均使用稳定 `ORDER BY ItemSource.id ASC`
    和 SQL `LIMIT 2`；0/1/2 行分别表示 absent/unique/conflict，超过一行稳定为
    `database_state_invalid`，不先加载无界结果。
- create 只有在 identity 与 URL 同时不存在时生成；相同 title 只产生稳定、升序、
  最多 32 个提示，不自动关联 Item。
- update 要求 identity source、URL source、stored URL、normalized URL 与 linked Item
  精确一致；Item.title 永远 keep-local，summary/release_date 仅 fill-blank，Source
  只允许计划刷新 last_checked_at 与 metadata_hash。
- apply projection hash 固定为 `v1:sha256:<64 lowercase hex>`，只覆盖 Provider key、
  external ID、normalized URL、title、summary、release date、received/source-updated
  time；不是完整 Provider response hash。
- canonical plan serialization/parser：
  - exact bytes-only、UTF-8、canonical Unicode JSON；
  - nested duplicate-key、unknown/missing field、bool/int 混淆、NaN/Infinity 拒绝；
  - 深度、节点、单字符串、数组与 32 KiB 总字节上限；
  - typed parity 和 parse → serialize 收敛。
- `nspap1` HMAC token：
  - 固定 HMAC-SHA256 与 domain separation；
  - secret 必须为 exact bytes、至少 32 bytes；
  - purpose context 参与绑定但不以明文写入 Token；
  - 默认 TTL 600 秒、最大 900 秒；
  - 使用 `hmac.compare_digest`；
  - wrong secret/context、payload/MAC 篡改、未来签发、过期、非法 schema/资源均拒绝；
  - Token 可解码，只提供完整性，不提供加密或保密。
- corrective fix 已完成：
  - `ProviderApplyPlan.has_writes` 严格等于任一 field change 的 `will_write`；无变化
    update Plan 仍可展示、serialize/parse round-trip，但 sign/verify 均稳定返回
    `nothing_to_apply`，不能进入可执行 Token；create、fill_blank 和 tracking-only
    update 仍可签名验证。
  - Builder 在 URL 处理和数据库查询前重建并验证 exact Provider/Request/Detail 及其
    nested DTO、合法 operation tuple、DETAIL authority、Provider key 与 external ID；
    类型/字段/authority 篡改均稳定脱敏失败，不抛 AttributeError 或原始异常。

## N5C-B 强制合同

N5C-B 写入前必须：

1. 验证 Token，且不重新调用 Provider；
2. 重读 identity source、URL source、linked Item 与 duplicate-title IDs；
3. 与 Token 中 snapshot 和读写字段逐项比较；
4. 任一变化返回 `stale_plan`，零写入；
5. create 再确认 identity/URL 均不存在；
6. update 再确认 source/URL/Item 与本地字段精确一致；
7. 在单一事务中执行有限写入；
8. 唯一约束冲突或任一写入失败必须完整 rollback；
9. commit 后只返回 bounded result；
10. Token 重放必须因数据库状态已变化而失败。

签名有效只证明应用签发与 Token 完整性，不等于当前数据库状态有效。

## 本地验证

```text
Phase 5-N5C-A focused: 73 passed
N4D-C / N4D-D-A / N5A / N5B / N5C-A: 240 passed
Full suite: 1305 passed
pip check: No broken requirements found.
git diff --check: passed
```

专项测试验证成功和失败路径调用前后数据库 snapshot 完全一致，SQL 仅为 SELECT；
Provider/Outbound、DNS、文件读写、dynamic import 与 Adapter operation 均为 0。

## 安全与范围确认

- 未修改 models、database、sources、source_search、source_adapters、video_metadata、
  routers、templates、i18n、main 或 config。
- 未新增 Apply Router、按钮、表单或任何生产数据库写入。
- 未接入真实 Provider，未添加真实 Host/Endpoint/URL/response/fixture，未访问
  canonical URL。
- 未新增依赖、Schema、Migration、Backup format、Docker、Compose 或 CI 变化。
- 未读取、枚举、进入、修改、暂存或提交既有 `data/`。
- 未调用 Hermes；未创建 Tag/Release；未部署 N100。

## 提交与云端门禁

原始提交信息：

```text
Add signed provider apply plan foundation
```

追加 corrective 提交信息：

```text
Harden signed provider apply plan invariants
```

corrective 使用普通追加提交和 fast-forward 推送；不得 amend 或 force push。推送后
等待 GitHub Actions `test` 与 `Docker production smoke` 均成功。
