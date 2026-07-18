# Phase 5-N3 完成摘要：核心 Provider 合同、认证与下载需求规划

## 阶段结论

Phase 5-N3 已完成。阶段性质为静态审计、合同设计和文档规划；没有选择、
命名、搜索、访问、批准或实现任何真实 Provider，也没有实现认证、Secret
Vault、Discovery、资产解析、下载、UI、路由或后台任务。

本摘要取代本阶段的执行清单，作为 N4 的交接基线。规范正文见：

- `PROVIDER_CONTRACT.md`
- `PROVIDER_APPROVAL_TEMPLATE.md`

N4 不能在用户逐项完成并明确批准 Provider Approval 前开始。Codex 不得从
远程响应、普通 URL、用户输入或缺失信息推断 Provider、Host、Endpoint、认证
模式、下载能力、依赖、Schema 或关系模型。

## 基线与不变量

- N3 起始 SHA：`9d8656ffc0cf6adf9d669f5cdf844514ce001d94`
- 应用版本：`1.1.0`
- 当前 Schema：`4`
- Backup：`nsfwtrack.backup.v2`，继续接受 v1
- Production Provider Registry：空
- Phase 5-N1、Phase 5-N2、Phase 5-P2：已完成
- 稳定版本：`v1.1.0`
- N100：未部署
- Hermes：本阶段未调用、未编写

本阶段只允许新增或修改以下文档：

```text
PROVIDER_CONTRACT.md
PROVIDER_APPROVAL_TEMPLATE.md
GOAL.md
README.md
PLAN.md
TASKS.md
REVIEW.md
CHANGELOG.md
```

不得修改代码、测试、配置、依赖、Schema、Migration、Backup 实现、Adapter、
Endpoint Registry、Outbound HTTP、Provider Registry、路由、模板、i18n、
Docker、Compose 或 CI。不得创建 tag、Release 或部署 N100。

既有 `data/` 只属于用户本地数据。本阶段及后续验证不得读取、枚举、复制、
修改、删除、移动、格式化、暂存或提交其中任何内容；测试和 Docker 只能使用
独立临时目录或隔离数据卷。

## 现有代码审计结论

### Adapter 与 DTO

`app/source_adapters/contracts.py` 的 `SourceAdapter` 目前只有：

```python
async def search(query: str, *, page: int, page_size: int) -> SourceSearchPage
async def fetch_detail(external_id: str) -> SourceDetail
```

现有冻结 DTO 为 `SourceCreator`、`SourceTag`、`SourceSearchResult`、
`SourceDetail`、`SourceSearchPage`。当前不存在 capability manifest、认证
Adapter、Provider credential broker、Secret Store、Discovery、资源 DTO、
asset list/resolve 或 Download Adapter。

### Registry 与 Outbound

`app/source_adapters/registry.py` 当前只表达代码固定的 Provider key、ASCII
hostname、HTTPS/443、固定 path template、typed query/path 参数、required 参数、
JSON 顶层结构、响应大小和 page-size 上限，Production Registry 为空。

`app/services/outbound_http.py` 的 `OutboundRequest` 只接受 Provider key、
operation、query、external ID、page、page size。当前请求固定为 GET+JSON，使用
`trust_env=False`，关闭 auth、cookie、proxy、redirect、retry 和 HTTP/2，并
保持完整 DNS 集合拒绝、selected numeric IP pinning、TLS hostname/SNI/Host、
TCP/TLS peer 复核、3 秒 connect、10 秒 total、1 MiB stream、bounded
concurrency、immutable JSON、取消和脱敏日志。

当前公共 API 不接受 URL、Host、port、base URL、任意 path、method、body、header、
cookie、token、password 或下载 Locator。

### Schema、Backup 与本地媒体安全基座

Schema 4 的 `ItemSource` 只有来源 identity/check 字段：`provider_key`、
`external_id`、`last_checked_at`、`metadata_hash`；当 identity 两字段非空时
由 partial unique index 约束。当前没有 Provider、credential、secret、asset、
download 或 Provider-specific response 表。

