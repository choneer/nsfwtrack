# JavDB package on branch `nsfwtrack_grok`

## Scope

- **Branch:** `nsfwtrack_grok` (for Codex review + merge)
- **Package:** `app/providers/javdb/`
- **Offline package:** `TEST_FIXTURE` only (hosts end with `.invalid`)
- **PRODUCTION facts:** `production.py` — code-owned SEARCH+DETAIL HTML +
  provider-session cookie policy for `javdb.com` (activation-validated only)
- **Operations (this package):** `SEARCH`, `DETAIL` only
- **Production registry:** still **empty** (no live Search wiring)

Full ordered roadmap and product rules: [PRODUCTION_ROADMAP.md](./PRODUCTION_ROADMAP.md).

## Product rules (verbatim)

1. Cookie + metadata scrape first.
2. Video: ASSET_LIST (links) + optional local DOWNLOAD later.
3. Comics/doujin: separate later package with local DOWNLOAD.
4. No VIP/login bypass.
5. JP/KR egress blocked for JavDB (operator proxy / `/egress`).

## ID strategy

- `external_id` = path **slug** (e.g. `RM29z` in `/v/RM29z`)
- Catalog number (e.g. `SSIS-001`) is `VideoIdentifier.catalog_number`

## Attribution

- https://github.com/Yuukiy/JavSP
- https://github.com/lmixture/JavdBviewed

Offline HTML fixtures are synthetic. PRODUCTION facts validate without network.
Live scrape / cookie injection / registry population remain later work.

## Egress diagnostics (related)

Local UI at `/egress` (`app/egress/`) for multi-source exit IP + proxy pool quality.
See [EGRESS.md](./EGRESS.md). Does **not** enable production JavDB hosts in the registry.

## Runtime B–D (explicit injection only; default catalogs empty)

Code-complete on this branch; **v1.3 default catalogs stay empty**.

- Live adapter + cookie loader + package builder: `package_build` / `live_adapter`
- Video ASSET_LIST (links) + optional acquisition DOWNLOAD
- Comic local DOWNLOAD: `app/providers/comic/`
- The legacy environment opt-in flag no longer activates a runtime. Package tests
  inject a static fetcher explicitly; a production fetcher needs separate review.

Still not default-wired:

- Non-empty `PRODUCTION_ENDPOINT_REGISTRY` / `PRODUCTION_SEARCH_PACKAGES`
- CookieCloud auto-sync / VIP bypass

## Tests

```bash
cd /home/nsfwtrack
.venv/bin/python -m pytest tests/test_javdb_metadata_provider.py tests/test_javdb_production_activation.py -q
```
