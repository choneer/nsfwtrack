# Phase 5-N4D-B — Video Metadata DTO 与 Fixture Adapter Framework

## 完成摘要

Phase 5-N4D-B 已完成。起始基线为 `ccb481a141370366d8cef0b6170586d7b157e938`，
分支为 `main`，应用版本保持 `1.1.0`，目标 Schema 保持 `4`，备份格式保持
`nsfwtrack.backup.v2`，Production Registry 仍为 `EndpointRegistry(())`。

本阶段只建立 Provider-neutral 的影视元数据数据层、解析边界和 fixture-only
测试框架；没有选择、命名、研究、访问或注册任何真实 Provider。

## 实现内容

- `app/video_metadata/contracts.py` 提供 frozen/slots DTO：
  `VideoIdentifier`、`VideoPerson`、`VideoOrganization`、`VideoSeries`、
  `VideoTag`、`VideoRating`、`VideoAsset`、`VideoMetadataProvenance`、
  `VideoSearchResult`、`VideoDetail` 和 `VideoSearchPage`。
- 所有集合均为 tuple；文本有硬上限并拒绝控制字符；Provider key 与外部身份
  按 Provider scope 验证；时间统一为 timezone-aware UTC；评分要求有限且在范围内；
  Asset ID 使用 opaque 约束，`requires_auth`/`downloadable` 固定为 `False`。
- `available_fields` 必须与实际非空字段完全一致；provenance 只能引用当前 DTO
  实际存在的字段和匹配的 Provider-scoped identity；DTO 不保存 raw Mapping、raw
  response、locator 或凭据。
- `VideoMetadataAdapter` 是 async Protocol，只声明独立的 `search`、`detail` 和
  `asset_list`，不接受任意 URL、Host、Header、Cookie、Auth 参数，也不负责写库。
- `app/video_metadata/merge.py` 提供纯函数 `VideoMetadataMergePlan`、
  `VideoFieldDecision`、`VideoFieldSource`、`VideoFieldAction` 和本地快照类型。
  计划保留用户编辑字段、把 missing/empty 视为不删除、不覆盖非空值；同一 Provider
  可更新自己的旧候选；不同 Provider 使用显式 priority；相同 priority 的冲突标记
  `conflict`；people/organization/series/tag 使用 Provider-scoped identity；Asset
  只产生关联计划，不 resolve、播放或下载。计划顺序稳定且不写 ORM、数据库或文件。
- `tests/video_metadata_fixture_provider.py` 仅读取仓库内合成 JSON fixtures，完全分离
  `search`/`detail`/`asset_list`，不调用 DNS、socket、httpx 或 `OutboundHttpClient`。
  malformed、missing、wrong-type、duplicate 和 oversized payload 统一转为稳定的
  `ProviderAdapterError(INVALID_PROVIDER_PAYLOAD)`，异常不回显原始 marker。

## 测试与文档

静态 fixtures 位于 `tests/fixtures/video_metadata/`：search success/empty、detail
complete/partial、asset list success 和 invalid payload。新增 `tests/test_phase5_n4d_b.py`
覆盖 DTO 不可变性、tuple-only、边界、UTC、评分、identity、字段/provenance 一致性、
fixture 错误脱敏、零网络、操作分离和 merge 矩阵。

`PLAN.md`、`TASKS.md`、`REVIEW.md`、`CHANGELOG.md`、`PROVIDER_CONTRACT.md` 与
视频 Provider 研究/路线文档已同步 N4D-B 完成状态和后续真实 Provider Approval 门禁。

## 长期边界

- 未修改 `app/source_adapters/registry.py`、`app/services/outbound_http.py`、ORM、
  路由、UI、认证、Vault、Schema、Migration、Backup、Docker、Compose、CI 或依赖。
- 不新增真实 Host、Endpoint、Header、URL、Provider response、网络权限、后台任务、
  Asset Resolve、播放、下载、推荐或 AI。
- 不调用 Hermes，不创建 tag/Release，不部署 N100，不读取或接触既有 `data/`。
- 测试只使用仓库静态合成 fixtures；既有 `data/` 不作为测试或 Docker 数据目录。

## 验收记录

本地门禁结果：

- N4D-B focused：`26 passed`；
- N4A/N4B/N4D-A/N4D-B/Source Adapter/Outbound targeted：`237 passed`；
- full pytest：`1055 passed`；
- `pip check`：`No broken requirements found`；
- 所有六份静态 fixture 均通过 JSON 解析；
- `git diff --check` 与最终范围审计在暂存前通过。

推送后仍需记录 GitHub Actions `test`/`Docker production smoke` 结果。唯一提交信息为：

```text
Add video metadata contract framework
```

不得创建 corrective commit。完成提交前，GOAL 白名单文件以外不得出现 tracked
修改，既有未跟踪 `data/` 保持原样且不暂存。
