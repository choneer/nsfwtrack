# JavDB package on branch `nsfwtrack_grok`

## Scope

- **Branch:** `nsfwtrack_grok` (for Codex review + merge)
- **Package:** `app/providers/javdb/`
- **Approval scope:** `TEST_FIXTURE` only (hosts end with `.invalid`)
- **Operations:** `SEARCH`, `DETAIL` only
- **Production registry:** unchanged / empty

## ID strategy

- `external_id` = path **slug** (e.g. `RM29z` in `/v/RM29z`)
- Catalog number (e.g. `SSIS-001`) is `VideoIdentifier.catalog_number`

## Attribution

- https://github.com/Yuukiy/JavSP
- https://github.com/lmixture/JavdBviewed

Offline HTML fixtures are synthetic. Real-site live access was proven separately
in the nsfwpro workspace (proxy + session cookie) and is **not** activated here.

## Not in this branch

- PRODUCTION hosts (`javdb.com`, mirrors)
- CookieCloud / `SESSION_COOKIE` production auth
- `ASSET_LIST` / `DOWNLOAD` / playback
- Changes to `PRODUCTION_ENDPOINT_REGISTRY`

## Tests

```bash
cd /home/nsfwtrack
python3.12 -m pytest tests/test_javdb_metadata_provider.py -q
```