`nsfwtrack.backup.v2` 只导出业务表和来源追踪字段，不导出 Secret Vault、凭据、
Locator、媒体索引内部状态或其他派生授权。Restore 使用 `BEGIN IMMEDIATE`、
事务内冲突重验、独立 Session 状态 digest，并区分 committed、committed after
error、confirmed rollback 和 unknown。

可复用但尚未构成下载实现的安全模式包括：

- `media_operation_lock()` 的跨进程锁、目录 FD、`O_NOFOLLOW`、owner/mode/link
  检查和锁对象映射重验；
- `coordinate_media_mutation()` 与 `synchronize_media_index_after_mutation()`
  的 post-mutation 刷新、unknown 失效和一次协调边界；
- `local_media` 的稳定 mode/device/inode、父目录 mapping、文件内容复核、
  no-overwrite 发布、fsync 和取消/清理失败处理；
- `media_directory_management.py` 与 `media_file_rename.py` 的
  `BEGIN IMMEDIATE`、精确 Item.cover_path / Creator.avatar_path 引用迁移、
  独立 Session commit outcome 复核、rollback 和现场保留；
- `backup.py` 的独立恢复 digest 与 unknown 结果分类；
- `local_media.py` 上传中的隔离临时文件、MIME/magic/hash 检查和内容寻址发布。

## N3 合同决策

### 五层能力

未来每个 Provider 都必须有 immutable、code-owned capability manifest。能力
分为 Metadata、Auth、Discovery、Asset、Download 五层。`search`、`detail`、
`discover`、`asset_list`、`asset_resolve` 和 `download` 是独立 operation，
每项都必须单独声明和批准；远程响应、用户表单和普通 URL 不能扩大能力。

Adapter 层职责为：

- `SourceMetadataAdapter`：把批准的 search/detail payload 映射为冻结 DTO，
  不写数据库、不写文件、不保存 raw response；
- `ProviderAuthAdapter`：只负责批准的开始、登录、测试、刷新、撤销/退出映射，
  不读取其他 Provider 秘密、不写普通 backup；
- `ProviderDiscoveryAdapter`：未来有限候选 discovery，默认不实现、不递归、不
  上传本地偏好、不自动收藏或下载；
- `ProviderAssetAdapter`：分离列出资源和解析短期 Locator，不把 URL 当作 asset ID；
- `ProviderDownloadAdapter`：声明资产、认证、精确 Asset Host、类型、大小、hash、
  Range 和 redirect 政策，实际字节流交给共享受控下载服务。

### 认证模式与状态

只规划下列 code-owned 模式：

```text
none
api_token
oauth
username_password
session_cookie
```

其中 `oauth` 的 state/PKCE、授权与 token Host、scope、refresh/revoke；
`api_token` 的固定注入位置；账号密码的登录交换和默认丢弃；Session Cookie
的显式导入/获批登录、Cookie Domain/Path/Secure/SameSite/expiry 和 Provider
隔离，都必须在 Approval 中逐项填写。

共同边界：合法用户授权、GET 零验证、秘密不进入 URL/query/log/exception/
request ID/普通 backup/config export、401/403 不自动删秘密、认证失败不影响
本地收藏、未配置或不确定时 protected operation fail closed。

认证状态固定为：

```text
not_configured / configured / valid / expired / invalid / revoked / unknown
```

`unknown` 不能推测为有效或撤销；页面加载不自动测试、登录或 refresh。

### Secret Vault 规划

推荐应用数据目录下独立的 Provider Secret Vault，由独立环境变量
`PROVIDER_SECRET_KEY` 提供加密主密钥。它不复用 `APP_PASSWORD` 或用于签名快照
的 `SECRET_KEY`。Vault 仅规划版本化 AEAD envelope，记录必须绑定 format、
Provider key、auth mode 和 purpose；文件/目录拒绝 symlink、hardlink、special
file 和不安全权限，使用目录 FD、`O_NOFOLLOW`、fsync、新 envelope 的
no-overwrite 创建和受控原子 replace/swap，写失败保留上一份有效秘密。

