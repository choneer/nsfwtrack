# Phase 5-N4C Comic Provider Research

## 1. Status and scope

This document is a static architecture study. It does not implement or approve
a Comic Provider, JavaScript engine, remote source loader, account flow,
favorite synchronization, reader, cache, or download. The Production Provider
Registry remains `EndpointRegistry(())`.

Future NSFWTrack Comic Providers must be fixed, reviewed Python adapters behind
the shared immutable Capability, Approval, Endpoint Registry, and outbound
client boundaries. Remote or local Provider JavaScript is not an allowed
adapter format.

## 2. Reviewed repository facts

| Repository | Default branch | Reviewed commit | License/status |
|---|---|---|---|
| `venera-app/venera` | `master` | `a0eba914f4c2a84ac1bc925adec2baabe920b9be` | `GPL-3.0` in root `LICENSE`; README states the project is no longer maintained |

Reviewed files:

- `README.md`, `LICENSE`, `doc/comic_source.md`;
- `lib/foundation/comic_source/comic_source.dart`;
- `lib/foundation/comic_source/parser.dart`;
- `lib/foundation/comic_source/types.dart`;
- `lib/foundation/comic_source/models.dart`;
- `lib/foundation/comic_source/category.dart`;
- `lib/foundation/comic_source/favorites.dart`.

Observed architecture:

- `ComicSourceManager` discovers source files, parses them through a JavaScript
  engine, keeps source key/version facts, and tracks available updates;
- the documented Source surface includes initialization, account/login/cookie
  flows, explore, categories, search, details, chapters/pages, thumbnails,
  favorites/folders, comments, rating, and archive download;
- content identity is effectively source key plus opaque comic ID; detail data
  carries chapter maps, thumbnails, tags, update time, and remote social state;
- page loading returns a bounded ordered list for one comic/chapter while local
  history is mixed into application-side models;
- several operations catch source exceptions and map them into a common result,
  while documented login-expired behavior may trigger relogin/retry.

Adopted as architecture ideas:

- capability decomposition across search, explore/category, detail, chapter,
  page/asset, account, favorite, comment, rating, and download domains;
- Provider-scoped comic/chapter identity and explicit ordered reading flow;
- separate summary/detail models, grouped chapters, page lists, local history,
  and remote favorite/social facts;
- source version and minimum-compatible-version facts as review metadata;
- DTO construction at the adapter boundary and a common stable error surface.

Not adopted:

- JavaScript execution, dynamic Source installation, directory scanning for
  executable sources, `init` execution, source update URLs, or auto-update;
- JavaScript-to-native bridges that expose networking, cookies, files, dynamic
  settings, or logging;
- persisted account/password arrays, browser cookie import, automatic relogin,
  raw exception logging, or remote state merged with local state;
- archive download, automatic chapter download, recursive caching, source-
  defined arbitrary URLs, or direct GPL code reuse.

Venera execution-boundary ledger:

| Area | Reviewed evidence | NSFWTrack decision |
|---|---|---|
| Module/source metadata | `comic_source.dart`, `parser.dart`, documented key/name/version/minimum version/update URL | keep fixed Provider/version facts; reject executable source/update URL |
| Search/explore/category | `doc/comic_source.md`, `category.dart`, parser loaders | adopt separate capabilities and typed paging; no dynamic callbacks |
| Detail/chapter/page | `models.dart`, `types.dart`, documented load functions | adopt Provider-scoped identities and ordered DTOs |
| Account/login/cookies | account parsing and documented login/cookie validation | future shared Vault/broker only; no browser extraction or adapter persistence |
| Favorites/comments/rating | `favorites.dart` and parser operation loaders | remote state stays separate; all mutation capabilities deferred |
| Source version/update | manager available-update map and source URL/version | code release + fresh Approval only; no remote code update |
| Download/local progress | archive downloader hooks and detail/history mixin | download deferred; reading progress is application-owned local state |
| Error/retry | common `Res`, caught exceptions, documented login-expired retry | stable redacted errors; no raw exception or automatic relogin/retry |

## 3. Comic DTO draft

All identifiers are opaque and Provider-scoped. A display URL, page locator, or
asset locator is never an identifier and never grants outbound access.

### `ComicSearchResult`

```text
provider_key
external_id
title
alternate_titles
summary
cover
creators
categories
tags
language
status
source_updated_at
available_fields
provenance
```

It is an incomplete preview. It cannot clear or replace detail/chapter facts.

### `ComicDetail`

```text
provider_key
external_id
title
alternate_titles
summary
cover
creators
categories
tags
language
status
chapter_groups
source_created_at
source_updated_at
available_fields
provenance
```

Remote favorite, rating, comment, and reading facts are not folded into this
metadata DTO.

### Supporting DTOs

