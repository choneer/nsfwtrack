# Production path roadmap (`nsfwtrack_grok`)

**Application 1.5.0** (Schema 5) is the development head on this branch.
v1.3.0 kept production catalogs empty; 1.4.x populated nsfwpro factory keys;
**1.5.0** adds CookieCloud, HLS/playback inspect, and `copymanga` real-site comic.

Latest published GitHub Release may still be older (`v1.3.0`); this document
describes the **code head**, not a cut Release tag.

## Product scope (confirmed)

1. **Cookie + metadata scrape first** — operator session cookie; SEARCH + DETAIL HTML.
2. **Video** — `ASSET_LIST` surfaces **non-downloadable link descriptors**; **optional** local `DOWNLOAD` via acquisition after explicit confirm.
3. **Comics / doujin** — separate package; local `DOWNLOAD` after confirm (`comic_local_fixture` proves path; `copymanga` is PRODUCTION comic).
4. **No VIP / login / paywall bypass.**
5. **JP/KR egress** for JavDB (operator proxy; `/egress`).
6. **CookieCloud** and **HLS inspect** are control planes (not Providers).

## Default catalog (1.5.0)

| Provider key | Scope | Default process mode | Notes |
|--------------|-------|----------------------|--------|
| `javdb_metadata` | PRODUCTION | **live_capable** if session cookie loadable; else **fixture_fallback** | Cookie via env / file / CookieCloud drop zone |
| `jiuse_vod` | TEST_FIXTURE | fixture_fallback | Offline only; live unauthorized |
| `zuidapi_vod` | PRODUCTION | fixture_fallback | Approval uses static JSON package unless a live fetcher is injected |
| `copymanga` | PRODUCTION | fixture_fallback | Real-site approval; default package static until live fetcher injected |
| `comic_local_fixture` | TEST_FIXTURE | fixture_fallback | Local page download proof |

**Endpoint registry (PRODUCTION hosts):** `javdb_metadata`, `zuidapi_vod`, `copymanga`.

**Acquisition packages:** `javdb_metadata`, `copymanga`, `comic_local_fixture`.

Operator readiness (no secrets): `GET /api/providers/readiness` and the CookieCloud page.

## Phase status

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **A** | Activation: PRODUCTION HTML + provider_session; SEARCH+DETAIL+optional ASSET_LIST | **Done** (default catalogs) |
| **B** | PRODUCTION facts + live async adapter + cookie loader + package builder | **Done** (JavDB live when cookie present) |
| **C** | Video ASSET_LIST (links) + optional acquisition DOWNLOAD | **Done** (JavDB optional) |
| **D** | Comic package + local DOWNLOAD acquisition | **Done** (fixture + copymanga PRODUCTION) |
| **E** | CookieCloud import + HLS/playback-line inspect (no segment fetch) | **Done** (1.5.0) |
| **F** | Catalog readiness honesty + CookieCloud operator UI | **Done** (1.5.0 engineering close) |

## Runtime (1.5.0)

```bash
export NSFWTRACK_JAVDB_SESSION_COOKIE='name=value; ...'   # lawful session only
# optional proxy for JavDB / CookieCloud:
export NSFWTRACK_HTTP_PROXY=http://127.0.0.1:6123
# optional CookieCloud import → data/cookies/javdb_metadata.cookie
```

```python
from app.source_search import build_production_search_service
from app.acquisition.registry import build_production_acquisition_registry
from app.providers.readiness import build_catalog_readiness

service = build_production_search_service()
registry = build_production_acquisition_registry()
ready = build_catalog_readiness()  # never contains cookie values
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
- Default zuidapi/copymanga packages use static fixtures unless a live fetcher is injected
- No merge to main / annotated tag / N100 deploy is implied by this document alone

## Modules

| Module | Role |
|--------|------|
| `app/providers/production_catalog.py` | Default endpoints + search + acquisition packages |
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
