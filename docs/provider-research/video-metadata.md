# Phase 5-N4C Video Metadata Provider Research

## 1. Status and scope

Phase 5-N4D-B is complete as a Provider-neutral contract and fixture framework.
The implementation intentionally contains no real Provider identity, Host,
Endpoint, response locator, network call, or Registry entry. `search`, `detail`,
and `asset_list` remain separate operations, and metadata merge is a local pure
plan only. A real Provider remains a future separately approved phase.

This document is a static architecture study. It does not approve, implement,
register, or contact a real Provider. The Production Provider Registry remains
`EndpointRegistry(())`. Any future Provider requires a separately completed
production Approval and a new implementation GOAL.

The study uses public source snapshots only. No implementation code is copied.
Search, detail, and asset listing remain separate operations; none may trigger
the next operation, write local records, or download an asset implicitly.

Phase 5-N4D-D-B0 adds a fixed-revision evidence profile only. It does not alter
these DTOs or activate a Provider. The detailed evidence, crosswalk, operation
matrix and readiness decision are recorded in the five B0 research documents.

## 2. Reviewed public repositories

| Repository | Default branch | Reviewed commit | License at reviewed commit |
|---|---|---|---|
| `lmixture/JavdBviewed` | `main` | `8c9245726906ece8d49f553542874980512d4504` | `AGPL-3.0-only` (`LICENSE`, package metadata) |
| `Yuukiy/JavSP` | `master` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | Root `LICENSE` is `GPL-3.0-only`; the README also claims Anti-996 and additional terms, so reuse has extra uncertainty |

### 2.1 JavdBviewed references

Reviewed files for B0:

- `README.md`, `package.json`, and `LICENSE` for status and licensing;
- `apps/extension/src/types/index.ts` for local record, user and manual fields;
- `apps/extension/src/features/webdavSync/domain/types.ts` for sync facts;
- `apps/extension/src/features/webdavSync/application/dataMerge.ts` and
  `importSanitizer.ts` for deterministic merge and device-state preservation.

Adopted as architecture ideas:

- separation of local viewing state from refreshed source metadata;
- protection of manually edited fields and local user values;
- explicit soft-delete and sync source/time/status facts;
- deterministic priority, fallback, tag and status merge behavior.

Not adopted:

- site-specific page parsing, browser extension behavior or source locators;
- account/login, media search, remote sync transport or download behavior;
- any AGPL implementation code or legacy userscript code.

### 2.2 JavSP references

Reviewed files for B0:

- `README.md` and `LICENSE` for licensing and additional terms;
- `javsp/datatype.py` for metadata vocabulary and output mapping;
- `javsp/__main__.py` for source ordering, aggregation and required fields.

Adopted as architecture ideas:

- one source-scoped metadata result per Provider before aggregation;
- a broad movie metadata vocabulary: catalog number, original/alternate title,
  plot, date, duration, people, organizations, series, tags, rating, covers,
  preview images, and preview video;
- deterministic Provider priority, first-nonempty scalar selection, retained
  cover alternatives, and an explicit required-field gate;
- explicit failure when required fields remain unavailable.

Not adopted:

- crawler modules, source-specific networking, cookies/proxies or browser use;
- filesystem mutation, poster/media downloading, naming, moving, scraping, or
  raw response/exception logging;
- direct GPL implementation reuse, especially given the README's additional
  license claims.

## 3. Provider-neutral DTO draft

All DTOs are immutable. Text is bounded and normalized only where the contract
defines a lossless representation. Provider identifiers are opaque and scoped
by `provider_key`; a URL is never an identifier or network authorization.

### 3.1 Identity and supporting DTOs

`VideoIdentifier`

| Field | Meaning |
|---|---|
| `provider_key` | Code-owned Provider identity |
| `external_id` | Provider-scoped opaque work identity |
| `catalog_number` | Display/catalog identity when supplied; not globally unique |
| `canonical_url` | Optional attribution locator, not fetch authority |

`VideoPerson`

| Field | Meaning |
|---|---|
| `provider_key`, `external_id` | Provider-scoped person identity; either may be absent only when the whole person is an unlinked display candidate |
| `display_name`, `alternate_names` | Bounded source values |
| `role` | `performer` or `director`; code-owned enum |

`VideoOrganization`

| Field | Meaning |
|---|---|
| `provider_key`, `external_id` | Provider-scoped organization identity |
| `display_name` | Bounded source value |
| `role` | `studio` or `publisher`; code-owned enum |

`VideoSeries` contains `provider_key`, optional opaque `external_id`, and
`display_name`. `VideoTag` contains `provider_key`, optional opaque
`external_id`, `raw_value`, `normalized_value`, and optional code-owned
`namespace`. Raw and normalized values are both retained.

`VideoRating` contains `provider_key`, `value`, `scale_min`, `scale_max`, and
optional bounded `vote_count`. It never silently converts unlike rating scales;
UI comparison first normalizes using the declared scale.