| DTO | Fields and identity rule |
|---|---|
| `ComicCreator` | `provider_key`, optional opaque `external_id`, `display_name`, code-owned `role`; display similarity does not merge creators |
| `ComicCategory` | `provider_key`, opaque category ID, `display_name`, optional parent ID; identity is not the label |
| `ComicTag` | `provider_key`, optional opaque tag ID, `namespace`, `raw_value`, `normalized_value`; raw value is retained |
| `ComicChapter` | `provider_key`, comic external ID, opaque `chapter_id`, `group_id`, `title`, stable `ordinal`, optional source publish/update time |
| `ComicPage` | `provider_key`, comic external ID, chapter ID, opaque `page_id`, stable `ordinal`, optional dimensions; no locator |
| `ComicPageAsset` | `provider_key`, opaque `asset_id`, page ID, MIME/size/checksum/dimensions, auth and expiry facts; locator remains internal and short-lived |
| `ComicReadingProgress` | local Item/source identity, chapter ID, page ID, ordinal, position, updated time, completion flag; strictly local state |

Provider identity keys are tuples: `(provider_key, external_id)` for comics,
`(provider_key, external_id, chapter_id)` for chapters, and the same plus
`page_id` for pages. Chapter/page IDs remain case-sensitive opaque values.

## 4. Operation contract draft

| Operation | Input | Output | Pagination | Database write | Follow-up request | Response/fixture requirement |
|---|---|---|---|---:|---|---|
| `search` | bounded keyword/options/page | page of `ComicSearchResult` | approved number or opaque token | none | none | bounded structured fixture including empty/malformed cases |
| `detail` | one opaque comic ID | one `ComicDetail` | none | none | no implicit chapter/page request | complete and partial detail fixtures |
| `category_list` | no user host/path; approved typed filters only | bounded `ComicCategory` tree/list | none or approved token | none | none | hierarchy, empty, duplicate/cycle-invalid fixtures |
| `category_items` | opaque category ID/options/page | page of `ComicSearchResult` | approved number/token | none | no detail | category paging fixtures |
| `chapter_list` | one opaque comic ID | ordered/grouped `ComicChapter` tuple | none or explicit token | none | no page request | flat/grouped/reordered/duplicate fixtures |
| `page_list` | comic ID + chapter ID | ordered `ComicPage` tuple | none | none | no asset bytes | empty/duplicate/invalid order fixtures |
| `asset_list` | one page ID or bounded page selection | bounded `ComicPageAsset` metadata | none | none | no resolve/download | opaque-ID/MIME/size/checksum/expiry fixtures |

Future optional operations, each separately approved:

```text
discover
auth_test
auth_login
favorite_list
favorite_update
comment_list
rating_update
download
```

The optional set is not authorized by N4C or automatically implied by a Comic
Provider. Mutation operations need explicit user POSTs and independently
designed outcome semantics. `download` is never implied by page reading.

## 5. Reading flow and state separation

```text
explicit search or category request
  -> user selects one comic
  -> explicit detail request
  -> explicit chapter_list request
  -> user selects one chapter
  -> explicit page_list request
  -> selected page asset resolution inside the reader
  -> explicit local-only reading progress write
```

Rules:

- comic, chapter, page, and asset identities are Provider-scoped opaque IDs;
- `ComicPage` and `ComicPageAsset` are separate, and locators are separate from
  both; page ordering never depends on parsing a URL;
- page bytes may come only from exact approved Asset Hosts through a future
  shared asset/playback path with DNS/IP/TLS/peer and size controls;
- displaying one page does not fetch the full chapter or future chapters;
- chapter changes create a diff. Missing remote chapters do not delete local
  records, progress, notes, favorites, or downloaded files;
- `ComicReadingProgress` belongs to local user state and is never uploaded by a
  metadata/page operation;
- remote favorites, folders, ratings, and comments are Provider state and stay
  separate from local favorites, ratings, notes, and progress;
- GET page rendering performs zero Provider network and zero writes. Network
  and progress writes are separate authenticated POST operations in any future
  implementation;
- assets are not persisted or downloaded merely because a page list exists.

## 6. Source lifecycle, account, and update boundary

A future fixed Python adapter is shipped and reviewed with the application. Its
`provider_key`, code version, capability manifest, hosts, endpoint paths,
response policy, DTO mapping, and fixture version are code-owned. There is no
remote source list, script update URL, dynamic import, runtime code download,
or source-authored host.

Provider update lifecycle:

```text
review repository/terms and exact Provider facts
  -> complete placeholder Approval
  -> explicit user production Approval
  -> implement fixed Python adapter + fixtures
  -> local Validator confirms exact Capability/Endpoint parity
  -> explicit release process activates the Registry entry
```

A remote source version may be display metadata only. It cannot install code.
Any adapter or host change requires code review and a new Approval comparison.

Authentication, if a later Provider requires it, uses only a separately
approved shared credential broker/Vault. Account credentials or cookies are not
stored in ordinary database fields, config, logs, fixtures, backup, or adapter
state. Automatic login/relogin/retry and browser-cookie extraction remain
denied. An `unauthorized` response does not delete local or remote-state facts.

Favorites/comments/ratings are mutation capabilities and are not part of the
first N4G reading scope. If later authorized, each needs a fixed operation,
signed confirmation, exact remote outcome classification, and no optimistic
success after unknown results.

## 7. Status matrices

### 7.1 Operation status matrix

