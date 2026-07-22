# Production path roadmap (`nsfwtrack_grok`)

Ordered phases. **Application 1.4.1** populates all nsfwpro factory Providers
(`javdb_metadata`, `jiuse_vod`, `zuidapi_vod`) plus `comic_local_fixture`.
v1.3.0 kept catalogs empty.

## Product scope (confirmed)

1. **Cookie + metadata scrape first** — operator session cookie; SEARCH + DETAIL HTML.
2. **Video** — `ASSET_LIST` surfaces **non-downloadable link descriptors**; **optional** local `DOWNLOAD` via acquisition after explicit confirm.
3. **Comics / doujin** — **separate package**; local `DOWNLOAD` after confirm (`comic_local_fixture` TEST_FIXTURE proves path; live comic host needs separate approval).
4. **No VIP / login / paywall bypass.**
5. **JP/KR egress** for JavDB (operator proxy; `/egress`).

## Phase status

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **A** | Activation: PRODUCTION HTML + provider_session; SEARCH+DETAIL+optional ASSET_LIST; fail-closed fixture/download | **Done** |
| **B** | PRODUCTION facts + live async adapter + cookie loader + package builder | **Done** (opt-in; not default registry) |
| **C** | Video ASSET_LIST (links) + optional acquisition DOWNLOAD | **Done** (opt-in) |
| **D** | Comic package + local DOWNLOAD acquisition | **Done** (TEST_FIXTURE proof + acquisition) |

## Runtime (1.4.1 default)

```bash
export NSFWTRACK_JAVDB_SESSION_COOKIE='name=value; ...'   # lawful session only
# optional:
export NSFWTRACK_HTTP_PROXY=http://127.0.0.1:6123
```

```python
from app.source_search import build_production_search_service
from app.acquisition.registry import build_production_acquisition_registry

service = build_production_search_service()  # javdb + comic packages
registry = build_production_acquisition_registry()
```

## Explicit non-claims

- No VIP bypass / CookieCloud auto-theft
- No invented live comic production hostname (fixture package only)
- Published GitHub Release / tag `v1.4.1` is not cut by this branch alone

## Modules

| Module | Role |
|--------|------|
| `app/providers/javdb/production.py` | PRODUCTION approval facts |
| `app/providers/javdb/live_adapter.py` | async SEARCH/DETAIL/ASSET_LIST |
| `app/providers/javdb/session.py` | cookie load |
| `app/providers/javdb/fetch.py` | allowlisted HTML fetch |
| `app/providers/javdb/package_build.py` | ProviderPackage + acquisition |
| `app/providers/comic/*` | comic fixture metadata + download |
| `app/providers/opt_in_catalog.py` | opt-in service/registry builders |

## Related

- [JAVDB_GROK_MERGE.md](./JAVDB_GROK_MERGE.md)
- [EGRESS.md](./EGRESS.md)
