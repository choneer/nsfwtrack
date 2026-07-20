# Phase 5-N5B — Search/Detail Empty-State and Approved-Provider UI

## 完成状态

Phase 5-N5B 已按授权范围完成本地实现与验证。

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

- 新增 `app/routers/source_search.py`：
  - `GET /source-search`
  - `POST /source-search/search`
  - `POST /source-search/detail`
  - `get_provider_search_service` 生产依赖只构造
    `build_production_search_service()`；测试仅通过 FastAPI
    `dependency_overrides` 注入 tests-only Service。
- GET 只调用 `list_providers()`；生产空 catalog 返回 HTTP 200 普通空状态
  “暂无可用外部来源”，不显示 synthetic Provider，不执行 Provider operation。
- Search 与 Detail 均由登录用户显式 POST 触发，分别通过 N5A request contract、
  当前 Provider catalog 和批准 operation 前置复核；每个请求只调用对应 Service
  operation 一次。
- Search 不自动 Detail，Detail 不自动 Asset List，返回 GET 不恢复或重复请求。
- 新增 `app/templates/source_search.html`，复用现有 Jinja/CSS/导航/认证/i18n：
  - Provider 与结果文本保持自动转义；
  - canonical URL 不成为链接；
  - cover/preview/asset 不成为远程图片、播放源或下载入口；
  - Detail 只展示 kind、display name、MIME、尺寸、时长等非 locator Asset facts；
  - 不新增 JavaScript、外部 CSS、字体、图片或脚本。
- 七类可渲染 `ProviderSearchServiceErrorCode` 映射为稳定、脱敏的
  400/409/502/503 中英文状态；query、external ID、cause、Provider marker、Host、
  payload 和异常文本不进入错误 HTML 或日志；`asyncio.CancelledError` 原样传播。
- 路由不依赖数据库，不保存 Search/Detail 响应到 DB、Session、Cookie、文件、
  cache 或 localStorage，不实现 import、Asset Resolve、播放、下载或后台任务。
- 更新 `app/main.py`、`app/templates/base.html` 和 `app/i18n.py`，新增中英文
  “外部来源 / External Sources”导航和完整页面文本。
- 新增 `tests/test_phase5_n5b.py`，覆盖认证、空状态、dependency override、
  operation 次数、分页 POST、XSS 转义、远程资源禁用、稳定错误、取消传播、
  零数据库/文件/Outbound 副作用及生产不变量。

## 本地验证

```text
Phase 5-N5B focused: 38 passed
Phase 5-N5A + N5B: 71 passed
Auth / Security Headers / Pages regression: 37 passed
Full suite: 1232 passed
pip check: No broken requirements found.
git diff --check: passed
```

## 安全与范围确认

- 未修改 `app/source_search/contracts.py`、`app/source_search/service.py`、
  `app/source_adapters/*`、`app/services/outbound_http.py`、数据库或模型文件。
- 未添加真实 Provider、Host、Endpoint、URL、response、fixture、认证、Cookie、
  Token、Secret Vault、网络入口、远程媒体、播放、下载、导入、缓存或后台任务。
- 未新增依赖、Schema、Migration、Backup、Docker、Compose 或 CI 变化。
- 未读取、枚举、进入、修改、暂存或提交既有 `data/`。
- 未调用 Hermes；未创建 Tag/Release；未部署 N100。

## 提交与云端门禁

唯一提交信息：

```text
Add provider search and detail UI
```

推送后等待 GitHub Actions `test` 与 `Docker production smoke` 均成功；不得
amend、force push 或创建 corrective commit。