`VideoAsset`

| Field | Meaning |
|---|---|
| `provider_key`, `asset_id` | Provider-scoped opaque identity |
| `kind` | `cover`, `preview_image`, or `preview_video` |
| `mime_type`, `byte_size`, `checksum` | Declared facts, each nullable until known |
| `width`, `height`, `duration_seconds` | Optional bounded media facts |
| `requires_auth`, `downloadable` | Provider-declared facts, never an authorization grant |
| `source_updated_at` | Optional Provider timestamp |

`VideoMetadataProvenance`

| Field | Meaning |
|---|---|
| `field_name` | DTO field or list member identity |
| `provider_key`, `external_id` | Exact source record |
| `operation` | `search`, `detail`, or `asset_list` |
| `observed_at`, `source_updated_at` | Local observation and optional source time |
| `raw_value_hash` | Versioned canonical-value digest, never raw payload |
| `confidence` | `reported`, `normalized`, or `derived`; no probabilistic guessing |

### 3.2 Search and detail DTOs

`VideoSearchResult` is deliberately incomplete:

```text
provider_key
external_id
catalog_number
title
alternate_titles
summary
release_date
duration_seconds
performers
canonical_url
cover
available_fields
provenance
```

Only fields actually present in the search response appear in
`available_fields`. Search output cannot clear or authoritatively replace detail
data.

`VideoDetail` is the normalized detail candidate:

```text
provider_key
external_id
catalog_number
title
alternate_titles
summary
release_date
duration_seconds
performers
director
studio
publisher
series
tags
rating
canonical_url
cover
preview_images
preview_video
source_updated_at
available_fields
provenance
```

`cover`, `preview_images`, and `preview_video` contain `VideoAsset` facts, not
fetchable arbitrary URLs. A Provider-specific parser may map an approved
payload locator to attribution data internally, but a future `asset_list` must
return opaque Asset IDs through the shared Provider boundary.

## 4. Operation contract draft

| Operation | Input | Output | Pagination | Response | Database write | Follow-up network | Maximum response | Fixture |
|---|---|---|---|---|---|---|---|---|
| `search` | bounded query, page token/number, page size | immutable page of `VideoSearchResult` | Provider-approved number or opaque token, bounded | approved structured metadata only | none | none; detail is a separate user action | exact Approval value; current shared ceiling is not expanded by this document | success, empty, malformed, oversized, timeout, 4xx/5xx, pagination edge |
| `detail` | one Provider-scoped opaque `external_id` | one `VideoDetail` | none | approved structured metadata only | none | none; assets are not fetched | exact Approval value | complete, partial, missing, conflicting, malformed, oversized, auth/error cases |
| `asset_list` | one approved Provider/external identity | bounded tuple of `VideoAsset` | normally none; if required, explicit bounded token | approved structured asset metadata only | none | none; no resolve/download | exact Approval value | no assets, every kind, duplicate ID, URL-like ID rejection, bad size/MIME/hash |
| future `discover` | code-owned bounded parameters only | bounded candidates | explicit if approved | approved structured metadata | none | none | separate Approval value | separate future suite |

N4C implements none of these operations. Future adapters parse one already
bounded response and return DTOs. They do not own HTTP, Registry construction,
database Sessions, local files, logging of raw values, or operation chaining.

## 5. Provenance, conflict, and merge rules

1. User-edited local fields always win. A Provider refresh may produce a
   candidate diff but cannot overwrite a manual value.
2. A single source update cannot erase another source or user edit. Missing
   means "not reported", never deletion.
3. Empty, whitespace-only, malformed, or out-of-range values do not replace a
   valid nonempty value.
4. Every accepted scalar and list member retains Provider provenance. The
   application may display an aggregate value while preserving all source
   candidates and the deterministic selection rule.
5. Scalar merge is deterministic: pinned user selection, then explicit
   Provider priority, then first nonempty valid value. Equal priority uses a
   stable Provider-key order, not response timing.
6. Alternate titles, people, organizations, series, and tags deduplicate only
   by their Provider-scoped identity or an explicit reviewed normalization
   rule. Display-name similarity alone never merges identities.
7. Tags retain `raw_value` and `normalized_value`; normalization cannot broaden
   capabilities or silently discard the raw source value.
8. Ratings retain their original scale and vote count. A normalized display
   score is derived and carries provenance.
9. Search results are previews, not complete-detail authority. Only a separate
   `detail` result can update detail candidates, and applying it remains a
   separate confirmed local operation in a later phase.
10. Asset metadata is a candidate only. It does not trigger resolution,
    preview probing, remote image embedding, or download.
11. Local watched/favorite/progress state is never Provider metadata and is
    neither uploaded nor cleared by refresh.
12. Provider failure is isolated. Partial multi-Provider success retains each
    result separately and reports failed/unknown Providers; it is not reported
    as a complete aggregate success.

