# Video Metadata Field Crosswalk v1

## Scope

This crosswalk maps non-sensitive concepts observed in the fixed JavSP and
JavdBviewed snapshots to the existing Provider-neutral video contracts. It does
not change DTOs, select a Provider, or authorize network access. FnDepot and
Venera contribute versioning and operation concepts rather than video fields.

`required` below means required for a particular normalized record or admission
gate, not required in every upstream response. Missing upstream data never
deletes an existing local value.

## Field mapping

| Upstream evidence | Target field | Required / optional | Normalization and identity | Provenance and merge behavior | Current authority |
|---|---|---|---|---|---|
| JavSP catalog number / serial | `VideoIdentifier.catalog_number` | optional | bounded text; identity remains `provider_key + external_id` | source operation and raw-value digest; first non-empty by priority | metadata candidate only |
| JavSP source record identity | `VideoIdentifier.external_id` | required for detail | opaque, Provider-scoped, never a URL | exact source identity; conflicts are hard | code-owned binding only |
| JavSP title / original title | `VideoSearchResult.title`, `VideoDetail.title`, `alternate_titles` | title required for usable detail; alternates optional | bounded Unicode; preserve original separately | source priority; local/manual title wins | no write until explicit apply |
| JavSP plot | `summary` | optional | bounded normalized text, no inference | first non-empty; absence does not clear | candidate only |
| JavSP release date | `release_date` | optional | ISO/UTC contract conversion only when unambiguous | retain source timestamp and operation | candidate only |
| JavSP duration | `duration_seconds` | optional | finite non-negative bounded number | source fact; conflicting values require review | candidate only |
| JavSP performers / JavdBviewed actors | `VideoPerson(role=performer)` | optional tuple | Provider-scoped person identity where available; stable display fallback | merge by scoped identity, preserve provenance | additive only after explicit review |
| JavSP director | `VideoPerson(role=director)` | optional | bounded display and scoped identity | source priority; no guessed person matching | candidate only |
| JavSP producer / studio | `VideoOrganization(role=studio)` | optional | bounded display and scoped identity | source priority, exact identity when present | candidate only |
| JavSP publisher | `VideoOrganization(role=publisher)` | optional | bounded display and scoped identity | source priority, no cross-provider merge | candidate only |
| JavSP series | `VideoSeries` | optional | Provider-scoped opaque identity plus bounded name | preserve source identity; no global name inference | candidate only |
| JavSP raw genre/tag and ID | `VideoTag` | optional tuple | retain raw and bounded normalized value; namespace is explicit | de-duplicate only within Provider scope | additive review only |
| JavSP score | `VideoRating` | optional | retain declared scale; reject incomparable scale coercion | source priority and vote facts remain separate | candidate only |
| JavSP cover / preview image / preview video categories | `VideoAsset` | optional tuple | opaque `asset_id`, kind and declared facts; no locator persistence | provenance records operation and source identity | `asset_list` only when separately approved |
| JavSP one source-scoped aggregate | `VideoDetail` | required only after detail admission | immutable bounded fields with exact `available_fields` | every available field has source provenance | candidate only |
| Venera list result with page or next token | `VideoSearchPage` | required for search result | bounded tuple plus either bounded page facts or opaque token | pagination source and operation are retained | candidate only |
| JavdBviewed viewed/browsed/want state | `LocalVideoMetadata` state fields | optional local state | enum validation; not remote metadata | local state always wins | local-only, never Provider authority |
| JavdBviewed rating, notes, favorite, list IDs | local user fields | optional local state | preserve exact local ownership and bounded values | manual/user fields cannot be overwritten by refresh | local-only |
| JavdBviewed manually edited fields | `manually_edited_fields` policy | optional marker | field names are code-owned and bounded | refresh skips protected fields | local authority |
| JavdBviewed soft deletion | local deletion fact | optional | explicit state/timestamp, never inferred from missing source data | remote absence cannot delete | local authority |
| JavdBviewed sync source/time/status | `VideoMetadataProvenance` / local sync facts | optional | UTC-aware bounded facts | preserve sync outcome and source identity | local-only |
| FnDepot `schema_version` and source metadata | `VideoMetadataProvenance` review metadata | required for manifest admission | exact version and bounded source identity | parser records version; no executable meaning | reference-only |
| FnDepot app/release/package keys | versioned manifest profile | required for admission | stable keys; architecture override is explicit | specific override beats common value; incomplete entry rejected | no Provider authority |
| Venera source `name`/`key`/`version` | Provider identity/version model | required for a future source | code-owned opaque key, exact version | identity must be reviewed independently | taxonomy reference only |
| JavSP ordered source results plus JavdBviewed manual protection | `VideoMetadataMergePlan` | required before any future apply | immutable local snapshot and source candidates | explicit priority, local ownership and conflicts | pure zero-write plan only |

## Local State and Merge Policy

1. Normalize one source-scoped result before combining sources.
2. Keep source priority explicit and deterministic.
3. Fill only missing scalar values; a missing or empty incoming field never
   deletes or clears an existing value.
4. Preserve alternative covers/assets as bounded candidates rather than
   silently replacing the selected value.
5. Keep local user and manually edited fields authoritative. Conflicting
   identities, rating scales, or hard mappings stop the plan for review.
6. Record `provider_key`, external identity, operation, observation time and a
   bounded canonical-value digest for every accepted field.
7. Return a pure merge plan. No adapter operation, database write, file write,
   download, or Registry mutation is implicit.

## Denied authority

No mapped field can authorize a host, endpoint, credential, cookie, download,
playback, arbitrary URL, code load, or second Provider. A URL-like upstream
value is not an identifier and is not retained as an executable locator. The
Production Profile remains limited to `search`, `detail`, and optional
`asset_list`, all behind a future explicit Approval.
