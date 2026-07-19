# Phase 5-N4D-C — Provider Package 绑定与离线激活门禁

## 完成摘要

Phase 5-N4D-C 已完成本地实现与验证。起始基线为
`5da317290de4a324f83ee4dda36f4f08d50929d4`，分支为 `main`。应用版本保持
`1.1.0`，Schema 保持 `4`，备份格式保持 `nsfwtrack.backup.v2`，
Production Registry 仍为 `EndpointRegistry(())`。

本阶段只建立 Provider-neutral、纯本地的 Provider Package 绑定和离线激活门禁。
没有选择、推荐、命名、研究、访问、实现或注册任何真实 Provider，也没有增加真实
Host、Endpoint、Header、URL、响应 Fixture 或网络权限。

## 实现内容

`app/source_adapters/package.py` 新增：

- frozen/slots `ProviderEvidenceManifest`；
- frozen/slots `ProviderFixtureEvidence`；
- bounded `ProviderEvidenceKind` 与 `ProviderFixtureOutcome`；
- frozen/slots `ProviderAdapterBinding` 与 `ProviderAdapterKind`；
- frozen/slots `ProviderPackage`；
- `validate_provider_package`；
- `build_endpoint_registry_from_packages`；
- `build_adapter_bindings_from_packages`；
- frozen/slots `ProviderPackageError` 与八个稳定
  `ProviderPackageErrorCode`。

`app/source_adapters/__init__.py` 只导出上述 Provider Package 公共合同，没有修改
`app/source_adapters/registry.py`、`app/services/outbound_http.py` 或任何生产
Registry 值。

## Evidence Manifest

`ProviderEvidenceManifest` 绑定 Provider key、scope、display name、content scope、
Approval ID、review revision、UTC review time、ordered operation tuple、fixture
evidence 和三项审查结论。所有集合均为 tuple，ID/revision 为有界 opaque identifier，
时间规范化为 timezone-aware UTC，文本有硬上限并拒绝控制字符。

Manifest 文本拒绝路径、URL、环境变量形式、dynamic include、模板/执行形式、
凭据样式内容和 JSON/XML 等原始响应形式；不保存 Header、Host、文件路径、原始
fixture 内容、Cookie、Token、Secret 或用户账号。notes 只作为可选审计文本，
不构成权限来源。

`ProviderFixtureEvidence` 只保存 operation、opaque fixture ID、64 字符小写
SHA-256、bounded kind 和稳定 expected outcome。kind/outcome 必须匹配；fixture ID
不可作为路径，operation + ID 不可重复，每个批准 operation 至少有一项 evidence。

## Package 与 Adapter Binding

`ProviderPackage` 精确绑定同一 Provider 的 typed Approval、Capabilities、
Endpoint、显式 Adapter Binding、Evidence Manifest 和独立 fixture digest catalog。
Provider key、display name、content scope、scope 与 ordered operations 必须一致；
Approval ID 必须与 Evidence 精确一致。

Adapter authority 只来自 `ProviderAdapterBinding.operations`。Source Metadata 和
Video Metadata Protocol 分开验证；Source Adapter 的静态 display name/capabilities
也必须与 Package 精确一致。Python 对象即使存在 download 等额外方法也不扩权，
`handler_for` 只分发 binding 明确批准的 search/detail/asset_list。构造、验证和
build 阶段均不执行任何 Adapter operation。

test-fixture Approval 继续由既有合同强制只使用 `.invalid` Host；production
Approval 继续拒绝 `.invalid` Host。production activation 仍调用既有
`validate_approval_for_activation`，test fixture 只执行 fixture-scope 一致性门禁，
不能伪装为 production activation。

## 离线门禁与错误模型

`validate_provider_package` 先执行精确对象类型、Provider identity、scope 和
operation parity 检查，再调用：

- `validate_provider_approval`；
- `validate_approval_against_capabilities`；
- `validate_approval_against_endpoint`；
- production scope 下的 `validate_approval_for_activation`。

随后验证显式 Adapter Binding、Evidence、operation 覆盖和 fixture digest。既有
`ApprovalValidationErrorCode` 作为稳定 `cause_code` 保留，不回显原始异常文本。
八个 package code 为：

```text
package_invalid
package_provider_mismatch
package_operation_mismatch
package_adapter_mismatch
package_evidence_mismatch
package_fixture_mismatch
package_duplicate_provider
package_not_activatable
```

