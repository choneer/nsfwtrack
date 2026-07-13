# NSFWTrack

NSFWTrack is a local single-user content record manager / collection tracker.

Current release: `v1.0.4 / non-root Docker runtime`.

Release: [NSFWTrack v1.0.4](https://github.com/choneer/nsfwtrack/releases/tag/v1.0.4).

Current status: `stable v1.0.4 — code development and WSL acceptance complete`.

Current development: `Phase 3-A5 media library search and pagination is complete on main and
not yet released; application Schema remains 2`.

N100 deployment: `not started; waits for explicit user authorization`.

NSFWTrack remains intentionally local-only. It is designed for manual records,
local SQLite persistence, LAN deployment, and simple personal collection
management.

## Completion Audit

Phase 2-K1 found no genuine TODO / FIXME marker, stub route, 501 response, or
dead navigation entry. Phase 2-K2 closed the three pre-use findings and the
current `v1.0.4` suite contains 358 passing tests.

Code development and WSL acceptance through `v1.0.4` are complete. See
[COMPLETION_AUDIT.md](COMPLETION_AUDIT.md) for the archived K1 / K2 evidence.

- Phase 2-K2 closed the local media-path, bulk / clear confirmation, deployment
  placeholder-secret, focused F4 test, and upgrade-runbook gaps.
- N100 / target-host deployment has not started and is not a current development
  task. It must wait for explicit user authorization.

Product feature development has explicitly reopened for the bounded Phase 3-A1
through A5 scopes below. Any expansion beyond them still requires separate approval.

## Unreleased: Phase 3-A5 Media Library Search and Pagination

The media-file card list under `/media-library` now has an independent,
read-only query layer for larger local libraries. The complete scan still feeds
the unchanged A3 matching and A4 item-candidate flows; only the browsed media
cards are searched, filtered, sorted, and paged.

- `media_q` performs local NFKC-normalized, case-insensitive substring matching
  against both the relative filename/path and the `/media/...` path. Searches
  longer than 200 characters safely fall back to an empty search.
- `media_status` supports all, available, damaged/unavailable, used, and unused.
  Used status is derived from current item-cover and creator-avatar references;
  no media or association is changed while filtering.
- `media_sort` supports filename ascending/descending and byte size
  ascending/descending, with deterministic filename/path tie breaking.
- `media_page` always displays at most 20 cards and safely falls back or clamps
  invalid, negative, non-numeric, empty, and out-of-range values.
- Media pagination preserves the canonical search/filter/sort state plus the
  current `match_page` and `create_page`. A3 and A4 pagination preserve each
  other, `media_page`, and all media filters. Upload, manual assignment, and
  candidate-confirmation redirects retain the same canonical state.
- Empty scans and empty filtered results have distinct bilingual states. Invalid
  status or sort values fall back to all media and filename ascending without a
  500 response or database write.

Phase 3-A5 performs no POST or mutation of its own and adds no table, Schema
change, migration, dependency, external request, AI/image recognition, media
file operation, version change, Release, or deployment.
The full local suite contains 424 passing tests after this phase.

## Unreleased: Phase 3-A4 Create Items from Unmatched Media

The local media library now offers a second read-only candidate flow for valid,
unused images that have no existing A3 item-cover or creator-avatar match.
Nothing is created until an authenticated manual confirmation is submitted.

- Suggested titles come from the filename without its image extension. The
  cover convention is removed from the title, while avatar-convention files are
  excluded from item creation entirely.
- Suggested titles remain editable until confirmation. The preview marks empty
  or oversized defaults, exact existing titles, normalized existing titles, and
  normalized conflicts among default candidate titles so they can be corrected.
- Single and current-page bulk POSTs regenerate the complete candidate set,
  enforce the current 20-row page, validate every local file again, and use only
  the submitted final titles. Forged, stale, occupied, missing, invalid, or
  cross-page candidates are rejected.
- Final titles must contain 1–255 characters and must not exactly or normally
  collide with an existing item or another title selected in the same batch.
  Any validation, file, insert, flush, or commit failure rolls back the entire
  batch, leaving no partially created items.
- A successful confirmation creates each item and assigns the candidate's
  existing local path as `cover_path`. It does not create, download, inspect,
  move, rename, overwrite, or delete any media file.

Standard mode requires browser and server confirmation; strict mode also
requires exact `CONFIRM`. Phase 3-A4 adds no table, Schema change, migration,
dependency, external request, AI/image recognition, version change, Release,
or deployment.
The full local suite contains 416 passing tests after this phase.

## Unreleased: Phase 3-A3 Local Media Candidate Matching

`/media-library` now generates explainable item-cover and creator-avatar
candidates from validated, unused local media filenames. Candidate generation
is read-only: opening or paging the screen never changes an association.

- Matching first compares NFKC-normalized, case-insensitive names exactly, then
  compares normalized names containing only letters and numbers. A final
  `.cover`, `-cover`, `_cover`, or space-separated `cover` suffix limits the
  target to items; the equivalent `avatar` suffix limits it to creators.
- Every candidate displays its target type, exact or normalized matching reason,
  and high or medium confidence. A media file matching multiple targets, or a
  target matching multiple files, is marked as an ambiguous conflict and cannot
  be selected or applied.
- Only available media with no current reference, items without covers, and
  creators without avatars are considered. Single and current-page bulk POSTs
  regenerate the candidate set before writing and reject stale, conflicting,
  cross-page, unavailable, or newly occupied targets.
- Standard mode requires browser and server confirmation. Strict mode also
  requires the exact text `CONFIRM`. A valid bulk operation assigns only the
  manually selected candidates from its current 20-row page in one transaction.
- Matching only updates existing `cover_path` or `avatar_path` fields. It never
  creates, downloads, recognizes, renames, moves, overwrites, or deletes a media
  file and never overwrites an existing cover or avatar association.

Phase 3-A3 adds no table, Schema change, migration, dependency, external network
request, AI, image-recognition, recommendation, version change, or deployment.
The full local suite contains 407 passing tests after this phase.

## Unreleased: Phase 3-A2 Local Media Library

`/media-library` scans app-owned images under `data/media`, shows whether each
image is used by an item cover or creator avatar, and accepts one or multiple
local uploads. Each batch is limited to 20 files and each file to 10 MB.

- AVIF, GIF, JPEG, PNG, and WebP are accepted only when extension, declared
  MIME type, and file structure agree. SVG, HTML, disguised, truncated, and
  unsupported files are rejected.
- Uploaded bytes are named and deduplicated by SHA-256 under
  `data/media/library`; repeated content is not saved twice. Each new file is
  fully written and fsynced through a random same-directory temporary file,
  then atomically published. A failed batch removes all of its temporary and
  newly published files.
- Directory scanning never follows symbolic links. Serving and assignment also
  reject symlinked, missing, oversized, invalid, or escaping paths.
- A valid library image can set or replace an item cover or creator avatar.
  Clearing either association uses a confirmed authenticated POST and leaves
  the media file intact; strict mode also requires `CONFIRM`.
- Missing or damaged assigned files render as the existing safe empty state and
  return 404 from `/media/...` instead of causing a page error.

The feature uses the existing `cover_path` and `avatar_path` columns and the
existing `./data:/app/data` mount. It adds no table, Schema change, dependency,
external request, image recognition, recommendation, or AI capability.
JSON/CSV backups preserve media path references but do not embed image bytes;
back up the stopped `data` directory to preserve both SQLite and media files.

## Unreleased: Phase 3-A1 Source Links and Local Bookmark Import

Phase 3-A1 stores user-provided source URLs without requesting them. One item
can have multiple sources, and each source stores the original URL, a globally
unique normalized URL, an optional title, and its creation time.

- Item detail pages list sources and support adding one URL or deleting one
  source after explicit confirmation. Deleting a source never deletes its item.
- `/sources/import` accepts pasted text with one URL per line,
  `title<TAB>URL`, or a user-uploaded local browser bookmarks HTML file.
- Every bulk operation is read-only until its preview reports new, duplicate,
  invalid, and conflicting rows. Confirmed writes revalidate the same data and
  commit all new items and sources in one transaction; failures roll back the
  batch.
- HTTP/HTTPS URLs are normalized by scheme, IDNA host, default port, percent
  escapes, root path, and fragment removal. URLs containing credentials,
  control/space characters, unsupported schemes, or no host are rejected.
- When no title is supplied, a readable host/path title is created locally.
  No title, metadata, image, or webpage is fetched from the URL.
- JSON backups include the optional `item_sources` table. CSV item export and
  CSV/JSON item import include a `sources` field; old backups and imports that
  omit sources remain compatible.

Schema 2 adds only `item_sources`. Existing Schema 1 databases do not migrate
at startup: open `/schema-upgrade`, review the read-only dry-run, confirm a
fresh backup, and explicitly apply `create_item_sources`. Existing items and
all prior tables remain unchanged.

The network boundary remains strict: NSFWTrack does not request external
webpages, fetch remote images, crawl, use site adapters, synchronize sources,
recommend content, or run AI analysis.

## Features in v1.0.4

`v1.0.4` publishes the Phase 2-L8 fixed non-root Docker runtime identity and
data-ownership migration. It adds no product feature, dependency, database
change, schema migration, or security-configuration relaxation.

- The production image creates the `nsfwtrack` user with fixed UID/GID
  `10001:10001`. Dockerfile `USER` makes both the application and image
  `HEALTHCHECK` run as that non-root identity.
- The v1.0.3 read-only root filesystem, all-capability drop,
  `no-new-privileges`, `/tmp` tmpfs, and `/app/data` writable mount remain in
  force. CI verifies the configured and actual identity plus these boundaries.
- Before upgrading v1.0.3 or any earlier deployment, stop the service, complete
  a verified backup, then migrate `data` ownership to `10001:10001` while
  keeping mode `0700`. The exact commands are in the upgrade checklist below.
- SQLite creation, Schema 1, healthy HTTP/security headers, and persistence
  across container removal and recreation are verified in CI.

## Features in v1.0.3

`v1.0.3` publishes the Phase 2-L7 Docker runtime security baseline and the
matching deployment-permission guidance. It adds no product feature,
dependency, database change, schema migration, or container-user change.

- Production and CI Compose run with a read-only root filesystem, drop all
  Linux capabilities with `cap_drop: ALL`, and enable `no-new-privileges`.
- `/tmp` is a bounded tmpfs while `/app/data` remains the only persistent
  writable application mount; CI verifies both writable and read-only paths.
- Rootful Docker deployments must prepare the host data directory ownership
  and permissions before startup. Existing installations should stop the
  service and take a verified backup before changing that ownership.

## Features in v1.0.2

`v1.0.2` publishes Phase 2-L1 through L6 maintenance and CI hardening. It adds
no product feature, database change, schema migration, or external integration.

- TestClient uses the supported `httpx2` path, and direct runtime/development
  dependencies are pinned to the versions verified on Python 3.12.
- CI runs `pip check` and full pytest, applies minimal browser security headers,
  and performs an isolated production-image Docker smoke test.
- The workflow token is limited to read-only repository contents, while stale
  runs for the same workflow/ref are cancelled automatically.
- The production image uses a Python-standard-library `/login` health check;
  Docker smoke waits for `healthy` before the existing HTTP and security-header
  assertions, with failure logs and unconditional cleanup retained.

## Features in v1.0.1

`v1.0.1` publishes the Phase 2-K1 completion audit and Phase 2-K2 use-before
boundary closure. It adds no product feature, dependency, database structure,
schema-version change, production migration, or external request.

### Phase 2-K2 Use-Before Boundary Closure

- `cover_path` and `avatar_path` accept only app-owned `/media/...` raster
  image paths. External URLs, protocol-relative paths, data URLs, traversal,
  encoded or backslash separators, query strings, fragments, and unsupported
  file types are rejected by API, page, and backup-restore boundaries.
- Item templates revalidate stored cover paths before rendering, so legacy
  external values cannot trigger a browser request.
- Every current-page bulk write, state clear, and relationship detach requires
  browser confirmation plus a server `confirm=1` marker. Strict mode also
  requires exact `CONFIRM` before any write.
- Bulk writes and state clearing are guarded modifications that may affect
  multiple records or erase state fields. Single relationship detach is a
  lower-impact guarded modification because both entities remain and can be
  linked again. Both classes honor strict mode; entity deletion and merge keep
  their existing destructive notices and backup guidance.
- Startup rejects the exact password and secret placeholders shipped in
  `.env.example` without echoing their values.
- Focused F4 tests cover complete Chinese / English warnings, backup links,
  `dangerous_only`, `always`, strict confirmation, and the clean-report state.

## Features in v1.0.0

`v1.0.0` publishes Phase 2-I1 through I4: reproducible performance auditing,
bounded query and pagination improvements, unified safe errors and request
logs, and the final security and compatibility audit. It adds no external
content source, dependency, index, database structure, schema-version change,
or production migration.

### Phase 2-I4 Release-Freeze Audit

- Every non-public page and API route is covered by the existing session
  authentication boundary. Public access remains limited to login and local
  language selection.
- Unsafe browser requests with an `Origin` or `Referer` header must match the
  request origin. Headerless local API clients remain compatible, while the
  session cookie keeps `SameSite=Lax` as a second browser-side boundary.
- Login clears pre-authentication session state except the selected language.
  Logout invalidates previously signed authenticated cookies for the running
  application instance, and an application restart also invalidates them.
- Dangerous page operations require a server-validated confirmation marker in
  addition to browser confirmation. Strict mode still requires the exact text
  `CONFIRM`.
- Item detail GET is read-only; its existing local activity count is recorded
  by an authenticated same-origin POST after the page loads.
- Session cookies are `HttpOnly` and `SameSite=Lax`. Deployments that terminate
  HTTPS at the application can set `SESSION_COOKIE_SECURE=true`.
- Local redirect targets reject external, protocol-relative, backslash, and
  control-character forms. Malformed login JSON returns a bounded 400 response.
- CSV / JSON imports have a configurable upload limit and fail before parsing
  or writing when the limit is exceeded.
- Five isolated database compatibility scenarios, rollback paths, bilingual
  behavior, safe errors and logs, and the 100 / 1,000 / 10,000 performance
  matrix were rerun without touching the default data volume.
- `CURRENT_SCHEMA_VERSION` remains `1`, and the production migration registry
  remains empty. No production migration is invented for the release.

### Phase 2-I3 Error Handling And Request Logs

Phase 2-I3 provides one safe error boundary for page and API requests without
changing business operations, transactions, the database schema, or project
dependencies.

- Page requests use one bilingual error template for 400, 403, 404, 405, 409,
  422, and 500 responses and retain the original status code.
- `/api/` requests and explicit JSON clients receive `error`, `message`, and
  `request_id`. The existing `detail` field remains available for compatible
  expected errors and validation details.
- 405 responses preserve `Allow`. FastAPI validation errors retain type,
  location, and message while submitted values are not echoed.
- Every HTTP response includes `X-Request-ID`. A client value is accepted only
  when it is a canonical UUID or 32-character UUID hex value; every other
  value, including credential-shaped strings, is replaced with generated UUID
  hex before the response or log is written.
- Local request logs contain request ID, method, sanitized route path, status,
  duration, and exception type for failures. They do not record query strings,
  request headers, cookies, authorization values, forms, passwords, or upload
  bodies.
- Matched requests log only their application-owned route template. Unmatched
  routes use the fixed value `/[unmatched]` instead of the raw request path.
- Unhandled exceptions return a generic 500 response and request ID. Exception
  values, traceback text, SQL, server paths, environment values, and secrets
  are not returned or written by the application request logger.
- Expected business errors remain normal 4xx responses or existing page flash
  results. Backup, import, merge, health repair, settings, and schema upgrade
  keep their existing transaction and rollback behavior.
- Login protection, POST-only mutations, browser confirmation, server-side
  confirmation, and strict `CONFIRM` checks are unchanged.
- No external logger, telemetry service, monitoring dependency, schema change,
  tag, or GitHub Release is included.

### Phase 2-I2 Query And Pagination Optimization

Phase 2-I2 applies the verified I1 findings without adding indexes, changing
the schema, increasing the schema version, or adding dependencies.

- Item pages load tag, creator, collection, and state relationships only for
  the current result page. Filter metadata no longer recursively loads related
  item graphs.
- Cleanup candidates use scalar metadata fields and relation counts. Duplicate
  and cleanup comparison pairs are paged while compare / merge behavior stays
  manual and unchanged.
- Tags, creators, and collections use 50-row pages.
- Collection detail uses separate 20-row pages for members and available
  items. Available items support local title search, and the previous N+1 is
  removed.
- Data-health keeps exact total and fix counts while rendering at most 200
  issue details.
- Shared page context reads settings once per request. Workbench saved views
  are limited in SQL before rendering.
- Stats uses consolidated aggregates and SQL date buckets while preserving the
  existing dashboard and API structures.
- At 10,000 fixture items, measured queries fell from 258 to 11 for items, 249
  to 4 for cleanup, 165 to 9 for collection detail, and 28 to 11 for stats.

See [PERFORMANCE.md](PERFORMANCE.md) for the complete I1 / I2 comparison and
remaining scan paths that require a separately approved real migration.

### Phase 2-I1 Performance Baseline

Phase 2-I1 adds analysis and test tooling only. It does not change existing
queries, business behavior, database structure, indexes, or dependencies.

- `scripts/profile_queries.py` creates disposable SQLite fixtures with 100,
  1,000, and 10,000 items and removes them after the audit.
- `app/services/performance_audit.py` runs fixed project operations through a
  SQLite `query_only` connection, blocks writes, counts SQL statements, records
  repeated fingerprints and elapsed time, and captures
  `EXPLAIN QUERY PLAN` summaries.
- Coverage includes item list pagination / filters / sorting, workbench, stats,
  metadata pages, collection detail, saved views, activity, duplicates,
  cleanup, data health, backup preview / validation, and import dry-run.
- The baseline confirms item-page and cleanup query amplification, one
  collection-detail N+1, unpaginated metadata / candidate paths, and repeated
  stats scans. These findings are documented but intentionally not fixed in
  I1.
- [PERFORMANCE.md](PERFORMANCE.md) contains the measured matrix, verified
  findings, unaffected paths, I2 priorities, and migration-required index
  suggestions.

Run the complete isolated audit with:

```bash
.venv/bin/python scripts/profile_queries.py \
  --sizes 100 1000 10000 \
  --output /tmp/nsfwtrack-performance-i1.json
```

## Features in v0.9.0

`v0.9.0` adds Phase 2-H1 database version preflight and Phase 2-H2 explicit
migration planning, dry-run, and apply flows on top of `v0.8.0`.

### Phase 2-H2 Explicit Migration Framework

Phase 2-H2 adds a lightweight, code-only SQLite migration framework. The
production migration registry is currently empty and
`CURRENT_SCHEMA_VERSION` remains `1`; this phase does not invent a production
migration or change an existing business table.

- Every code migration declares `from_version`, `to_version`, `name`, a
  read-only preview, an apply function, a source-version pre-check, and a
  target-version post-check.
- Registry construction rejects duplicate, disconnected, skipped, reversed,
  or cyclic paths. Upgrade planning reads the database version before resolving
  the continuous path to the application-owned target version.
- A recorded lower-version database may start in upgrade-required mode without
  first matching the newest structure. Each migration owns its old-structure
  pre-check, and each target structure is checked after apply.
- `GET /schema-upgrade` shows the current state without migrating.
- `POST /schema-upgrade/preview` runs a protected read-only dry-run. SQLite
  `query_only`, a read-only authorizer, and rollback prevent table, business
  data, and version-record writes, including accidental writes in preview code.
- Dry-run lists current / target versions, ordered steps, expected changes,
  warnings, errors, and pre-check status. Later-step checks are marked deferred
  because preview never applies earlier steps; apply runs every check in order.
- `POST /schema-upgrade/apply` rereads the current version and resolves the path
  inside one transaction. Each step, post-check, and `schema_migrations` insert
  commits atomically; any exception or failed post-check rolls back the chain.
- Apply requires login, POST, browser confirmation, existing server-side danger
  confirmation, and explicit acknowledgement of the pre-upgrade JSON backup.
  Strict mode still requires the exact text `CONFIRM` on the server.
- The routes accept no SQL, table name, target version, downgrade, check bypass,
  or arbitrary migration operation from the user.
- Startup never runs the migration registry. Upgrades are always explicit.
- `schema_migrations` remains outside JSON backup and restore.

### Phase 2-H1 Database Version Preflight

Phase 2-H1 adds an internal schema version record and startup compatibility
check. The current application schema version is `1`.

- `schema_migrations` is an internal SQLite table with unique `version`,
  descriptive `name`, and `applied_at` fields.
- A new empty database creates all current tables and registers baseline
  version `1` in the same initialization transaction.
- A legacy database without `schema_migrations` must already contain every
  required current business table and column before baseline registration.
  Missing structure stops initialization and does not create a version record.
- A database at the current version starts normally.
- A lower database version is reported as requiring an upgrade. NSFWTrack does
  not change the recorded version or execute a migration in this phase.
- A database version higher than the application refuses startup and gives a
  safe compatibility and backup message.
- The login-protected `/settings` page shows the application version, database
  version, status, latest registration time, and a JSON backup reminder.
- The status area is read-only. There is no page, URL, form, downgrade action,
  or bypass action that can change a schema version.
- `schema_migrations` is not exported, previewed, validated as restorable data,
  or restored from JSON backups. A backup cannot overwrite the local schema
  version.

Phase 2-H1 does not modify, delete, or rebuild existing business tables or
fields. It does not run a real migration, add Alembic, add a dependency,
automatically upgrade or downgrade data, or restore a backup.

The v0.9.0 application keeps `CURRENT_SCHEMA_VERSION = 1` and an empty
production migration registry. There is no invented `1 -> 2` production
migration. Startup performs compatibility checks only and never runs an
upgrade; any future upgrade must be explicitly triggered after reviewing the
dry-run and creating a fresh JSON backup.

## Features in v0.8.0

`v0.8.0` adds Phase 2-G1 local settings and Phase 2-G6 safer,
consistent dangerous-operation confirmations on top of `v0.7.0`.

Phase 2-G1 adds a login-protected local settings page at `/settings`.

- Settings are stored in the local SQLite `app_settings` table.
- Supported basic keys are `default_language`, `default_page_size`,
  `default_sort`, `default_sort_dir`, and `default_home`.
- Setting keys and values are validated through fixed allowlists. Unknown keys,
  external URLs, script-like arbitrary values, and unsupported values are
  rejected without writing to the database.
- `POST /settings` saves settings, and `POST /settings/reset` restores defaults
  only with explicit confirmation.
- Default page size and default sorting apply to `/items` only when the URL does
  not provide `page_size` or `sort`.
- Explicit URL parameters and saved view query strings keep priority over local
  defaults.
- Default language applies only when the session has no explicit language
  choice from `/set-language`.
- The dashboard workbench shows the configured default-home entry and highlights
  matching local entries such as items, stats, or recent activity.
- JSON backup export, preview, validation, and restore include `app_settings`.
  Older JSON backups without `app_settings` remain compatible.

Phase 2-G6 reuses `app_settings` to unify dangerous-operation preferences.

- `danger_confirmation_mode` accepts only `standard` or `strict`.
- `backup_reminder_mode` accepts only `always` or `dangerous_only`; safety
  notices cannot be disabled.
- `danger_result_detail` accepts only `summary` or `detailed` and changes only
  result presentation.
- Standard mode preserves the existing login, write-method, browser confirm,
  server confirmation, and rollback behavior.
- Strict mode adds an exact server-validated `CONFIRM` text requirement. A
  missing, wrong, invalid, or unreadable setting never disables confirmation;
  invalid confirmation settings safely fall back to standard mode.
- Unified notices show the operation object, consequence, deletion scope,
  recoverability, applicable JSON backup recommendation, and current mode.
- Coverage includes item and current-page bulk deletion, tag / creator /
  collection deletion, item and metadata merge, recent activity clearing,
  backup restore, data health manual fixes, and settings reset.
- JSON backup export, preview, validation, and restore include the three G6
  settings. Older backups without them continue to use safe defaults.
- No setting can add one-click delete / merge / repair, bypass login, change a
  mutation into GET, skip browser or server confirmation, widen an operation's
  data scope, or weaken rollback behavior.

This settings center is local-only. It does not add multi-user preferences,
cloud sync, external accounts, plugins, AI recommendations, external content
sources, new dependencies, or changes to existing database fields.

## Features in v0.7.0

`v0.7.0` adds local Phase 2-F data health and validation capabilities on top of
`v0.6.0`:

- Phase 2-F1 data health check / local data self-check.
- Phase 2-F2 backup file validation, restore dry-run, and import dry-run
  reporting.
- Phase 2-F3 low-risk manual data health fixes.

Phase 2-F3 adds low-risk manual data health fixes on `/data-health`.

- Fixes are limited to orphaned and duplicate `item_tags`, `item_creators`, and
  `item_collections` rows; orphaned `item_activity`; negative
  `view_count` / `edit_count`; and risky or unknown
  `saved_views.query_string` parameters.
- The page only shows a fix button when the matching issue exists in the
  current health report.
- Each fix requires login, `POST`, browser confirmation, and a server-side
  `confirm=1` check.
- The server accepts only whitelisted `fix_type` values and does not accept
  table names, column names, SQL, or `fix_all`.
- Fix failures are rolled back before returning an error flash message.
- Result summaries report deleted, corrected, and skipped row counts.
- These fixes do not delete items, tags, creators, or collections. They only
  remove relation/helper rows or normalize saved views query strings.
- Export a JSON backup from `/backup` before running any manual fix.

Phase 2-F2 adds backup validation, restore dry-run reporting, and import
dry-run reporting.

- The `/backup` page can validate a local JSON backup before restore and show a
  structured report with `error`, `warning`, and `info` levels.
- Backup validation checks schema, supported tables, unknown top-level fields,
  required fields, unknown row fields, duplicate ids, invalid `status` /
  `rating`, invalid `extra` JSON, orphaned relations, duplicate relations,
  saved views parameters, and item activity references.
- Older JSON backups that do not contain newer optional tables such as
  `saved_views` or `item_activity` remain compatible and are treated as empty
  optional tables during validation / preview.
- Restore dry-run reports table counts, relation counts, expected skipped rows,
  and whether the current database already has data that a real restore would
  append / merge with.
- CSV / JSON import previews now include a dry-run report with importable rows,
  skipped rows, row errors, unknown fields, invalid `rating` / `status`,
  abnormal `tags` / `creators` fields, duplicate title candidates, and
  existing-title warnings.
- Dry-run reports do not write to the database, delete business data, restore
  backups, import rows, auto-create tags / creators / collections, modify saved
  views / activity, auto-fix files, auto-merge data, or call external services.
- Before a real restore or import, export a fresh JSON backup from `/backup`.

Phase 2-F1 adds a local data health check page at `/data-health`.

- The page requires login and is linked from the authenticated top navigation
  and the dashboard workbench.
- The report is read-only. It does not modify the database, delete business
  data, repair records, merge records, import data, or call external services.
- The summary shows the overall status, total issue count, warning / problem
  counts, and issue counts grouped by items, relations, duplicate relations,
  saved views, and activity.
- Item checks report empty titles, invalid status / rating values, missing or
  invalid timestamps, updated-before-created timestamps, and invalid `extra`
  JSON.
- Relation checks report orphaned `item_tags`, `item_creators`, and
  `item_collections` rows that point to missing items, tags, creators, or
  collections.
- Duplicate relation checks report repeated item-tag, item-creator, and
  item-collection links.
- Saved views checks report empty names, empty or malformed `query_string`
  values, unknown parameters, blocked `page` / `next` / `redirect` parameters,
  and external URL values.
- Activity checks report `item_activity` rows that point to missing items,
  negative `view_count` / `edit_count` values, and invalid activity timestamps.

When the page reports issues, export a JSON backup from `/backup` before doing
any manual cleanup. The data health flow does not provide automatic repair,
one-click repair, automatic deletion of core entities, automatic merge, AI
judgment, external lookup, URL import, crawler / adapter integration, cloud
sync, or multi-user features.

## Features in v0.6.0

`v0.6.0` adds local Phase 2-E usage efficiency enhancements on top of
`v0.5.0`:

- Phase 2-E1 saved item-list views / common views.
- Phase 2-E2 recent views and recent edits.
- Phase 2-E3 quick action entry points and workbench improvements.

These features stay local-only. They do not add AI recommendations, smart
analysis, automatic classification, external content sources, URL import,
crawlers, adapters, cloud sync, multi-user sharing, third-party analytics, new
dependencies, or changes to existing database fields.

### Phase 2-E3 Quick Actions And Workbench

Phase 2-E3 organizes local navigation entry points on the dashboard and item
list:

- The dashboard now includes a workbench quick action grid for creating an
  item, opening the item list, saved views, recent activity, stats,
  collections, duplicate item detection, metadata cleanup, import, and backup.
- The dashboard shows a small saved views panel so local saved filters can be
  opened from the workbench without saving or updating anything automatically.
- Recent views and recent edits remain visible from the dashboard with links to
  the full recent activity page.
- The item list now has a quick action section for creating items, jumping to
  saved views / save-current-view controls, recent activity, duplicate
  detection, metadata cleanup, import, and backup.
- Quick action entries are navigation links only. They do not delete, merge,
  clear activity, restore backups, or run any dangerous action directly.
- Existing login protection, POST-only mutations, browser confirmation prompts,
  saved views, filters, sorting, pagination, and current-page bulk editing are
  preserved.
- The quick action layout uses existing Jinja2 templates and CSS, remains
  mobile-friendly, and adds no front-end framework or build step.

Phase 2-E3 does not add database tables, change existing database fields, add
dependencies, external content sources, URL import, crawlers, adapters, AI
recommendations, smart analysis, automatic classification, cloud sync,
multi-user sharing, third-party analytics, or activity trend charts.

### Phase 2-E2 Recent Activity

Phase 2-E2 adds local recent activity for item records:

- Item detail visits are recorded as recent views with `last_viewed_at` and
  `view_count`.
- User-driven item edits are recorded as recent edits with `last_edited_at` and
  `edit_count`.
- Recent edit tracking covers basic item edits, state / rating / review
  updates, tag changes, creator changes, collection changes, and current-page
  bulk edits.
- `/activity` shows recent views and recent edits, requires login, and is
  read-only.
- `POST /activity/clear` clears only `item_activity` records after browser
  confirmation. It does not delete items, tags, creators, collections, or saved
  views.
- The dashboard shows recent views and recent edits, the item list links to the
  activity page, and item detail pages show local activity counts and
  timestamps.
- JSON backup export / preview / restore includes `item_activity` while
  remaining compatible with older backups that do not contain this table.

Activity is stored only in the local SQLite `item_activity` table. NSFWTrack
does not record IP addresses, User-Agent values, device fingerprints, external
referrers, or off-site URLs. This feature does not add recommendations, AI
analysis, automatic classification, external content sources, URL import,
crawlers, adapters, cloud sync, third-party analytics, multi-user activity
feeds, new dependencies, or changes to existing database fields.

### Phase 2-E1 Saved Views

Phase 2-E1 adds local saved views for the item list page:

- The item list can save the current keyword, status, tag, creator, collection,
  minimum rating, time range, sort, and page-size settings as a named view.
- Saved views are stored locally in the SQLite `saved_views` table.
- Saved views can be applied with one click, updated to the current filter
  state, or deleted with browser confirmation.
- Create, update, and delete actions require login and POST.
- Applying a saved view is a GET redirect back to `/items` and does not modify
  the database.
- Saved view query strings are filtered through a whitelist, normalized, and
  stored in stable order.
- Unknown parameters, page numbers, session data, cookies, CSRF values, and
  external redirect targets are not stored.
- JSON backup export / preview / restore includes saved views while remaining
  compatible with older backups that do not contain `saved_views`.

This feature stays local-only. It does not add AI recommendations, smart
classification, external content sources, URL import, crawlers, adapters, cloud
sync, multi-user shared views, new dependencies, or changes to existing
database fields.

## Features in v0.5.0

`v0.5.0` adds local Phase 2-D data cleanup and manual merge support on top of
`v0.4.0`:

- Phase 2-D1 duplicate item detection and manual merge.
- Phase 2-D2 tag / creator / collection cleanup and manual merge.

These features stay local-only. They do not add automatic merging, AI judgment,
external content sources, URL import, crawlers, adapters, recommendation
systems, cloud sync, multi-user support, new dependencies, or database schema
changes. Export a JSON backup before merging duplicate items or metadata.

### Phase 2-D1 Duplicate Detection

Phase 2-D1 adds local duplicate candidate detection and manual merge support on
top of `v0.4.0`:

- `/duplicates` lists read-only duplicate candidate groups.
- Exact title matching trims leading and trailing whitespace for detection only.
- Normalized title matching uses Unicode NFKC, trimming, casefolding, and
  whitespace collapsing for detection only.
- Candidate groups show the match type, match key, item count, title, state,
  rating, and tag / creator / collection counts.
- `/duplicates/compare` shows a side-by-side comparison of the primary item and
  duplicate item before merge.
- Manual merge keeps the primary item and deletes the duplicate item only after
  a POST submission and browser confirmation.
- Tags, creators, and collections are transferred to the primary item without
  creating duplicate relations and without deleting tag, creator, or collection
  records.
- Missing primary summary / state / rating / review values can be copied from
  the duplicate; conflicting values keep primary by default unless the user
  explicitly chooses the duplicate value.
- `extra` JSON merges non-conflicting duplicate keys into the primary item and
  keeps primary values for conflicting keys.
- Merge results summarize relation transfers, field handling, `extra` merge
  counts, conflict counts, and duplicate deletion.

Phase 2-D1 is still local-only. It does not add external content sources, URL
import, crawlers, adapters, AI dedupe, image similarity, automatic bulk merge,
recommendation systems, cloud sync, multi-user support, database schema changes,
or new dependencies.

### Phase 2-D2 Metadata Cleanup

Phase 2-D2 adds local duplicate metadata candidate detection and manual merge
support for tags, creators, and collections:

- `/cleanup` lists read-only duplicate metadata candidate groups for tags,
  creators, and collections.
- Exact name matching trims leading and trailing whitespace for detection only.
- Normalized name matching uses Unicode NFKC, trimming, casefolding, and
  whitespace collapsing for detection only.
- Candidate groups show metadata type, match type, match key, object names, and
  related item counts.
- `/cleanup/compare` shows the primary object that will be kept and the
  duplicate object that will be deleted after merge.
- Manual merge keeps the primary tag / creator / collection and deletes the
  duplicate object only after a POST submission and browser confirmation.
- Related item links are transferred to the primary object without creating
  duplicate relations and without deleting any items.
- Collection description handling is conservative: duplicate description is
  copied only when primary is empty, conflicts keep primary by default, and the
  duplicate description overwrites primary only when explicitly selected.
- Merge results summarize the metadata type, kept object, deleted object,
  transferred relations, skipped duplicate relations, description handling, and
  duplicate deletion.

Before merging duplicate metadata, export a JSON backup from the Backup page.
This first version only supports manual confirmed merges. It does not support
automatic batch merging, merge-all actions, AI synonym detection, fuzzy
matching, external information lookup, external content sources, URL import,
crawlers, adapters, recommendation systems, cloud sync, multi-user support,
database schema changes, or new dependencies.

## Features in v0.4.0

`v0.4.0` adds local Phase 2-C collection management and completes collection
data coverage in backup / import flows on top of `v0.3.0`:

- Phase 2-C1 collections / list management.
- Phase 2-C2 backup / import support for collection data.

These features stay local-only. They do not add external content sources, URL
import, crawlers, adapters, recommendation systems, AI assistants, cloud sync,
multi-user support, new dependencies, or front-end build tooling.

### Phase 2-C1 Local Collections

`v0.4.0` includes local collections / list management. Collections are manual
local lists for grouping existing items into long-term watch lists, topic
lists, review queues, or any other personal organization scheme.

- Collections are stored in local SQLite tables `collections` and
  `item_collections`.
- The Collections page supports creating, editing, deleting, listing, and
  opening collection detail pages.
- Collection detail pages show the items in a collection and allow adding or
  removing existing local items.
- Item detail pages show linked collections and allow adding or removing one
  existing collection.
- The item list can filter by collection while preserving existing keyword,
  tag, creator, status, sorting, and pagination query-string state.
- Current-page bulk editing can add selected items to one existing collection
  or remove selected items from one existing collection.
- The stats page includes total collections, items with collections, items
  without collections, and a local collection ranking.
- Deleting a collection deletes only the collection and its item links. It does
  not delete any items.

### Phase 2-C2 Collection Backup And Import

`v0.4.0` also closes the local data loop for collections:

- JSON backups include `collections` and `item_collections` alongside the
  existing items, tags, creators, relations, and state records.
- JSON backup preview reports collection counts, item-collection relation
  counts, collections to create or merge, restorable collection links, skipped
  collection links, and collection-related errors.
- JSON restore merges collections and item-collection links. It does not delete
  existing items, does not overwrite the database, and skips bad collection
  links with a readable result summary.
- Old JSON backups without `collections` or `item_collections` remain
  compatible and restore as backups with no collection data.
- CSV export includes a `collections` field. Multiple collection names are
  separated with semicolons.
- CSV import and JSON import support an optional `collections` field. CSV uses
  semicolon-separated names, while JSON requires an array of strings.
- Import preview and import results include collection creation, collection
  link, skipped collection, and collections field error counts.
- Old CSV / JSON import files without a `collections` field remain compatible.

Collections in import files are still local user-provided data from uploaded
files. Phase 2-C2 does not add URL import, external content sources, crawlers,
adapters, recommendation systems, AI assistants, cloud sync, multi-user
support, new dependencies, or database schema changes.

## Features in v0.3.0

`v0.3.0` adds local Phase 2-B UI and stats enhancements on top of `v0.2.0`:

- Phase 2-B1 mobile / responsive UI polish.
- Phase 2-B2 local SQLite stats dashboard enhancements.

These features do not add external content sources, URL import, crawlers,
adapters, recommendation systems, AI analysis, prediction models, chart
libraries, new dependencies, database schema changes, cloud sync, or multi-user
support.

### Phase 2-B2 Stats Dashboard Enhancements

`v0.3.0` includes local SQLite statistics dashboard enhancements:

- The stats page now has overview cards for total items, tags, creators, items
  with state, items with rating, average rating, and recent 7 / 30 day created
  counts.
- Status and rating distributions use pure HTML / CSS bars, with empty states
  when there is no local data.
- Tag usage and creator link rankings show the top 10 local associations and
  their share of all local links.
- Recent activity shows 7 / 30 day created and updated counts plus a 7-day
  local trend block.
- Data completeness shows neutral counts for items without tags, creators,
  state records, ratings, or summaries.

These stats are generated only from local SQLite data. They do not add external
content sources, URL import, crawlers, adapters, recommendation systems, AI
analysis, prediction models, chart libraries, new dependencies, database schema
changes, cloud sync, or multi-user support.

### Phase 2-B1 Responsive UI Polish

`v0.3.0` also includes responsive UI polish on top of `v0.2.0`:

- The shared layout, cards, grids, forms, buttons, pills, and flash messages are
  tuned for narrow screens without changing backend behavior.
- The top navigation wraps into readable groups on mobile while keeping
  NSFWTrack, language switching, and login / logout access visible.
- The item list keeps advanced filters, current-page bulk editing, item cards,
  and pagination usable on phones and tablets.
- The detail page, import page, item / tag / creator forms, backup page, and
  stats page use mobile-friendly stacking or local table scrolling where needed.
- Long local titles, tags, creator names, and JSON / table content are contained
  with wrapping or section-level scrolling instead of creating whole-page
  horizontal overflow.

This polish does not add business features, database fields, dependencies,
external content sources, URL import, crawlers, adapters, recommendation
systems, AI assistants, cloud sync, or multi-user support.

## Features in v0.2.0

`v0.2.0` adds local Phase 2 enhancements on top of the Phase 1 MVP:

- Phase 2-A1 advanced local filters, sorting, and pagination.
- Phase 2-A2 current-page bulk editing.
- Phase 2-A3 item detail page enhancements.
- Phase 2-A4 CSV / JSON import enhancements.

These features continue to use only the local SQLite database. They do not add
external content sources, URL import, crawlers, adapters, remote image fetching,
recommendations, AI assistants, cloud sync, or multi-user support.

## Phase 2 Local Enhancements

### Phase 2-A1 Advanced List Filters

`v0.2.0` includes local list page improvements for finding and reviewing
existing records:

- Advanced local filters by keyword, status, one tag, one creator, minimum
  rating, and created / updated time range.
- Sorting by created time, updated time, title, or rating.
- Page size selection with `10`, `20`, `50`, or `100` items per page.
- Query-string based filters, sorting, and pagination so refreshes and copied
  links keep the same list state.
- Current filter summary, clear filters action, and clearer empty results.
- Chinese / English UI text for the new list controls.

These enhancements still only query the local SQLite database. They do not add
external content sources, crawlers, adapters, remote image fetching,
recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A2 Bulk Editing

`v0.2.0` also includes local bulk management for items on the current list page:

- Select individual items, select the current page, or clear the current
  selection.
- Bulk update status, add one existing tag, remove one existing tag, and set
  rating.
- Bulk delete selected items with browser confirmation and a visible dangerous
  action warning.
- Return to the previous list URL after bulk actions so filters, sorting, and
  page size are preserved where possible.
- Unified Chinese / English success and error messages showing processed and
  skipped counts.

Bulk editing only affects selected local SQLite records. It does not select
items across pages and does not add external sources, crawlers, adapters,
recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A3 Detail Page Enhancements

`v0.2.0` also improves the local item detail page:

- Detail information is split into basic information, state information, tags,
  creators, and actions.
- The page shows title, description, created / updated time, readable
  `extra JSON`, current state, rating, short review, linked tags, and linked
  creators.
- The detail page can update status, rating, and short review without opening
  the full item edit form.
- The detail page can add or remove one existing tag and attach or detach one
  existing creator.
- Item links from the list page carry a safe `next` value so returning from the
  detail page preserves filters, sorting, page, and page size where possible.
- Chinese / English UI text and flash messages cover the new detail actions.

Detail enhancements only operate on local SQLite records. They do not create
external content sources, crawlers, adapters, remote image fetching, automatic
sync, recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A4 Import Enhancements

`v0.2.0` also improves local CSV / JSON import:

- The import page provides downloadable CSV and JSON templates for the supported
  local import structure.
- The import page explains supported fields, required and optional fields, valid
  internal status values, rating rules, tag / creator handling, and local-only
  boundaries.
- CSV preview now shows a one-time field mapping table so custom source columns
  can map to `title`, `summary`, `status`, `rating`, `note`, `tags`,
  `creators`, `extra`, or be ignored.
- Import preview shows total rows, importable rows, error rows, tags to create,
  creators to create, the first five recognized rows, and readable error rows.
- Confirmed import shows a result summary with imported, skipped, created tag,
  created creator, tag link, creator link, state record, and error counts.
- Chinese / English UI text and tests cover templates, mapping, preview errors,
  partial valid imports, result summaries, and local-only import boundaries.

Import enhancements only accept uploaded local CSV / JSON files and only write
to the local SQLite database after confirmation. They do not add URL import,
external content sources, crawlers, adapters, remote image fetching, automatic
sync, recommendations, AI assistants, cloud sync, or multi-user support.

## Features in v0.1.0

- Single-user login protection with session cookies
- Chinese / English UI switching
- Local item CRUD
- Tag management
- Creator management
- Item state tracking
- Local title / tag / state search
- Simple stats
- CSV / JSON import
- Complete JSON backup export
- Readable CSV export
- JSON backup restore
- Backup preview before restore
- Configurable backup upload size limit
- Docker Compose deployment
- SQLite local persistence under `./data`
- GitHub Actions CI
- Basic test coverage

## Local Boundaries

The current development state is still a local single-user app. It does not
include external content sources, crawlers, adapters, remote image fetching,
third-party cookie/token management, automatic sync, multi-source search,
random exploration, recommendation systems, AI assistants, URL import, cloud
backup, scheduled backup, overwrite restore, complex permissions, or multi-user
support.

## Local Development

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
export APP_PASSWORD='change-me'
export SECRET_KEY='change-this-secret'
export DATABASE_URL='sqlite:///data/nsfwtrack.db'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and log in with `APP_PASSWORD`.

For a runtime-only environment, `pip install -r requirements.txt` is enough.
For development and CI, use `requirements-dev.txt` to install `pytest` and the
Starlette TestClient dependency (`httpx2`). Direct dependency versions are
pinned; this is not a full transitive lockfile.

## Configuration

Create a local `.env` from `.env.example` for Docker Compose, or export the same
variables before running `uvicorn` locally.

- `APP_PASSWORD`: the single local login password. Use a strong value on any
  LAN.
- `SECRET_KEY`: signs the session cookie. Use a long random value and rotate it
  if it leaks.
- `DATABASE_URL`: defaults to the SQLite database under `data/nsfwtrack.db`.
- `MAX_BACKUP_UPLOAD_MB`: maximum uploaded JSON backup size. The default is `5`.
- `MAX_IMPORT_UPLOAD_MB`: maximum uploaded CSV / JSON import size. The default
  is `5`.
- `SESSION_COOKIE_SECURE`: set to `true` only when the application receives
  HTTPS requests directly. It defaults to `false` for local HTTP and LAN use.

Do not commit `.env`. It is intentionally ignored by git.

The exact placeholder `APP_PASSWORD` and `SECRET_KEY` values from
`.env.example` are startup errors. Replace both before starting the app.

## Local Media

Prepare `./data/media` only after the rootful Docker data-directory ownership
step in the Docker Compose section below. The production image runs as fixed
UID/GID `10001:10001`, and the data mount makes this directory available inside
the container without another volume or dependency.

```bash
sudo install -d -m 0700 -o 10001 -g 10001 data/media
```

For `./data/media/covers/example.webp`, store this value in `cover_path`:

```text
/media/covers/example.webp
```

The accepted extensions are `.avif`, `.gif`, `.jpeg`, `.jpg`, `.png`, and
`.webp`. Media is served only after login. Use `/media-library` to upload,
scan, deduplicate, and associate local images. NSFWTrack never fetches, proxies,
or imports images from URLs; creator avatars follow the same local storage and
authenticated-serving rule as item covers.

## Docker Compose

Before the first rootful Docker start, prepare `./data` for the fixed container
UID/GID `10001:10001`. Existing v1.0.3 installations must use the stopped,
verified-backup migration procedure below before changing ownership.

```bash
cp .env.example .env
sudo install -d -m 0700 -o 10001 -g 10001 data
sudo install -d -m 0700 -o 10001 -g 10001 data/media
docker compose build
docker compose up -d
```

The service listens on port `8000` by default:

```text
http://localhost:8000
```

Stop it with:

```bash
docker compose down
```

Production Compose runs with a read-only container root filesystem, drops all
Linux capabilities, enables `no-new-privileges`, and mounts a 64 MiB tmpfs at
`/tmp`. The existing `./data:/app/data` mount remains writable and persistent
for SQLite and local media; other image paths remain read-only. This hardening
is combined with a fixed `nsfwtrack` UID/GID `10001:10001`; both the application
and image health check run as that non-root identity.

With rootful Docker, UID/GID `10001:10001` must own `./data` and its existing
contents because all capabilities, including `DAC_OVERRIDE`, are dropped. Keep
the data directory at mode `0700`; do not use `chmod 777`, a root startup
script, sudo/gosu in the container entry point, or startup-time automatic
`chown`.

## Install, Upgrade, And Rollback Checklist

Use this single checklist for the current local deployment line.

### First Install

1. Copy `.env.example` to `.env`, replace both shipped credential placeholders
   with a unique strong password and a long random secret, and keep `.env`
   outside version control.
2. Before the first rootful Docker start, create and secure the writable data
   and media directories for container UID/GID `10001:10001`:

   ```bash
   sudo install -d -m 0700 -o 10001 -g 10001 data
   sudo install -d -m 0700 -o 10001 -g 10001 data/media
   ```

3. Only after that preparation, run `docker compose build` and
   `docker compose up -d`.
4. Confirm
   `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login`
   returns `200`, log in from the intended LAN device, and keep the service off
   the public internet.
5. Export and validate a JSON backup after entering important data; also copy
   `data/nsfwtrack.db` only while the container is stopped.

### Upgrade From v0.9.x Or v1.0.x

1. Export a fresh JSON backup from `/backup`, run its preview / validation, and
   retain the verified file outside the deployment directory.
2. Run `docker compose down`, then copy the stopped `data/nsfwtrack.db` to a
   dated rollback file before changing code or images.
3. If the existing deployment is v1.0.3 or earlier and `./data` is not already
   owned by `10001:10001`, complete the ownership migration below while the
   service remains stopped.
4. Fetch the reviewed target tag or commit, verify its release notes, then run
   `docker compose build` and `docker compose up -d`.
5. Confirm `/login` returns `200`, log in, and inspect the schema status in
   `/settings`. A v1.0.4 or earlier database reports Schema 1 and requires the
   explicit `create_item_sources` upgrade to Schema 2.
6. Open `/schema-upgrade`, run the read-only preview, verify the fresh backup,
   then explicitly confirm apply. Startup and GET never migrate data.
7. Confirm `/settings` reports Schema 2 and existing item counts are unchanged;
   then test adding a local source URL. The migration creates only
   `item_sources` and does not alter an existing table.

### Migrate Existing v1.0.3 Data Ownership

Do not change a live data directory. First export and validate a fresh JSON
backup, then stop the service and make a byte-verified stopped copy outside the
deployment directory. Only after `cmp` succeeds should ownership change:

```bash
docker compose down
backup_dir="../nsfwtrack-data-v1.0.3-$(date +%Y%m%d-%H%M%S)"
sudo cp -a data "${backup_dir}"
sudo test -s "${backup_dir}/nsfwtrack.db"
sudo cmp -s data/nsfwtrack.db "${backup_dir}/nsfwtrack.db"
sudo chown -R 10001:10001 data
sudo chmod -R u+rwX,go-rwx data
sudo chmod 0700 data
sudo install -d -m 0700 -o 10001 -g 10001 data/media
docker compose build
docker compose up -d
```

After startup, confirm `/login` returns `200`, complete the explicit Schema 1 →
2 preview/apply flow, verify Schema 2 in `/settings`, and retain the stopped
backup until application data has been checked. Do not replace this procedure
with world-writable permissions, a root container, or an entry point that
changes ownership automatically.

### Rollback

1. Run `docker compose down` before replacing code or SQLite data.
2. Return to the previous reviewed tag or commit and restore the matching
   stopped SQLite copy. Do not mix a newer database with older code unless its
   schema status is explicitly compatible.
3. Rebuild, start, verify `/login`, and inspect the data before resuming use.
4. Never edit `schema_migrations` by hand. There is no automatic downgrade; a
   future schema-changing release must provide its own explicit rollback or
   backup-restore instructions.

## N100 LAN Deployment

On an N100 mini PC or similar home server, keep the app on the local network and
bind the Compose port mapping to `8000:8000`. After `docker compose up -d`, open
the service from another LAN device with:

```text
http://N100局域网IP:8000
```

Recommended local setup:

- keep `.env` only on the N100 host
- set a strong `APP_PASSWORD`
- set a long random `SECRET_KEY`
- keep `./data` on persistent storage
- back up `./data/nsfwtrack.db` and exported JSON backups regularly

## Data Persistence

Docker Compose mounts the host `./data` directory into the container at
`/app/data`. With the default `DATABASE_URL=sqlite:///data/nsfwtrack.db`, the
SQLite file is stored at:

```text
./data/nsfwtrack.db
```

Keep this directory out of git. For backups, prefer exporting JSON from
`/backup` and also copying the SQLite file while the container is stopped.

## Security Notes

NSFWTrack is a local single-user app. Do not expose it directly to the public
internet. If you put it behind a reverse proxy, frpc, VPN, or any other remote
access layer, confirm `APP_PASSWORD` is strong first and keep the remote access
layer protected as well.

NSFWTrack does not need third-party cookies, tokens, crawlers, or external
content source credentials in this release.

All authenticated browser writes use session authentication, same-origin
checking, and `SameSite=Lax`. Dangerous operations and guarded bulk / clear /
detach writes also require server-validated confirmation; strict mode adds
exact `CONFIRM`. These controls do not make the application suitable for direct
public-internet exposure. When using HTTPS directly, enable
`SESSION_COOKIE_SECURE=true`; with a reverse proxy, verify its scheme and host
forwarding before enabling that setting.

## Import

Open `/import` after logging in.

Available local-only actions:

- Download the CSV template: `GET /api/import/template/csv`
- Download the JSON template: `GET /api/import/template/json`
- Preview a local CSV upload on `/import`
- Preview a local JSON upload on `/import`
- Confirm import only after reviewing the preview

The CSV template uses these headers:

```text
title,summary,status,rating,note,tags,creators,collections,sources,extra
```

The JSON template uses an `items` array with the same field names. Field names
are not translated. `title` is required. `status` must be one of the internal
values `wish`, `watching`, `watched`, `like`, `dislike`, or `ignore`.
`rating` must be `1` to `5`. `tags`, `creators`, and `collections` are created
or linked using the current local import logic. `sources` accepts a JSON array
of `{title, url}` objects in JSON or a JSON-encoded CSV cell; semicolon-separated
URLs are also accepted in CSV.

CSV preview includes a field mapping table. If a source CSV has custom column
names, choose which source column maps to `title`, `summary`, `status`,
`rating`, `note`, `tags`, `creators`, `collections`, `sources`, or `extra`; columns can
also be ignored. The mapping is used only for the current import and is not
saved.

Preview does not write to the database. It shows total rows, importable rows,
error rows, tags / creators / collections that would be created, collection
links that would be created, the first five recognized rows, and error rows
with row number, reason, and brief source content. If some rows are invalid,
confirmation imports only valid rows and reports the skipped rows. If every row
is invalid, confirmation is disabled.

General item import only accepts uploaded local files. The separate source
import saves URL strings supplied by the user but never requests those URLs.
Neither flow uses crawlers, adapters, cloud sync, or remote fetchers.

## Backup And Export

Open `/backup` after logging in.

Available local-only actions:

- Export a complete JSON backup: `GET /api/backup/export/json`
- Export a readable items CSV: `GET /api/backup/export/csv`
- Preview a JSON backup without writing data: `POST /api/backup/preview/json`
- Restore a JSON backup exported by NSFWTrack: upload the file on `/backup`, or
  use `POST /api/backup/restore/json`

JSON backups include `items`, `tags`, `creators`, `collections`, `item_tags`,
`item_creators`, `item_collections`, `user_item_states`, `saved_views`,
`item_activity`, `app_settings`, and optional `item_sources`. Restore uses an append / merge strategy;
it is not an overwrite restore and does not clear the current database.
Collection restore merges by collection name, saved views merge by name,
recent activity rows merge only for existing local items, and supported local
settings and normalized source URLs are validated before restore. Old backups
without `item_sources` remain compatible.

Backup restore only accepts uploaded local JSON files exported by NSFWTrack. It
never restores from a URL, cloud sync, or an external data source. Uploaded JSON
backup files are limited to 5 MB by default.

CSV and JSON import files are also limited to 5 MB by default. Oversized files
are rejected before parsing or database writes.

Configure the upload limit with:

```bash
export MAX_BACKUP_UPLOAD_MB=5
export MAX_IMPORT_UPLOAD_MB=5
```

## Language

The default UI language is Chinese unless changed in local settings.

Use the language switch in the top bar to change between `中文` and `English`.
The preference is saved in the session, so refreshing the page keeps the chosen
language. A session language choice takes priority over the local default
language stored in `/settings`.

Direct routes are also available:

```text
/set-language?lang=zh
/set-language?lang=en
```

## Tests And CI

```bash
pip install -r requirements-dev.txt
python -m pip check
python -m pytest
```

GitHub Actions runs two jobs:

1. `test` — Python 3.12, install `requirements-dev.txt`, `python -m pip check`,
   then `python -m pytest`.
2. `docker-smoke` — build the production image with temporary CI credentials
   and an isolated data directory, wait for the container to become `healthy`,
   then verify `/login` HTTP 200 and baseline security response headers, dump
   container logs on failure, and always clean up containers and temporary files.

The production image health check uses Python's standard library against the
existing `/login` route. After `docker compose up -d`, `docker compose ps`
shows `healthy` when the application is ready; no curl package is required.

Phase 2-L1 installs `httpx2` for the Starlette TestClient path used by
`fastapi.testclient`. Phase 2-L2 pins the verified direct runtime and test
dependency versions used by development, CI, and Docker. Full local and CI
pytest runs should no longer emit the previous `httpx` deprecation warning.
A complete transitive lockfile is still not generated.

Phase 2-L3 adds a minimal browser security-header baseline to every HTTP
response: `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
and a restricted `Permissions-Policy`. HSTS and aggressive CSP are not
enabled, so existing local HTTP, forms, and inline scripts remain intact.
`X-Request-ID` and 405 `Allow` behavior are unchanged.

## Known Limitations

- Only one local user is supported.
- The app is intended for local network / LAN deployment.
- Direct public internet exposure is not recommended.
- Backup restore is append / merge based, not an overwrite restore.
- There are no external content sources, crawlers, recommendation systems, or
  AI assistants.
