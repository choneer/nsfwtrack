# nsfwpro factory Providers in nsfwtrack 1.4.1

| nsfwpro factory key | nsfwtrack `provider_key` | Scope | Ops |
|---------------------|--------------------------|-------|-----|
| `javdb-metadata` | `javdb_metadata` | PRODUCTION | SEARCH, DETAIL, ASSET_LIST |
| `jiuse-vod` | `jiuse_vod` | TEST_FIXTURE | SEARCH, DETAIL (offline HTML) |
| `zuidapi-vod` | `zuidapi_vod` | PRODUCTION | SEARCH, DETAIL (MacCMS JSON) |

Map: `app/providers/production_catalog.NSFWPRO_FACTORY_KEY_MAP`.

The map records reviewed identity correspondence only. It does not activate an
endpoint, search, or acquisition package; all production catalogs are empty.

Not factory Providers (out of scope for “all nsfwpro Providers”): CookieCloud,
HLS/playback modules, Venera comic **site** hosts, FnDepot.
