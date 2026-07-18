# 规划结果：Phase 5-P1 - v1.2.0 外部内容源与统一搜索

## 阶段结论

Phase 5-P1 已完成现有代码、数据模型、迁移、备份恢复、本地来源导入、
页面、安全、Docker、CI 与相关测试的只读审计，并形成 v1.2.0 实施路线。
本阶段不实现功能。

- 当前正式稳定版：`v1.1.0`
- 当前应用版本：`1.1.0`
- 当前 Schema：`3`
- 下一目标版本：`v1.2.0`
- v1.1.0 annotated tag object：
  `07643bf6a7b36cb488c80c0ac694b6bc733e61e3`
- v1.1.0 peeled commit：
  `c1ff2760f8ee8ca988493aa04e8b4affbc4b4b9d`
- N100：未部署

此前的 `v2.0.0` 本地媒体关系化规划已作废。破坏性兼容变化仍可保留给
未来 v2.0.0，但不属于当前路线。

## v1.2.0 一句话目标

通过获批、代码固定、无需凭据的公开元数据 adapter，提供用户主动触发的
单来源和多来源搜索、只读预览、手动确认入库、来源追踪与手动确认更新。

## 已确认架构

- 使用 async `SourceAdapter` protocol：`search()` 与 `fetch_detail()`
- adapter 返回 immutable、provider-neutral 的 `SourceSearchResult`、
  `SourceDetail` 与 `SourceSearchPage`
- router 不包含 provider HTTP 或 parser 逻辑
- 所有 adapter 只能使用一个共享 `OutboundHttpClient`
- provider、HTTPS host、port 443、base path 和 endpoint 模板由代码固定注册
- 用户不能提供 scheme、host、port、API base URL 或任意 path
- 不创建 provider 数据库表，不持久化搜索结果或原始 HTTP 响应

## Outbound HTTP 边界

- 外部网络默认禁止，只允许当前阶段与用户共同批准的 adapter
- 只有登录用户主动提交的 POST 可以访问网络；GET 和页面加载零网络
- `trust_env=False`，不读取代理、浏览器配置、Cookie、Token 或账号
- 不发送 `Authorization`，不保存任何 provider 凭据
- 请求前解析并 pin 公开 IP，拒绝 loopback、private、link-local、multicast、
  reserved、unspecified 和不安全混合解析结果
- TLS hostname verification、SNI 与 Host 始终使用 allowlisted hostname
- redirect 默认关闭；获批时最多一次同 HTTPS host/port 且 endpoint 仍获批
- connect timeout 3 秒、total timeout 10 秒、响应上限 1 MiB
- 使用 identity encoding，只接受预期 JSON Content-Type
- query 最多 200 字符、page size 最多 50、一次最多 4 provider/4 并发
- DNS/security、timeout、401/403/404/429/5xx、redirect、content-type、
  malformed JSON 和 oversized body 使用稳定错误分类，不无限重试
- 日志只记录 provider key、operation、bounded status class、latency 与
  request ID，不记录 query、URL、external ID、response、header 或 signed token
- 测试只使用 mock transport / deterministic fixture，不访问真实 DNS/provider

## 用户流程与事务边界

```text
GET  /source-search                              local read only
POST /source-search                             network read only
POST /source-import/preview                     network read only
POST /source-import/apply                       local database write only
GET  /items/{item_id}/sources                   local read only
POST /items/{item_id}/sources/{source_id}/check network read only
POST /items/{item_id}/sources/{source_id}/update local database write only
POST /items/{item_id}/sources/{source_id}/remove local database write only
```

search / detail / check 与 apply / update 必须分为独立请求。网络 preview 生成
使用现有 `SECRET_KEY` 的 HMAC-SHA256 snapshot，包含明确 format、purpose、
version、expiry、provider/external ID、canonical mapped fields、目标 Item
快照和冲突事实，并使用恒定时间比较验证。snapshot 不保存 secret、凭据或
原始 provider response，也不能与其他 operation token 混用。

签名不能替代登录、same-origin 或事务内复核。apply/update 必须零网络，在
`BEGIN IMMEDIATE` 后重新验证目标 Item、provider/external ID、normalized URL、
Creator/Tag 与用户选择。

provider 空字段不能清空本地值。现有字段默认不覆盖，只允许用户逐项选择的
非空字段；Creator/Tag 只 additive 且必须预览，case-fold 歧义阻止写入。不
修改 status、rating、review、collections、media 或 extra data，不自动创建、
更新、合并或删除条目。

preview/check 不更新 `last_checked_at`。只有 confirmed apply 或未来明确的
confirmed mark-checked 操作才可在同一事务更新 `last_checked_at` 与
`metadata_hash`。后者是带格式版本的 canonical provider-neutral detail 字段
摘要，不是原始 response hash，也不包含未映射 payload。manual check 只使用
已注册的 `provider_key + external_id`，绝不获取 ItemSource 用户 URL 或任意 URL。