主密钥、envelope、认证状态和任何 Provider 秘密永不进入数据库、普通
`nsfwtrack.backup.v2`、普通配置导出、日志、异常或仓库。密钥丢失只影响认证，
不破坏业务数据库和本地媒体。N3 不实现 Vault，也不选择加密依赖。

### Typed Outbound 扩展

未来 Registry 只能由代码固定并冻结以下 typed policy：method（GET/POST）、
request encoding（固定 JSON 或 form schema）、auth requirement、fixed headers、
Provider-isolated cookie policy、response kind/content types/size、redirect policy
和 exact `allowed_asset_hosts`。不得开放用户自定义 method、body dictionary、
header map、Cookie header、proxy、URL 或 Host。

N1 的完整 DNS answer-set 验证、numeric-IP pinning、TLS certificate/SNI/Host、
TCP/TLS peer、timeout、stream limit、concurrency、HTTP/1.1、`trust_env=False`、
redirect/retry/.netrc 禁止、取消和日志脱敏必须保留。

### `SourceAsset` 与 Locator

未来 DTO 为 immutable、Provider-neutral 的 `SourceAsset`，至少含：

```text
provider_key, external_id, asset_id, kind, display_name, mime_type,
size_bytes, checksum_algorithm, checksum_value, requires_auth, downloadable
```

`asset_list` 只返回有界资源事实和 opaque Provider-scoped asset ID；
`asset_resolve` 只为已经选择的 asset ID 返回短期内部 Locator。`downloadable` 不
等于用户已确认下载。

Locator 是不可信输入，必须验证 HTTPS/443、无凭据/fragment/backslash/字面空白、
精确批准 Asset Host、固定 path/query grammar、expiry、Provider/external/asset/auth
绑定，并在传输时重做全套 DNS/IP/TLS/peer 检查。wildcard、suffix matching、
用户 Host、响应新增 Host、Locator 写入普通数据库/日志/backup 和未经批准的
redirect 扩权全部禁止。

### v1.2.0 下载 MVP

下载只接受用户主动确认的单项或 code-bounded 小批次，在同一请求内执行并传播
取消。GET 页面零 Provider 网络、零锁文件、零文件/数据库写入；Asset Preview
POST 只执行一次批准的 list/resolve；独立的 Download Confirmation POST 必须
验证登录、same-origin、purpose-specific HMAC snapshot、expiry、selected asset、
当前 auth/capability、限额和本地目标事实。

确认后，受控服务将字节流写入隔离临时区，执行实际字节上限、Content-Type、
magic/signature、本地 SHA-256 和批准的 Provider hash 检查。只有验证完成后才
取得 M4 媒体锁，重验根/父目录和目标不存在，以目录 FD 相对 no-overwrite 方式发布；
再在 `BEGIN IMMEDIATE` 内写入精确本地关系，验证关系集合并提交。提交异常以独立
Session 和文件稳定身份复核。释放锁前每个确认请求最多做一次 post-mutation 索引
协调：已知变化刷新，unknown 失效索引。

没有隐藏后台 worker、持久队列、页面关闭后继续、暂停/断点续传、自动 retry、
定时下载、启动恢复、推荐自动下载或无限批量。远程 filename 只作显示信息，不能
成为磁盘路径；不自动解压、执行、打开或作为模板处理；不以跨设备复制替代
no-overwrite rename/publish。

### 状态、结果与错误

文件状态为：

```text
not_started / temporary / validated / published / linked / failed / cancelled / unknown
```

