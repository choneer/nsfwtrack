# 阶段结果：Phase 5-N1 - 受控 HTTP 与 Adapter 基础

## 完成结论

Phase 5-N1 已实现 provider-neutral 的受控外部元数据访问底座。生产 registry
保持为空，因此当前应用没有任何真实 provider 或可达的外部请求目标。

- 阶段起始 SHA：`2f1310475db225ce65fd90397aebd98885c81e74`
- 当前稳定版：`v1.1.0`
- 应用版本：`1.1.0`
- Schema：`3`
- 下一目标：Phase 5-N2 - Schema 4 来源追踪
- N100：未部署

## 依赖结果

- 将现有固定版本 `httpx2==2.5.0` 从开发依赖提升为 runtime 依赖
- `requirements-dev.txt` 继续通过 `-r requirements.txt` 继承，不重复声明
- 未升级 httpx2，未增加其他直接第三方依赖或 optional extra
- httpx2 精确依赖 `httpcore2==2.5.0`；实现只使用两者顶层公开 transport、
  connection pool、network backend 和 network stream API，不访问私有模块/属性

## Adapter contract 与 DTO

新增 `app/source_adapters/`：

- async runtime-checkable `SourceAdapter` protocol
- frozen `SourceCreator`、`SourceTag`、`SourceSearchResult`、`SourceDetail`、
  `SourceSearchPage`
- 所有集合字段使用 tuple，字符串、数量、日期和 timezone-aware datetime 有界
- DTO canonical URL 仅接受无凭据、无 fragment、无字面空白或反斜杠的
  HTTP/HTTPS URL
- DTO 不含 HTTP client、数据库 Session、Cookie、Token、Header、原始 response
  或 provider-specific 未映射 payload

## 固定 endpoint registry

- `EndpointRegistry`、`ProviderEndpoint`、`EndpointOperation` 均为 immutable
- registry 只接受代码固定的 lowercase provider key、ASCII hostname、port 443、
  可打印 ASCII 固定 path template、固定 operation 和固定 query 参数映射
- path 参数只能按 operation 声明后单独 percent-encode
- client 公共请求只有 provider key、operation、query、external ID、page 和
  page size；没有 URL、scheme、host、port、base URL、path、header、proxy、
  Cookie 或 auth 参数
- `PRODUCTION_ENDPOINT_REGISTRY` 精确为空，不包含真实 provider、hostname 或
  endpoint

## DNS、连接绑定与 TLS

每个逻辑请求执行：

1. registry/参数检查，unknown/invalid 在 DNS 前拒绝
2. 可注入 resolver 返回本次 A/AAAA 全部结果
3. 任一结果为空、不可解析或非公网单播，整组拒绝；不筛掉危险结果后继续
4. 保留全部批准地址并确定一个 selected IP
5. 新建一次性 HTTP/1.1 connection pool，retries=0、keepalive=0
6. pool origin 和请求 URL 保持 allowlisted hostname
7. 公开 network backend 将唯一 TCP connect 的 host 替换为 selected 数值 IP
8. TCP 后通过 `get_extra_info("server_addr")` 验证 peer 精确等于 selected IP:443
9. TLS `server_hostname` 仍为 allowlisted hostname，SSLContext 强制
   `check_hostname=True` 与 `CERT_REQUIRED`
10. TLS 后再次验证 peer 精确等于 selected IP:443
11. HTTP Host 保持 allowlisted hostname，请求完成后关闭 stream/client/pool

因此不存在“预解析后仍按 hostname 普通连接”的降级路径，也不会进行第二次
连接尝试或自动重试。

## HTTP 边界

- `trust_env=False`、proxy=None、auth=None、cookies=None
- 不读取 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY 或 `.netrc`
- provider `Set-Cookie` 不跨逻辑请求保留
- HTTP/1.1 only，HTTP/2/SOCKS/CLI extras 未启用
- redirect 完全禁止；所有 3xx 为 `redirect_blocked`，不读取或跟随 Location
- connect timeout 3 秒，total deadline 10 秒
- total deadline 覆盖 semaphore、DNS、connect、TLS、headers、body streaming 与
  JSON decode
- 全局并发 4、单 provider 并发 1
- query 最大 200、page >= 1、page size 最大 50
- 发送 `Accept-Encoding: identity`，拒绝非 identity Content-Encoding
- 只接受 `application/json` 与 `application/*+json`，允许 charset 参数
- 正文逐 chunk 在复制前检查，最大 1 MiB；完整限额后才解析 JSON
- operation 固定顶层 JSON object/array 类型；重复 object key、非有限数和
  递归异常拒绝，成功解析结果递归冻结

## 稳定错误与日志

已实现固定错误码：

```text
provider_not_allowed
operation_not_allowed
invalid_request
dns_resolution_failed
unsafe_address
peer_address_mismatch
connect_timeout
request_timeout
tls_failed
connection_failed
redirect_blocked
unauthorized
forbidden
not_found
rate_limited
provider_server_error
unexpected_status
unexpected_content_type
unexpected_content_encoding
response_too_large
malformed_json
invalid_payload
cancelled
```

错误只携带 sanitized provider/operation、有效 request ID、bounded status 与安全
Retry-After 秒数。日志只记录 provider、operation、outcome、status class、latency
bucket 和 request ID，不记录 query、URL、path value、external ID、response、
headers、DNS 地址或原始异常文本。

## 验证结果

- N1 专项：`99 passed`
- release security / error handling / security headers / config：`66 passed`
- `pip check`：`No broken requirements found`
- 所有 outbound 测试使用 fake resolver、fake clock、MockTransport 或实现公开
  network backend 接口的 fake stream；未请求真实 DNS、localhost 测试服务或
  互联网
- connection 测试真实经过自定义 httpx2/httpcore2 transport，不通过 monkeypatch
  绕过 pinning 核心
- 隔离 Docker：build 成功、两个 container lifecycle healthy、`/login` 200、runtime import
  httpx2 2.5.0、应用 1.1.0、Schema 3、UID/GID 10001、read-only root、
  `CapEff=0`、no-new-privileges
- Docker 上下文和数据使用独立临时目录；临时容器、镜像和目录已清理
- 既有 `data/` 未进入、读取、枚举或修改

## 未实现范围

本阶段没有实现：

- 真实 provider、provider 名称或生产 endpoint
- 页面、路由、导航、外部搜索或详情 UI
- signed import preview、Item 写入或手动更新
- models、Schema 4、迁移或 backup v2
- remote image、credential、Cookie、automatic sync、background job
- tag、Release 或 N100 部署
- Hermes 验收或提示词

## 下一阶段入口：Phase 5-N2

下一正式目标为“Phase 5-N2 - Schema 4 来源追踪”。范围应限定为：

- Schema 3 -> 4 连续迁移
- 为 `item_sources` 增加 nullable `provider_key`、`external_id`、
  `last_checked_at`、`metadata_hash`
- 双非空 `(provider_key, external_id)` partial unique index
- backup v2、v1 restore 兼容与精确冲突报告
- 稳定 v1.1.0 对 Schema 4 的 future-schema 拒绝

N2 不实现真实 provider、网络搜索或 UI。开始 N2 前等待用户正式指令。

Hermes 在 Phase 5-N1-N7、corrective 与 I1 全部期间继续禁止；只有整个
v1.2.0 功能、Actions、云端复核和 I1 集成冻结全部完成后，Phase 5-R1 才能
调用一次。