`str(error)` 和 `repr(error)` 只包含稳定 code/cause code，不包含 Provider Host、
Header、fixture path、实际/预期 digest、marker 或对象 repr。

两个 builder 都先完整验证所有 Package，再检查重复 Provider key 并按 key 稳定排序。
任意 Package 失败时不构造、返回或写入部分 Registry/binding；空 tuple 分别返回空
`EndpointRegistry` 和空 binding tuple。全程不修改全局或 Production Registry。

## Fixture-only 证据

`tests/provider_package_fixture.py` 复用现有 N4A
`FixtureReferenceProvider` 和 N4D-B `FixtureVideoMetadataProvider`，定义两个
tests-only synthetic Package。它们只使用 `.invalid` Host，不进入生产 package 或
Registry。

固定 opaque ID 只映射到明确授权的九份仓库静态 fixture：N4A search/detail/assets
三份和 N4D-B video metadata 六份。Manifest 中 SHA-256 为硬编码审查值，测试侧才
读取固定映射并计算实际 digest；生产模块不导入路径、不读取 fixture、不扫描目录，
也不会自动更新或接受新 digest。fixture 内容变化会使固定 SHA-256 比较或 Package
validation 以稳定 mismatch 失败。

## 测试与文档

`tests/test_phase5_n4d_c.py` 覆盖：

- frozen/slots、tuple-only、无动态属性与 mutable collection 拒绝；
- opaque ID、SHA-256、UTC、有界文本、环境/路径/raw/sensitive 内容拒绝；
- Source/Video 完整 Package 与 Protocol 精确绑定；
- provider/display/content/scope/operation/Approval ID mismatch；
- binding 缺少或增加 operation、Adapter kind/key/capabilities mismatch；
- 额外 Adapter 方法不扩权且构造/验证/build 不执行 operation；
- fixture operation 覆盖、固定 digest、digest 变化与错误脱敏；
- 八类稳定 package error 和 Approval cause code；
- duplicate、stable sort、empty tuple、invalid second package 的 all-or-nothing；
- socket/DNS、HTTP client、Outbound client、SQLAlchemy、Path 读写与 Adapter
  operation forbidden 时仍可完成 validation/build；
- Production Registry 对象和值保持为空且未修改。

`PLAN.md`、`TASKS.md`、`REVIEW.md`、`CHANGELOG.md`、
`PROVIDER_CONTRACT.md`、Provider roadmap 和 video approval draft 已同步路线：

```text
N4D-A  Approval policy closure
N4D-B  Video Metadata DTO / fixture / merge framework
N4D-C  Provider Package binding and offline activation gate
N4D-D  One complete, explicitly approved real Video Metadata Provider package
```

N4D-D 仍要求用户明确批准 Provider identity、合法访问/条款、精确
Host/Endpoint/Header/Operation、脱敏静态 fixture、typed production Approval，并
通过全部 N4D-C Package 门禁。

## 长期边界

- 未修改 Registry、Outbound、ORM、路由、UI、认证、Vault、Schema、Migration、
  Backup、Docker、Compose、CI 或依赖。
- 不实现真实网络请求、DNS、数据库写入、Asset Resolve、播放、下载、后台任务、
  推荐、AI 或任意 URL/Host/Path 输入。
- 构造、validation 与 builder 零网络、零 DNS、零数据库、零文件写入；生产模块
  同时零 fixture 文件读取。
- 不调用 Hermes，不创建 tag/Release，不部署 N100。
- 既有未跟踪 `data/` 未读取、枚举、进入、复制、修改、移动、删除、暂存或提交；
  测试只使用仓库静态 fixture 和隔离临时资源。

## 验收记录

最终本地门禁：

- N4D-C focused：`38 passed`；
- N4A/N4B/N4D-A/N4D-B/N4D-C/Source Adapter/Outbound targeted：
  `285 passed`；
- full pytest：`1103 passed`；
- `pip check`：`No broken requirements found`；
- Application：`1.1.0`；
- Schema：`4`；
- Backup：`nsfwtrack.backup.v2`；
- Production Registry：`EndpointRegistry(())`；
- `git diff --check` 与允许文件范围审计通过。

唯一提交信息为：

```text
Add provider package activation gate
```

推送后仍需等待并记录 GitHub Actions `test` 与
`Docker production smoke` 均成功。不得创建 corrective commit、tag 或 Release；
最终工作区只允许保留既有 `?? data/`。