结果至少区分：网络前无变化、临时失败后已清理、取消、已发布但关系未提交并已
安全补偿、`committed`、`committed_after_error`、`cleanup_failed`、
`download_outcome_unknown`。异常不等于 rollback；混合引用、无法独立复核、
文件身份不符或清理失败必须保留现场、按需失效索引并禁止普通成功提示。

稳定错误包括 `auth_not_configured`、`auth_invalid`、`auth_expired`、`auth_revoked`、
`auth_failed`、`provider_unavailable`、`rate_limited`、`invalid_provider_payload`、
`asset_not_found`、`asset_not_downloadable`、`asset_locator_invalid`、
`asset_host_not_allowed`、`download_too_large`、`download_type_rejected`、
`download_integrity_failed`、`download_cancelled`、`download_publish_failed`、
`download_link_failed`、`download_cleanup_failed`、`download_outcome_unknown`。
公共错误和日志都不得包含 query、external ID、username、URL/Locator、header、
cookie、token、password、raw response、完整路径、SQL、traceback 或原始异常。

## 签名快照与批准门禁

操作快照使用现有 `SECRET_KEY` 做 HMAC-SHA256，并以恒定时间比较验证；它不用于
加密 Provider 凭据。purpose 必须区分并版本化，例如：

```text
source_search_result.v1
source_import_preview.v1
provider_asset_preview.v1
provider_download_confirm.v1
source_update_preview.v1
```

快照绑定 format/purpose/version/expiry、Provider key、external ID、asset ID、
显示事实、批准限额、目标/引用冲突事实和安全 digest；不保存 password、token、
cookie、raw response、完整动态 Locator 或任何密钥。签名不能替代登录、same-origin、
当前 Host/capability allowlist、最终文件系统检查或关系复核。

`PROVIDER_APPROVAL_TEMPLATE.md` 是空白模板，用户必须逐项填写并批准：Provider
身份和 NSFW-core relevance、合法条款/归属、每个 metadata/auth/asset Host、每个
Endpoint 的 method/encoding/response/content-type/size/rate/redirect、认证和秘密
生命周期、Search/Detail/Discovery/Asset/Download 映射、Locator 规则、文件限额/
MIME/magic/hash/Range/naming/provenance、fixture 和完整故障矩阵、dependency/
Schema/Migration/Backup 影响、最终 N4 范围和明确授权。

## 阶段交接

### N4

只实现一份完整 Approval 明确批准的首个 Provider、capability、最小认证/Vault
需求、Search/Detail Adapter 和批准的 Asset metadata mapping，以及 fixture/mock
测试。缺少身份、Host、Endpoint、method、encoding、response type、认证生命周期、
法律/归属依据、fixtures、依赖或 Schema 影响时停止，不猜测、不搜索。

### N5

实现用户主动 Search/Detail UI、字段选择、signed import preview、zero-network
apply 和 Schema 4 `ItemSource` 关联；不自动下载。

### N6

实现 Asset Preview、signed confirmation、流式临时下载、校验、no-overwrite 发布、
精确关系、取消、一次索引协调和完整 outcome matrix；不引入隐藏 worker、未授权
依赖或 Schema。

### N7

实现用户主动 source check、signed diff、manual update、认证/下载安全收尾、
rate/abuse、i18n、无障碍、性能和相关回归；后台同步仍默认拒绝。

## 最终范围确认

- 本阶段只完成文档规划，不声称任何真实 Provider 或下载能力已存在。
- 应用版本保持 `1.1.0`，Schema 保持 `4`，Backup 保持 `nsfwtrack.backup.v2`。
- Production Provider Registry 保持空；不新增依赖、Schema、Migration、Backup、
  网络、AI、推荐、后台任务、tag、Release 或 N100 部署。
- 所有未来测试必须用静态 fixture、fake resolver/transport/clock 和隔离数据卷，
  不请求真实网络，不访问既有 `data/`。
- 本摘要与 N3 文档由同一阶段提交保存；GitHub Actions 的 `test` 和
  `Docker production smoke` 是阶段最终外部门禁，不改变本文合同。