## 6. Status matrices

### 6.1 Operation status matrix

| Status | `search` | `detail` | `asset_list` | Meaning |
|---|---:|---:|---:|---|
| `success` | yes | yes | yes | Complete bounded parse for that operation only |
| `invalid_request` | yes | yes | yes | Local typed input invalid; zero network |
| `not_approved` | yes | yes | yes | Approval/Registry gate denied; zero network |
| `not_supported` | yes | yes | yes | Capability absent; zero network |
| `unauthorized` | possible | possible | possible | Approved operation requires valid auth |
| `forbidden` | possible | possible | possible | Provider denied the operation |
| `not_found` | possible | expected | possible | No matching resource; never delete local state |
| `rate_limited` | possible | possible | possible | User-visible; no automatic retry in this plan |
| `provider_unavailable` | possible | possible | possible | Timeout/DNS/TLS/5xx after shared classification |
| `invalid_payload` | possible | possible | possible | Type/schema/parser validation failed |
| `response_too_large` | possible | possible | possible | Shared stream limit stopped parsing |
| `expired` | no | possible | possible | Approved auth/session or locator fact expired |
| `cancelled` | possible | possible | possible | Request cancellation propagated |
| `unknown` | possible | possible | possible | Final remote result cannot be proven |

### 6.2 Network side-effect matrix

| Action | GET page | Explicit operation POST | Chained request | Asset bytes |
|---|---:|---:|---:|---:|
| Render search/detail UI | none | n/a | none | none |
| `search` | forbidden | one approved request | forbidden | none |
| `detail` | forbidden | one approved request | forbidden | none |
| `asset_list` | forbidden | one approved request | forbidden | metadata only |
| Apply metadata | none | zero Provider network | forbidden | none |

### 6.3 Database write matrix

| Action | Candidate cache | Item fields | ItemSource | User state |
|---|---:|---:|---:|---:|
| N4C research | none | none | none | none |
| Future search/detail/asset list | none by adapter | none | none | none |
| Future explicit apply | only if separately designed | selected fields only | exact source identity/check facts | unchanged |
| Failure/unknown | none | none | none | unchanged |

### 6.4 Permission matrix

| Actor/fact | View local page | Run Provider operation | Apply candidate | Download asset |
|---|---:|---:|---:|---:|
| Authenticated local user | yes | only explicit approved POST | later explicit signed POST | not in N4C/N4D |
| Provider response | no authority | no expansion | no authority | no authority |
| Subscription/URL value | no authority | no authority | no authority | no authority |
| Background task | no | no | no | no |

### 6.5 Authentication matrix

| Auth state | Public approved operation | Protected operation | Local data effect |
|---|---:|---:|---:|
| `not_configured` | allowed if Approval says `none` | denied | none |
| `configured` | allowed if public | explicit test required first | none |
| `valid` | allowed | allowed only for exact operation/host scope | none |
| `expired` / `invalid` / `revoked` | public only | denied | never delete metadata or secret speculatively |
| `unknown` | public only if independent | denied | preserve state and report unknown |

### 6.6 Error matrix

| Source fact | Stable result | Retry/merge behavior |
|---|---|---|
| Local validation/capability failure | `invalid_request`, `not_approved`, or `not_supported` | zero network; do not merge |
| HTTP 401/403/404/429 | `unauthorized`, `forbidden`, `not_found`, `rate_limited` | no automatic retry; retain local state |
| DNS/TLS/timeout/5xx | `provider_unavailable` | no automatic retry; other Provider results stay separate |
| Wrong content type/schema | `invalid_payload` | raw payload not logged or stored |
| Stream limit | `response_too_large` | stop reading; no partial DTO |
| Cancellation | `cancelled` | close request; no partial DTO |
| Unclassifiable final state | `unknown` | no merge, deletion, or ordinary success |

### 6.7 Result uncertainty matrix

| Proven fact | Classification | Allowed consequence |
|---|---|---|
| Response fully received and DTO validated | `success` | display candidate for this operation |
| Request proven not sent or rejected locally | matching local error | no remote implication |
| Request sent but response completion unknown | `unknown` | preserve local state; allow explicit retry |
| Some Providers succeeded, one failed | partial result plus per-Provider error | display provenance and incompleteness |
| Search field absent | missing | retain existing detail/user value |
| Provider says resource missing | `not_found` | do not infer deletion or clear local data |

## 7. N4D handoff requirements

Before implementing the first video metadata Provider, the user must supply and
approve every placeholder in `video-metadata-approval-draft.md`, including the
exact Provider identity, lawful/terms basis, fixed hosts and operations,
response limits/types, field mapping, fixtures, and error mapping. N4D may then
implement only `search`, `detail`, and optional `asset_list`; it must not add
auth, playback, download, background refresh, or a second Provider implicitly.