| Status | Read operations | Future auth/social mutation | Meaning |
|---|---:|---:|---|
| `success` | yes | possible | Exact operation completed and DTO/outcome validated |
| `invalid_request` | yes | yes | Local typed input rejected; zero network |
| `not_approved` | yes | yes | Provider/operation/host denied; zero network |
| `not_supported` | yes | yes | Capability absent |
| `unauthorized` | possible | possible | Valid auth not available |
| `forbidden` | possible | possible | Provider denied exact operation |
| `not_found` | possible | possible | Resource absent; no local deletion |
| `rate_limited` | possible | possible | No automatic retry |
| `provider_unavailable` | possible | possible | Shared network failure classification |
| `invalid_payload` | possible | possible | Schema/order/identity/parser failure |
| `response_too_large` | possible | possible | Shared response/asset limit exceeded |
| `expired` | asset/auth possible | auth/session possible | Explicit expiry fact |
| `cancelled` | possible | possible | Cancellation propagated |
| `unknown` | possible | possible | Final result is unprovable |

### 7.2 Network side-effect matrix

| Action | Provider requests | Asset bytes | Chained operation |
|---|---:|---:|---:|
| GET local page/reader shell | 0 | 0 | no |
| Each search/detail/category/chapter/page/list POST | at most one exact approved operation | 0 | no |
| Future page asset resolution | one selected approved operation | one selected bounded asset | no chapter prefetch by default |
| Local progress/favorite/note write | 0 | 0 | no |
| N4C research | 0 runtime requests | 0 | no |

### 7.3 Database write matrix

| Action | Metadata/source | Progress | Local favorite/note | Remote state |
|---|---:|---:|---:|---:|
| N4C | none | none | none | none |
| Read operations | none | none | none | none |
| Future explicit metadata apply | selected exact local transaction | none | none | none |
| Explicit progress POST | none | exact local progress only | none | none |
| Future favorite mutation | none | none | local state only if separately chosen | remote result kept separate |
| Failure/unknown | unchanged | unchanged unless local write independently committed | unchanged | preserve last proven state |

### 7.4 Permission matrix

| Authority source | Read metadata/pages | Update local progress | Remote social mutation | Download |
|---|---:|---:|---:|---:|
| Authenticated user + explicit operation | only approved operation | explicit local POST | future separately approved POST | future separate approval |
| Source JavaScript/update URL | forbidden | forbidden | forbidden | forbidden |
| Provider payload | cannot expand hosts/ops | no authority | no authority | no authority |
| Page/asset locator | only internal exact operation scope | no authority | no authority | no authority |
| Background task | no | no | no | no |

### 7.5 Authentication matrix

| Auth state | Public read | Protected read | Remote mutation | Local progress |
|---|---:|---:|---:|---:|
| `not_configured` | allowed only if approved public | denied | denied | allowed locally |
| `configured` | public only | explicit test required | denied | allowed locally |
| `valid` | allowed | exact scope only | exact separately approved scope only | allowed locally |
| `expired` / `invalid` / `revoked` | public only | denied | denied | allowed locally |
| `unknown` | independently public only | denied | denied | allowed locally; do not alter remote facts |

### 7.6 Error matrix

| Failure | Stable result | Behavior |
|---|---|---|
| Invalid opaque ID/options/order | `invalid_request` | zero network/write |
| Missing Approval/capability | `not_approved` / `not_supported` | zero DNS/network |
| 401/403/404/429 | `unauthorized` / `forbidden` / `not_found` / `rate_limited` | retain local metadata/progress; no auto-login/retry |
| DNS/TLS/timeout/5xx | `provider_unavailable` | no partial DTO or raw exception |
| Bad schema/duplicate chapter/page/asset ID | `invalid_payload` | reject whole operation result |
| Metadata/asset bound exceeded | `response_too_large` | stop stream; no partial success |
| Cancellation | `cancelled` | close request/reader resources |
| Final response/mutation uncertain | `unknown` | no success, deletion, or guessed remote state |

### 7.7 Result uncertainty matrix

| Proven facts | Classification | Allowed consequence |
|---|---|---|
| Full bounded response and DTO valid | `success` | display exact operation result |
| Detail valid, chapter request failed | detail success + chapter error | keep layers separate; no complete-flow claim |
| Page list incomplete or order invalid | `invalid_payload` | do not render partial chapter as complete |
| Asset request sent, completion unproven | `unknown` | no cached/downloaded/success claim |
| Remote chapter absent | `not_found` or diff fact | do not delete local chapter/progress/assets |
| Social mutation response lost | `unknown` | show unresolved state; no optimistic local mirror |
| Local progress commit proven | local success | independent of remote read/mutation outcome |

## 8. N4G handoff requirements

N4G begins only after a real Provider has a fully completed and explicitly
approved `comic-source-approval-draft.md`, static legal/terms evidence, exact
hosts/operations, reviewed fixtures, and a fixed Python adapter plan. Initial
scope is `search`, `detail`, `chapter_list`, and `page_list`; category and asset
operations require explicit inclusion. Auth, favorites, comments, rating,
remote source updates, JavaScript, caching, and download remain out of scope
unless a later GOAL and Approval authorize each one.
