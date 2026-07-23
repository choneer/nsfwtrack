# Production path roadmap (`nsfwtrack_grok`)

**Application 1.5.0** (Schema 5) is the formally released application.
It includes CookieCloud, egress diagnostics, HLS/playback inspect, reviewed
nsfwpro identity mappings, and a `copymanga` package contract. All production
runtime catalogs remain empty.

The latest stable version and GitHub Release are both `v1.5.0`. No production
image has been published, and N100 has not been deployed.

## Product scope (confirmed)

1. **Cookie + metadata scrape first** — operator session cookie; SEARCH + DETAIL HTML.
2. **Video** — `ASSET_LIST` surfaces **non-downloadable link descriptors**; **optional** local `DOWNLOAD` via acquisition after explicit confirm.
3. **Comics / doujin** — separate package; local fixture tests prove the path, while `copymanga` remains unactivated.
4. **No VIP / login / paywall bypass.**
5. **JP/KR egress** for JavDB (operator proxy; `/egress`).
6. **CookieCloud** and **HLS inspect** are control planes (not Providers).

## Default catalog (1.5.0)

| Provider key | Scope | Default process mode | Notes |
|--------------|-------|----------------------|--------|
| `javdb_metadata` | PRODUCTION identity | **not_configured** | A cookie may be loadable, but no controlled runtime is activated |
| `jiuse_vod` | TEST_FIXTURE | **not_configured** | Offline tests only; live unauthorized |
| `zuidapi_vod` | PRODUCTION identity | **not_configured** | Package tests require an explicitly injected fetcher |
| `copymanga` | PRODUCTION identity | **not_configured** | Package tests require an explicitly injected fetcher |
| `comic_local_fixture` | TEST_FIXTURE | **not_configured** | Local tests only |

**Endpoint registry:** empty.

**Search and acquisition packages:** empty.

Operator readiness (no secrets): `GET /api/providers/readiness` and the CookieCloud page.

## Phase status

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **A** | Reviewed PRODUCTION facts; SEARCH+DETAIL+optional ASSET_LIST | **Contracts complete; runtime not activated** |
| **B** | Async adapter + cookie loader + package builder | **Explicit injection tests only** |
| **C** | Video ASSET_LIST + optional acquisition DOWNLOAD | **Contract tests only** |
| **D** | Comic package + local DOWNLOAD acquisition | **Contract/fixture tests only** |
| **E** | CookieCloud import + HLS/playback-line inspect (no segment fetch) | **Done** (1.5.0) |
| **F** | Catalog readiness honesty + CookieCloud operator UI | **Done** (1.5.0 engineering close) |

## Runtime (1.5.0)

```bash
export NSFWTRACK_JAVDB_SESSION_COOKIE='name=value; ...'   # readiness only
# optional explicit proxy for CookieCloud / egress control planes:
export NSFWTRACK_HTTP_PROXY=http://127.0.0.1:6123
# optional CookieCloud import → data/cookies/javdb_metadata.cookie
```

```python
from app.source_search import build_production_search_service
from app.acquisition.registry import build_production_acquisition_registry
from app.providers.readiness import build_catalog_readiness

service = build_production_search_service()
registry = build_production_acquisition_registry()
ready = build_catalog_readiness()  # not_configured; never contains cookie values
```

Control planes:

- CookieCloud UI: `/cookiecloud` — APIs `/api/cookiecloud/import|status`
- HLS inspect: `/api/playback/hls/inspect`, `/api/playback/lines/parse`
- Egress: `/egress`
- Readiness: `/api/providers/readiness`

## Explicit non-claims

- No VIP / login / paywall bypass; CookieCloud is operator-initiated import only
- HLS inspect does **not** fetch media segments or keys
- jiuse remains TEST_FIXTURE until an approved live endpoint freeze
- Production catalogs never substitute test fixtures or infer activation from a cookie
- Package builders require an explicit fetcher and do not create a production runtime
- The v1.5.0 source release does not publish a production image or deploy N100

## Modules

| Module | Role |
|--------|------|
| `app/providers/production_catalog.py` | Reviewed identity map and empty default builders |
| `app/providers/readiness.py` | Catalog readiness snapshot (no secrets) |
| `app/providers/javdb/*` | PRODUCTION HTML + session + live/fixture package |
| `app/providers/jiuse/*` | TEST_FIXTURE offline |
| `app/providers/zuidapi/*` | MacCMS PRODUCTION (static default) |
| `app/providers/copymanga/*` | Real-site comic PRODUCTION |
| `app/providers/comic/*` | Local comic download proof |
| `app/cookiecloud/*` | CookieCloud control plane + UI |
| `app/playback/*` | HLS / playback-line parse only |
| `app/egress/*` | Proxy pool / exit diagnostics |

## Related

- [JAVDB_GROK_MERGE.md](./JAVDB_GROK_MERGE.md)
- [EGRESS.md](./EGRESS.md)
- [NSFWPRO_FACTORY.md](./NSFWPRO_FACTORY.md)