## Schema 4 与备份

Schema 4 直接扩展现有 `item_sources`，新增 nullable：

- `provider_key`
- `external_id`
- `last_checked_at`
- `metadata_hash`

新增 `(provider_key, external_id)` 双非空 partial unique index。provider key
是代码定义的小写标识，external ID 保持 provider 内 opaque、区分大小写。
Schema 3 旧行迁移后四列为 null。

迁移继续使用现有 registry、query-only preview、`BEGIN IMMEDIATE` apply、
precheck/postcheck、备份确认、版本记录和全链 rollback。必须验证 fresh 4、
1 -> 2 -> 3 -> 4、稳定 v1.1.0 3 -> 4、重复 apply 和未来版本拒绝。稳定
v1.1.0 必须拒绝 Schema 4。rollback 使用停机后的已验证 Schema 3 数据库副本，
不实现自动 downgrade。

v1.2.0 规划导出 `nsfwtrack.backup.v2`，包含来源追踪字段并继续接受 v1。
restore 零网络且事务化：payload 内重复身份为 validation error；与本地映射
完全相同的来源可复用/skip 并单独计数；指向不同 Item 或事实不一致的
normalized URL / provider-external-ID 冲突必须在 preview 阻止 restore。v1.2.0
备份不承诺可恢复至 v1.1.0，不能让旧版本静默丢弃 provider 元数据。

## 冲突与多来源结果

- 同 provider/external ID 在同 Item：reuse/no-op
- 同 provider/external ID 在其他 Item：hard conflict，零写入
- 同 normalized URL 在其他 Item：hard conflict，零写入
- 同 normalized URL 位于目标 Item 的 legacy null-provider row：只允许
  preview 后显式 enrichment，不静默重分配
- title similarity 只提示，不自动判断相同条目
- provider 失败相互隔离；支持 grouped view 与按 provider-local rank、registry
  order、external ID 的确定性 round-robin aggregate view
- exact canonical URL 只做视觉分组并保留全部 provenance
- 不持久化结果，不自动去重、合并或导入

## Provider 批准门禁

P1 与 N1 不实现真实 provider。每个 adapter 开始前必须由用户明确批准来源
与固定 endpoint，并确认公开合法、无需账号/Cookie/Token、无需 HTML 抓取、
具有稳定 ID 与 search/detail JSON、条款允许、无需远程图片且可完整 mock。

N3 需要首个获批 provider，N5 需要第二个获批 provider。未获批时停止，
不得自行选择替代来源。

## 阶段路线

1. Phase 5-N1：受控 HTTP、endpoint registry、adapter protocol、DTO 与错误模型
2. Phase 5-N2：Schema 4、ItemSource 追踪、backup v2 与冲突
3. Phase 5-N3：首个获批 adapter
4. Phase 5-N4：搜索 UI、signed preview 与手动入库
5. Phase 5-N5：第二个获批 adapter 与统一搜索
6. Phase 5-N6：手动 check / update / remove
7. Phase 5-N7：安全、i18n、响应式、日志与性能收尾
8. Phase 5-I1：完整集成冻结
9. Phase 5-R1：唯一一次 Hermes 最终独立验收
10. Phase 5-R2：v1.2.0 正式发布

普通阶段执行 targeted、相关回归、pip check、必要时隔离 Docker、Actions 与
云端 diff 复核。Schema/备份、跨模块大型阶段、I1 和 release candidate 才
要求本地全量 pytest。所有测试和 Docker 使用临时目录或隔离 volume，不接触
既有 `data/`。

P1、N1-N7、corrective 与 I1 均不得调用或编写 Hermes 验收。只有整个
v1.2.0 功能完成、全部 Actions 与云端复核通过、I1 集成冻结且无已知代码
阻塞后，R1 才可调用 Hermes 一次。

## 下一阶段入口：Phase 5-N1

下一正式目标是“Phase 5-N1 - 受控 HTTP 与 adapter 基础”。只允许实现共享
outbound client、固定 endpoint registry、SSRF/DNS/TLS/redirect/timeout/size/
Content-Type 防护、adapter protocol、provider-neutral DTO、稳定错误和 mock
测试；不得实现真实 provider、UI、Schema 4、备份 v2 或网络导入。

P1 不授权依赖变化。N1 若需要把当前开发依赖中的已固定 async client 提升为
runtime 依赖，必须在 N1 正式指令中明确审查和授权。开始 N1 前等待用户指令。

## 持续非目标

不实现通用 URL fetch、HTML crawler、remote images、credentialed provider、
cookies/tokens、automatic sync、background jobs、scheduled refresh、automatic
create/update/merge、recommendation、AI、cloud sync、multi-user 或 N100 部署。
R2 前不创建 v1.2.0 tag 或 Release。
