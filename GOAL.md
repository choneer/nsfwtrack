# Phase 5-N5C-B1 — Transactional Provider Apply Service

## 完成状态

Phase 5-N5C-B1 已完成并通过本地门禁。本阶段只实现服务层，不实现页面、Router、
按钮、表单、模板、JavaScript 或真实 Provider。

基线与不变项：

```text
repository: /home/nsfwtrack
branch: main
base: 433e4b1c2bc9e58816df237a26a91e88082f39e0
Application: 1.1.0
Schema: 4
Backup: nsfwtrack.backup.v2
Production Endpoint Registry: EndpointRegistry(())
Production Search Packages: ()
Production Search Providers: ()
```

起始工作区预置修改为 `GOAL.md`，并有既有未跟踪 `data/`。该 `data/` 属于用户本地
数据，本阶段没有读取、枚举、进入、复制、修改、移动、删除、格式化、暂存或提交
其中任何内容。测试使用 pytest 隔离临时数据库；没有向既有 `data/` 写入测试文件。

## 实现

新增或更新的唯一授权代码/测试文件：

```text
app/provider_apply/transaction.py
app/provider_apply/contracts.py
app/provider_apply/__init__.py
tests/test_phase5_n5c_b1.py
```

公开服务入口为：

```python
apply_provider_apply_token(
    db,
    token,
    *,
    secret,
    context,
    now,
    verification_session_factory,
) -> ProviderApplyResult
```

### Token-first 与事务边界

- 先调用既有 `verify_provider_apply_token`；在验签失败、过期、错误 context/secret、
  no-op 等路径，不访问 DB、Session transaction、Provider、Outbound、网络、文件或
  dynamic import。
- 验证后拒绝 `new/dirty/deleted` 的调用方 Session、既有 transaction、非 SQLite bind、
  非 callable verification factory 和没有 `will_write=True` 字段的 Plan；不替调用方
  自动 rollback/commit 或吸收其 pending 状态。
- 所有业务 SELECT/INSERT/UPDATE 前执行 SQLite `BEGIN IMMEDIATE`。不使用无锁
  read-then-write，也不改变 engine/global isolation level。

### Exact stale revalidation

写锁内重新读取并比较：

- Provider identity source：`provider_key + external_id`、`ORDER BY id ASC LIMIT 2`；
- normalized URL source：`ORDER BY id ASC LIMIT 2`；
- linked Item：按 snapshot ID 读取 title、summary、release_date，并保留 cover/extra
  的当前值用于 post-state 保护；
- duplicate-title Item IDs：`ORDER BY id ASC LIMIT 32`。

create 必须再次证明 identity、URL 均不存在且 duplicate-title ID tuple 未改变；不得
按标题关联已有 Item。update 必须再次证明 source ID、item ID、Provider identity、
raw/normalized URL、tracking values、linked Item title/summary/release_date 和
duplicate-title tuple 全部匹配。任一合法快照变化返回 `stale_plan`，且不产生业务
写入；多行或损坏数据库状态返回 `database_state_invalid`。

### 最小写入白名单

create 只用固定列 INSERT 创建一个 Item 和一个 ItemSource：

- Item：title，以及 Plan 中实际存在的 summary/release_date；不写 cover_path/extra；
- ItemSource：item_id、url、normalized_url、title、provider_key、external_id、
  last_checked_at、metadata_hash。

update 只写 Plan 中 `will_write=True` 的以下字段：

- `Item.summary`
- `Item.release_date`
- `ItemSource.last_checked_at`
- `ItemSource.metadata_hash`

Item.title、cover_path、extra，ItemSource URL、normalized URL、title、Provider identity，
以及 Tag、Creator、Collection、State、Activity、Media 或任何关系表都不修改。不会
执行 DELETE/DDL、目录/文件操作、标题合并、覆盖或第二个 ItemSource 创建。

### Post-state、commit 与异常分类

- flush 后、commit 前在同一事务中重新读取并证明 exact expected post-state；post-check
  不通过时不返回普通 success。
- `commit()` 正常返回也必须由独立、clean、同 bind 的 verification Session 通过有界
  SELECT 证明 durable post-state；factory/session/lifecycle/state proof 失败返回
  `commit_state_unknown`。
- flush/commit/post-check/rollback 异常后，先由独立 Session 证明 exact post-state，再
  证明 exact pre-state；不得用异常类型或 commit 返回值替代事实：

| 独立事实 | 返回 |
|---|---|
| exact post-state，commit 正常 | `committed` |
| exact post-state，commit 抛异常 | `committed_verified_after_exception` |
| exact pre-state，Integrity/唯一约束失败 | `write_conflict` |
| exact pre-state，其他写入失败 | `write_failed` |
| pre/post 均不能证明 | `commit_state_unknown` |

异常、SQL、Provider identity、URL、title、Token、Secret、context 和 marker 不进入
稳定错误文本、Result、`str`、`repr` 或日志。

## Result 与 replay 合同

新增 frozen/slotted/redacted `ProviderApplyResult`：

```text
format: nsfwtrack.provider-apply-result
version: 1
action: create_item | update_item
item_id: positive integer
source_id: positive integer
written_fields: exact non-empty tuple in Plan order
commit_status: committed | committed_verified_after_exception
```

`written_fields` 严格等于 Plan 中 `will_write=True` 的字段顺序，不包含 Token、Secret、
context、URL、external ID、title、SQL 或原始异常。成功 create/update 后使用同一 Token
重放必须返回 `stale_plan`，不得第二次写入或新增 ItemSource。

## 外部副作用与长期边界

- 不重新调用 Provider，不注册或激活真实 Provider，不增加网络、爬虫、远程媒体、
  识别、推荐、AI、多用户、云同步、下载、播放或后台任务。
- 不新增依赖、Schema、Migration、Backup format、Docker/Compose/CI 行为。
- 不从环境、Request、Session、文件或 Registry 自动派生 secret/context。
- 不创建 Tag/Release，不部署 N100，不调用或编写 Hermes 验收。
- 未创建、读取或输出任何凭据。

## 验证结果

```text
focused: 47 passed
specified N4D/N5A/N5B/N5C regression set: 287 passed
full pytest: 1352 passed
pip check: passed
git diff --check: passed
Application: 1.1.0
Schema: 4
Backup: nsfwtrack.backup.v2
Production Registry/Packages/Providers: empty
```

N5C-B1 的本地实现和验证完成。N5C-B2 仍待独立授权，范围为显式 Preview/Confirm
routes、session-bound secret/context 派生、模板、i18n 与用户可见结果；B2 不得弱化
本摘要中的 Token-first、`BEGIN IMMEDIATE`、字段白名单、独立状态证明、replay rejection
或 `data/` 边界。
