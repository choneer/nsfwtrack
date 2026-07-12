# Changelog / 变更记录

## Unreleased

### Fixed

- Source import now treats multiple existing items with the same case-folded
  title as an explicit conflict in preview and apply instead of silently
  attaching the source to an arbitrary item.

### Added

- Added the authenticated Phase 3-A2 `/media-library` for safe local scanning,
  multi-image uploads, reference visibility, and item-cover / creator-avatar
  assignment using the existing media path fields and data mount.
- Added 20-file batch and 10 MiB per-file limits, extension/MIME/structure
  validation, SHA-256 content deduplication, and safe missing/corrupt-image
  fallback without adding a dependency or database object.

- Added Phase 3-A1 `item_sources` with one-to-many item sources, original and
  globally unique normalized HTTP/HTTPS URLs, optional titles, timestamps, and
  item-delete cascading.
- Added authenticated item-detail source listing, single-source add, confirmed
  source delete, and `/sources/import` for one-URL-per-line,
  `title<TAB>URL`, and user-uploaded local browser bookmarks HTML.
- Added read-only source import previews with new, duplicate, invalid,
  conflict, and new-item counts. Confirmed writes revalidate and commit new
  items/sources in one transaction with full rollback on failure.
- Added the real explicit Schema 1 → 2 `create_item_sources` migration with
  read-only preview, source/target checks, backup confirmation, and version
  registration through the existing migration framework.

### Changed

- Item covers and creator avatars can now be set, replaced, or cleared from the
  local media library. Clearing an association never deletes its media file.

- JSON backup export, validation, preview, merge restore, CSV item export, and
  CSV/JSON item import now include sources. `item_sources` remains optional in
  old backup/import payloads for backward compatibility.
- RULE now explicitly allows saving user-provided URLs and parsing local
  bookmark HTML or plain-text URL lists while retaining the external-network
  prohibition.

### Security

- Media scanning and serving reject symlinks, path escape, unsupported and
  non-regular files. Only validated AVIF, GIF, JPEG, PNG, and WebP uploads are
  accepted; SVG, HTML, disguised files, remote fetching, recognition,
  recommendations, and AI remain out of scope.

- Source URL normalization accepts only credential-free HTTP/HTTPS URLs,
  canonicalizes scheme/IDNA host/default ports/percent escapes/root paths,
  removes fragments, and enforces database uniqueness on the normalized value.
- Source and bookmark import performs no external HTTP request and fetches no
  remote title, metadata, image, or page. Crawlers, site adapters, automatic
  synchronization, recommendations, and AI remain out of scope.

## [1.0.4] - 2026-07-12

### Security

- Phase 2-L8 runs the production application and image health check as the
  fixed non-root `nsfwtrack` UID/GID `10001:10001`. CI prepares the isolated
  bind mount for that identity and verifies container identity, the L7 runtime
  restrictions, writable boundaries, healthy HTTP/security-header behavior,
  and Schema 1 SQLite persistence across container recreation.
- Documented first-install ownership and the stopped, verified-backup migration
  from v1.0.3 root-owned data without world-writable permissions, a root entry
  point, sudo/gosu, or startup-time automatic ownership changes.

## [1.0.3] - 2026-07-12

### Security

- Phase 2-L7 runs production Compose and CI Docker smoke with a read-only root
  filesystem, all Linux capabilities dropped, `no-new-privileges`, and a
  dedicated `/tmp` tmpfs. `/app/data` remains the persistent writable mount;
  CI verifies both writable paths and rejects writes to other image paths.

## [1.0.2] - 2026-07-12

### Added

- Added a production-image `HEALTHCHECK` that uses only Python's standard
  library to request the existing `/login` route; no curl, package, dependency,
  or application endpoint was added.
- Added an independent GitHub Actions Docker production smoke job that builds
  the image with temporary CI credentials and an isolated data directory,
  waits for `/login` HTTP 200, checks baseline security response headers, dumps
  container logs on failure, and always cleans up containers and temporary data.
- Added CI concurrency grouped by workflow and ref with `cancel-in-progress`,
  so an older run for the same branch or pull-request ref is cancelled.
- Added a minimal `SecurityHeadersMiddleware` that applies consistent browser
  hardening headers to successful HTML, redirects, JSON, error, and local
  media responses without enabling HSTS or an aggressive CSP.
- Added focused security-header regression coverage for login, API JSON,
  redirects, 404 / 422 / 405, and authenticated media responses while
  preserving `X-Request-ID` and 405 `Allow`.

### Fixed

- Resolved the Starlette TestClient deprecation warning by installing the
  supported `httpx2` test client dependency instead of filtering warnings.
  Full pytest now runs without the `httpx` / `httpx2` deprecation message.

### Changed

- Clarified post-`v1.0.1` project status in planning docs: stable release is
  `v1.0.1`, code development and WSL acceptance are complete, and N100 /
  target-host deployment has not started and waits for explicit user
  authorization. K3 is no longer listed as an active development task.
- Development / CI test dependencies now declare `httpx2==2.5.0` instead of
  unpinned `httpx`.
- Phase 2-L2 pins direct runtime and development dependency versions that
  were already verified on Python 3.12. This is a direct-dependency baseline
  only; a full transitive lockfile is still not generated.
- CI now runs `pip check` after installing `requirements-dev.txt` and before
  pytest.
- Phase 2-L4 updated the checkout and Python setup actions, and uses fixed
  job-level smoke paths so failure and `always` cleanup target the same Compose
  project and temporary directory without changing test or smoke behavior.
- Phase 2-L6 makes the Docker smoke job wait for the image health status to
  become `healthy` before running the existing `/login` and security-header
  assertions; failure logs and unconditional cleanup remain unchanged.

### Security

- Phase 2-L5 explicitly limits the GitHub Actions token to read-only repository
  contents; the workflow requests no write permission or additional secret.

## [1.0.1] - 2026-07-11

### Added

- Added `COMPLETION_AUDIT.md` with the Phase 2-K1 implementation, documentation,
  test-gap, dead-entry, and F4 safety-prompt audit.
- Added an authenticated app-owned `/media/...` contract backed by
  `data/media`, with one shared validator for item covers, creator avatars,
  page forms, APIs, backup validation, preview, restore, and template rendering.
- Added focused configuration, local-media, confirmation-boundary, and F4
  safety-prompt regression coverage.
- Added a single first-install, v0.9/v1.0 upgrade, backup, and rollback checklist.

### Changed

- Reduced the pre-use roadmap to Phase 2-K2 boundary closure and Phase 2-K3
  target deployment acceptance. Historical completed phases remain archived.
- Corrected current planning language to describe the existing Jinja2 and
  lightweight vanilla JavaScript frontend rather than claiming active HTMX
  behavior.
- All current-page bulk writes, state clearing, and item relationship detach
  actions now require browser and server confirmation. Strict mode requires
  exact `CONFIRM` before these writes.
- Updated the FastAPI application version metadata from `1.0.0` to `1.0.1`.

### Security

- Closed the K1 local media-path, bulk / clear / detach confirmation, and
  shipped placeholder-secret findings without adding external media, upload,
  proxy, URL import, dependencies, schema changes, or migrations.
- Startup now rejects the exact `APP_PASSWORD` and `SECRET_KEY` placeholders
  shipped in `.env.example` without echoing either credential.
- Confirmed the F4 data-health warning flow already provides backup guidance,
  impact and deletion scope, manual single-fix limits, server confirmation,
  strict confirmation, and rollback coverage; focused bilingual and policy
  tests now close the remaining acceptance gap.
- Kept `CURRENT_SCHEMA_VERSION = 1`, the production migration registry empty,
  and all previously published tags unchanged.

## [1.0.0] - 2026-07-11

### Added

- Added Phase 2-I1 reproducible read-only SQLite performance auditing with
  disposable 100 / 1,000 / 10,000 item fixtures, SQL query counting,
  fingerprint repetition counts, elapsed-time observations, and
  `EXPLAIN QUERY PLAN` summaries.
- Added coverage for item list filtering / sorting / pagination, workbench,
  stats, tags, creators, collections, saved views, activity, duplicate items,
  metadata cleanup, data health, backup preview / validation, and JSON import
  dry-run.
- Added `PERFORMANCE.md` with the measured baseline, confirmed N+1 and query
  amplification findings, paths without a confirmed major issue, I2 priority
  order, and a separate list of index suggestions that require a real schema
  migration.
- Added performance-audit tests for read-only enforcement, connection-state
  cleanup, required operation coverage, stable paginated query counts, and the
  confirmed collection-detail N+1.
- Added Phase 2-I2 shared pagination for tags, creators, collections, duplicate
  comparison pairs, cleanup comparison pairs, collection members, and the
  searchable collection available-item selector.
- Added query-regression tests for pagination reachability, collection member
  preservation, bounded collection detail loading, complete data-health counts,
  single-request settings reuse, and I2 query-count ceilings.
- Added Phase 2-I3 unified bilingual HTML error pages and JSON error envelopes
  for 400, 403, 404, 405, 409, 422, and 500 responses.
- Added a request-context middleware that validates or generates a bounded
  `request_id`, returns it as `X-Request-ID`, and emits one sanitized local log
  line with method, route path, status, duration, and exception type when
  applicable.
- Added error-handling tests for HTML / JSON negotiation, `Allow` preservation,
  validation compatibility, request-id validation, safe 500 responses, log
  redaction, expected-error severity, and transaction rollback.
- Added static-review regression coverage proving `ghp_` / `github_pat_`
  request IDs are replaced, unmatched credential-shaped paths are never
  logged, and matched routes continue using route templates.
- Added Phase 2-I4 release-freeze coverage for authentication dependencies,
  same-origin enforcement, session renewal and invalidation, cookie flags,
  local redirects, HTML escaping, malformed login JSON, and bounded imports.
- Added configurable `MAX_IMPORT_UPLOAD_MB` and `SESSION_COOKIE_SECURE`
  deployment settings with safe local defaults.

### Changed

- Replaced recursive model-default relationship loading on item, metadata,
  activity, duplicate, and cleanup list paths with operation-specific
  `selectinload` / `noload` strategies. Current item-page relationships still
  load for rendering, while unrelated reverse graphs no longer load.
- Metadata cleanup candidates now select id, name, and relation count; compare
  and merge continue loading concrete objects only when explicitly opened.
- Collection detail now uses separate 20-row pages for current members and
  searchable available items. The confirmed per-member collection N+1 is
  removed without changing collection membership mutations.
- Metadata pages use 50-row pages. Duplicate and cleanup pages paginate 20
  comparison pairs while keeping every candidate reachable.
- Shared page context reuses one validated settings object, and workbench saved
  views apply `LIMIT 4` in SQL instead of slicing an unbounded result.
- Consolidated stats aggregates and seven-day buckets from 28 to 11 measured
  queries while preserving the existing response structure.
- Combined data-health orphan checks and limited rendered details to 200 while
  preserving complete totals and manual-fix issue counts.
- Updated the 100 / 1,000 / 10,000 performance matrix with I1-to-I2 results.
- API errors now retain the compatible `detail` field and status while also
  returning `error`, `message`, and `request_id`. Validation errors retain
  type, location, and message without echoing submitted input.
- Page errors use one responsive template with the original status code and a
  generic localized message. Redirects and successful responses also receive
  `X-Request-ID`; 405 responses retain `Allow`.
- Replaced Uvicorn's raw request-line access log with the application request
  log so query strings, headers, cookies, form values, and upload content are
  not recorded.
- Tightened accepted external request IDs to canonical UUID or 32-character
  UUID hex values. Every other value is replaced with server-generated UUID
  hex before it can reach a response or log.
- Unmatched routes now use the fixed log path `/[unmatched]`; only matched
  routes may contribute their application-owned route template to logs.
- Login now clears pre-authentication session state except the selected
  language. Authenticated sessions carry an application generation, so logout
  and application restart invalidate previously signed authenticated cookies.
- Dangerous page operations now require a server-validated confirmation marker
  in standard and strict modes. Strict mode continues to require exact
  `CONFIRM`; existing transaction and rollback boundaries are unchanged.
- Local redirect validation now rejects external, protocol-relative,
  backslash, encoded-backslash, and control-character targets. Malformed or
  non-object login JSON returns a safe 400 response.
- CSV and JSON import uploads now stop after the configured byte limit and are
  rejected before parsing or writing.
- Item detail GET is now read-only. Its existing local view activity is
  recorded by a login-protected, same-origin POST after the page loads.
- Corrected the internal FastAPI application metadata from the historical
  `0.1.0` value through the current published `1.0.0` release.
- Reran the isolated 100 / 1,000 / 10,000 matrix. Query counts remained 11 for
  items and filtered items, 9 for collection detail, 7 for duplicates, 4 for
  cleanup, 3 for metadata lists, and 11 for stats, with no N+1 regression.

### Security

- Performance fixtures are created only in disposable SQLite databases and
  removed after each run. The audit connection uses SQLite `query_only`,
  blocks write statements before execution, accepts no arbitrary SQL or table
  name, and does not access the default local data volume.
- Added no index, table, field, dependency, cache, background task, production
  migration, schema-version change, business-logic optimization, tag, or
  GitHub Release.
- Phase 2-I2 adds no index, table, field, dependency, production migration,
  schema-version change, cache, external service, tag, or GitHub Release. All
  performance acceptance data remains isolated and disposable.
- Unhandled exceptions now return only a generic message and request ID. The
  application logs the exception type without traceback text or exception
  values, and expected 4xx responses remain informational rather than system
  failures.
- Phase 2-I3 preserves existing login, POST, browser confirmation, strict
  `CONFIRM`, transaction, and rollback boundaries. It adds no external logging,
  telemetry, dependency, schema change, tag, or GitHub Release.
- Credential-shaped request IDs and raw unmatched paths are no longer trusted
  log fields. Query strings, headers, bodies, exception values, and raw
  unmatched paths remain excluded from the application request log.
- Unsafe requests that provide `Origin` or `Referer` must match the local
  request origin. Headerless local API clients remain compatible, with the
  `HttpOnly`, `SameSite=Lax` session cookie providing the browser boundary;
  HTTPS deployments can explicitly enable the `Secure` cookie flag.
- Phase 2-I4 verified protected route coverage, XSS escaping, upload and error
  boundaries, rollback behavior, and five isolated database compatibility
  scenarios. It adds no product feature, dependency, index, table, field,
  schema-version change, production migration, tag, or GitHub Release.

## v0.9.0 - 2026-07-10

### Added

- Added Phase 2-H2 explicit SQLite migration framework with code-only migration
  steps, strict registry validation, continuous path resolution, source-version
  pre-checks, target-version post-checks, and per-step version records.
- Added login-protected `GET /schema-upgrade`, read-only
  `POST /schema-upgrade/preview`, and explicit
  `POST /schema-upgrade/apply` flows. Apply requires browser confirmation,
  existing server-side dangerous-operation confirmation, explicit backup
  acknowledgement, and exact `CONFIRM` text in strict mode.
- Added protected upgrade dry-run reports with current / target versions,
  ordered migration steps, expected changes, warnings, errors, first-step
  pre-check results, and deferred later-step checks that are rerun during apply.
- Added test-only migration registries covering duplicate, gap, jump, reverse,
  and cyclic path rejection; continuous path resolution; read-only data and DDL
  enforcement; authentication and confirmation; missing paths; downgrades;
  two-step rollback; post-check rollback; and version-record atomicity.
- Added Phase 2-H1 internal database schema version tracking with a local
  `schema_migrations` table containing unique `version`, descriptive `name`,
  and `applied_at` fields. The current application schema baseline is version
  `1`.
- Added startup schema preflight handling for empty databases, compatible
  legacy databases without a version record, matching versions, lower database
  versions, higher database versions, missing required tables / columns, and
  unreadable version records.
- Added a login-protected, read-only database schema status area on `/settings`
  showing the application version, database version, compatibility status,
  latest registration time, and a pre-upgrade JSON backup recommendation.
- Added tests for new and legacy database registration, structure validation,
  initialization rollback safety, matching / lower / higher versions, real
  application lifespan refusal, status-page access and read-only behavior,
  backup isolation, version uniqueness, and Chinese / English copy.

### Changed

- Lower-version startup now reads and reports the recorded database version
  without requiring the old database to match the latest application structure.
  The migration step pre-checks own source-version requirements, and target
  structure is checked only after each step applies.
- Migration apply rereads the database version and resolves the code registry
  inside one transaction. All migration steps, post-checks, and version inserts
  commit together or roll back together.
- Replaced unconditional startup `create_all` with a schema-aware initializer.
  Empty databases create the current schema and baseline in one transaction;
  unversioned legacy databases must already contain every required business
  table and column before the internal baseline is registered.
- Database versions lower than the application are reported as requiring an
  upgrade without changing the recorded version or running migrations.
  Versions higher than the application refuse startup with a safe backup hint.

### Security

- Enforced dry-run read-only behavior with SQLite `query_only`, an authorizer
  that denies data / schema writes, and unconditional rollback. Preview never
  calls apply or writes `schema_migrations`.
- Kept the production migration registry empty and
  `CURRENT_SCHEMA_VERSION = 1`: no test-only production migration, schema bump,
  existing business-table change, dependency, automatic migration, downgrade,
  user SQL, table-name input, or target-version input was added.
- Kept `schema_migrations` outside JSON backup export, preview, validation, and
  restore data. Uploaded backup rows using that table name are ignored and
  cannot replace the local schema version.
- Added no page, URL parameter, form field, downgrade control, bypass control,
  automatic migration, automatic repair, Alembic integration, dependency, or
  change to an existing business table or field.

## v0.8.0 - 2026-07-10

### Added

- Added Phase 2-G6 dangerous-operation preferences by reusing the existing
  `app_settings` table, with allowlisted keys and values:
  `danger_confirmation_mode` (`standard` / `strict`),
  `backup_reminder_mode` (`always` / `dangerous_only`), and
  `danger_result_detail` (`summary` / `detailed`).
- Added a centralized dangerous-operation policy and server-side strict-mode
  validation. Strict mode requires the exact text `CONFIRM` in addition to
  the existing login, HTTP method, browser confirmation, service confirmation,
  and rollback behavior.
- Added unified bilingual safety notices that identify the operation object,
  consequence, deletion scope, recoverability, JSON backup recommendation,
  and current confirmation mode.
- Applied strict confirmation to item and current-page bulk deletion, tag /
  creator / collection deletion, item and metadata merge, recent activity
  clearing, JSON backup restore, data health manual fixes, and settings reset.
- Added summary / detailed result presentation without changing mutation
  logic, data scope, or transaction behavior.
- Added tests for setting allowlists, rejected disabling values, standard and
  strict confirmation, every covered dangerous route, GET safety, invalid and
  unreadable setting fallback, backup reminder behavior, result display
  independence, backup compatibility, and i18n symmetry.
- Added Phase 2-G1 basic local settings center at `/settings`.
- Added a local SQLite `app_settings` table for `default_language`,
  `default_page_size`, `default_sort`, `default_sort_dir`, and `default_home`.
- Added whitelist validation for setting keys and values so unknown settings,
  external URLs, and script-like arbitrary values are rejected without a 500.
- Added login-protected settings save and reset flows:
  `POST /settings` and `POST /settings/reset`, with reset requiring explicit
  `confirm=1`.
- Added setting application for item-list default page size, item-list default
  sort field / direction, default language fallback when no explicit session
  language exists, and dashboard default-home entry highlighting.
- Added JSON backup export / preview / restore compatibility for
  `app_settings`, while keeping older backups without `app_settings`
  compatible as an empty optional table.
- Added backup validation for `app_settings` key/value validity.
- Added Chinese / English settings UI and flash text.
- Added tests for settings login protection, valid save, invalid key/value
  rejection, default page size, default sorting, explicit URL override,
  language switching precedence, reset confirmation, default-home highlighting,
  `app_settings` backup compatibility, database table creation, and i18n
  coverage.

### Changed

- Centralized browser confirmation handling in the base template while keeping
  all dangerous mutations login-protected and write-only. Settings cannot turn
  confirmation, safety notices, or rollback off, and invalid confirmation
  settings safely fall back to `standard`.
- Extended existing JSON backup export, validation, preview, and restore for
  the three G6 settings. Older backups without those rows continue to use safe
  defaults.
- Kept Phase 2-G1 scoped to local single-user preferences only: no multi-user
  settings, cloud sync, external accounts, plugin system, AI recommendation,
  external content source, existing-table field change, or dependency change.

## v0.7.0 - 2026-07-09

### Added

- Added Phase 2-F3 low-risk manual data health fixes on `/data-health`,
  limited to relation tables, `item_activity`, and `saved_views.query_string`.
- Added a whitelisted data health fix service for orphaned `item_tags`,
  `item_creators`, and `item_collections` rows; duplicate relation rows in
  those same tables; orphaned `item_activity`; negative `view_count` /
  `edit_count`; and risky or unknown saved views query parameters.
- Added login-protected `POST /data-health/fix` with server-side confirmation
  checks, one-fix-type-at-a-time dispatch, rollback on failure, and flash
  summaries for deleted, corrected, and skipped rows.
- Added `/data-health` manual fix controls that appear only when the matching
  issue exists, include browser confirmation, link to JSON backup, and state
  that items, tags, creators, and collections are not deleted.
- Added tests for unauthenticated fix rejection, GET no-fix behavior, invalid
  `fix_type`, rejected `fix_all`, missing confirmation, orphan relation
  cleanup, duplicate relation cleanup for legacy schemas, orphan activity
  cleanup, negative activity count correction, saved views query cleanup, core
  entity preservation, rollback, and i18n coverage.
- Added Phase 2-F2 JSON backup file validation with a structured
  `error` / `warning` / `info` report for schema, tables, rows, required
  fields, unknown fields, duplicate ids, relation integrity, duplicate
  relations, saved views, and item activity.
- Added backup restore dry-run reporting on the `/backup` page, including
  table counts, relation counts, expected skipped rows, compatibility notices
  for older backups without newer optional tables, and a pre-write JSON backup
  recommendation.
- Added successful backup preview API reports at `/api/backup/preview/json`
  while preserving existing 400 responses for invalid backup files.
- Added import dry-run report details to CSV / JSON preview pages, covering
  importable rows, skipped rows, row errors, unknown fields, invalid
  `rating` / `status`, abnormal `tags` / `creators` fields, duplicate title
  candidates, existing-title warnings, and read-only backup prompts.
- Added tests for backup validation login protection, invalid / empty JSON,
  old backup compatibility, unknown fields, missing required fields, invalid
  values, orphaned relations, duplicate relations, saved views issues,
  item activity issues, dry-run no-write behavior, dry-run no-delete behavior,
  import dry-run reports, i18n coverage, and existing backup / import
  regressions.
- Added Phase 2-F1 local data health checking with a login-protected
  `/data-health` page.
- Added a read-only data health service that reports item data issues,
  relation integrity issues, duplicate relation issues, saved views parameter
  issues, and item activity issues without modifying SQLite data.
- Added item checks for empty titles, invalid `rating` values, invalid
  `status` values, missing / invalid item timestamps, updated-before-created
  timestamps, and invalid `extra` JSON.
- Added relation checks for orphaned `item_tags`, `item_creators`, and
  `item_collections` rows that point to missing items, tags, creators, or
  collections.
- Added duplicate relation checks for repeated item-tag, item-creator, and
  item-collection links, including legacy-schema test coverage where unique
  constraints may be absent.
- Added saved views checks for empty names, empty or malformed `query_string`
  values, unknown query parameters, blocked `page` / `next` / `redirect`
  parameters, and external URL values.
- Added `item_activity` checks for missing item references, negative
  `view_count` / `edit_count`, and invalid `last_viewed_at` /
  `last_edited_at` values.
- Added data health navigation from the authenticated top nav and dashboard
  workbench.
- Added Chinese / English data health UI text and tests for authentication,
  healthy state rendering, issue reporting, read-only behavior, no business
  data deletion, and language coverage.

### Changed

- Kept Phase 2-F3 scoped to manual low-risk maintenance: no items, tags,
  creators, or collections are deleted; no automatic fix-all, automatic merge,
  AI judgment, external content source, URL import, crawler, cloud sync,
  multi-user system, database schema change, dependency change, tag, or GitHub
  Release is added.
- Kept Phase 2-F2 strictly read-only: validation and dry-run reports do not
  restore backups, import data, create tags / creators / collections, modify
  saved views / activity, write SQLite data, delete business data, auto-fix,
  auto-import, auto-restore, auto-merge, request external network resources,
  add dependencies, or change database schema.
- Kept Phase 2-F1 strictly read-only: no auto-fix, one-click fix, automatic
  deletion, automatic merge, AI judgment, external information lookup, external
  content source, URL import, crawler, adapter, cloud sync, multi-user system,
  database schema change, new table, new field, or new dependency.

## v0.6.0 - 2026-07-09

### Added

- Added Phase 2-E3 dashboard / workbench quick action entry points for new
  items, the item list, saved views, recent activity, stats, collections,
  duplicate item detection, metadata cleanup, import, and backup.
- Added a dashboard saved views panel that shows a small set of local saved
  views and links to apply them without saving, updating, deleting, or
  modifying any data from the dashboard.
- Added an item-list quick action section for new items, save-current-view /
  saved views, recent activity, duplicate detection, metadata cleanup, import,
  and backup while preserving the existing filter, sort, pagination, saved
  views, and bulk edit areas.
- Added Chinese / English workbench and quick action UI text.
- Added tests for dashboard login protection, dashboard quick action rendering,
  navigation-only quick action sections, empty saved views / activity states,
  dashboard saved view and recent activity entries, item-list quick actions,
  existing filter and saved view preservation, and English quick action labels.
- Added Phase 2-E2 local item activity tracking backed by a new local SQLite
  `item_activity` table with one activity row per item.
- Added recent view recording for login-protected item detail visits, tracking
  `last_viewed_at` and `view_count` without recording list exposure,
  non-existent items, or unauthenticated requests.
- Added recent edit recording for user-driven item changes, including item
  basics, state / rating / review updates, tag changes, creator changes,
  collection changes, and current-page bulk edits.
- Added a login-protected `/activity` page with recent views, recent edits,
  empty states, item links, local activity counts, and a clear activity action.
- Added `POST /activity/clear` to clear only `item_activity` rows with browser
  confirmation, preserving items, tags, creators, collections, and saved views.
- Added dashboard and item-list entry points for recent views and recent edits,
  plus item detail activity metadata.
- Added Chinese / English recent activity UI and flash text.
- Added JSON backup export / preview / restore support for `item_activity`
  while keeping old backups without `item_activity` compatible and skipping
  activity rows that reference missing items.
- Added tests for activity login protection, empty states, recent view counts,
  unauthenticated and missing item no-write behavior, recent edit counts,
  relation changes, collection-side changes, current-page bulk edit activity,
  ordering, POST-only clear, clear safety, i18n coverage, table creation, and
  JSON backup compatibility.
- Added Phase 2-E1 local saved views for the item list page, backed by a new
  local SQLite `saved_views` table.
- Added login-protected saved view create, update, delete, and apply flows:
  `POST /saved-views`, `POST /saved-views/{id}/update`,
  `POST /saved-views/{id}/delete`, and `GET /saved-views/{id}/apply`.
- Added an item-list saved views panel for naming the current filter view,
  applying saved views, updating a saved view to the current filters, and
  deleting saved views with browser confirmation.
- Added saved view query-string normalization that stores only existing
  item-list filter / sort / page-size parameters, removes page numbers, ignores
  unknown parameters, and uses stable parameter ordering.
- Added Chinese / English saved view UI and flash text.
- Added JSON backup export / preview / restore support for saved views while
  keeping old backups without `saved_views` compatible.
- Added tests for saved view login protection, creation, validation, duplicate
  names, parameter filtering, apply redirects, no-write apply behavior, invalid
  IDs, update, POST-only delete, deletion, page rendering, i18n coverage, table
  creation, and JSON backup compatibility.

### Changed

- Kept Phase 2-E3 limited to local UI entry-point organization, with no
  database schema change, new table, dependency, dangerous one-click shortcut,
  login bypass, POST / confirm bypass, AI recommendation, smart analysis,
  automatic classification, external content source, URL import, crawler,
  adapter, cloud sync, multi-user sharing, third-party analytics, activity
  trend chart, tag, or GitHub Release.
- Kept Phase 2-E2 limited to local item activity, with no AI recommendation,
  smart analysis, automatic classification, external content source, URL
  import, crawler, adapter, cloud sync, multi-user activity feed, third-party
  analytics, IP logging, User-Agent logging, device fingerprinting, external
  referrer logging, database field changes, or new dependency.
- Kept Phase 2-E1 limited to local saved item-list views, with no AI
  recommendation, smart classification, external content source, URL import,
  crawler, adapter, cloud sync, multi-user shared views, database field
  changes, or new dependency.

## v0.5.0 - 2026-07-09

### Added

- Added Phase 2-D2 local metadata cleanup for tags, creators, and collections
  using exact trimmed name matches and normalized name matches with Unicode
  NFKC, trimming, casefolding, and whitespace collapsing.
- Added a login-protected `/cleanup` page showing read-only duplicate metadata
  candidate groups, match type, match key, object names, and related item
  counts across tags, creators, and collections.
- Added a login-protected `/cleanup/compare` page for manually comparing a
  primary metadata object and a duplicate metadata object before merge.
- Added manual metadata merge handling that keeps the primary tag / creator /
  collection, transfers related item links without duplicating relations,
  deletes the duplicate metadata object after confirmation, and never deletes
  items.
- Added collection description conflict handling: copy duplicate description
  when primary is empty, keep primary by default when both differ, and overwrite
  only when the user explicitly chooses the duplicate description.
- Added merge result flash summaries covering metadata type, kept object,
  deleted object, transferred relations, skipped duplicate relations,
  description handling, duplicate deletion, and a prompt to recheck cleanup.
- Added navigation, tag page, creator page, and collection page entry points for
  metadata cleanup.
- Added Chinese / English metadata cleanup and merge UI text.
- Added tests for cleanup login protection, empty states, tag / creator /
  collection exact and normalized candidate detection, comparison validation,
  POST-only merge, relation transfer, duplicate relation skipping, duplicate
  metadata deletion, item preservation, collection description copy / keep /
  overwrite handling, merge summaries, and i18n labels.
- Added Phase 2-D1 local duplicate candidate detection using exact trimmed title
  matches and normalized title matches with Unicode NFKC, trimming, casefolding,
  and whitespace collapsing.
- Added a login-protected `/duplicates` page showing read-only duplicate
  candidate groups, match type, match key, item counts, state, rating, and
  tag / creator / collection counts.
- Added a login-protected duplicate comparison page for manually choosing a
  primary item and a duplicate item before merge.
- Added manual duplicate merge handling that keeps the primary item, transfers
  tag / creator / collection relations without duplicating relations, merges
  safe fields, merges non-conflicting `extra` JSON keys, keeps primary values
  for conflicts by default, and deletes the duplicate item after confirmation.
- Added merge result flash summaries covering transferred relation counts,
  summary / status / rating / review handling, `extra` merge counts, `extra`
  conflict counts, and duplicate deletion.
- Added navigation, item list, and item detail entry points for duplicate
  detection.
- Added Chinese / English duplicate detection and merge UI text.
- Added tests for duplicate login protection, empty states, exact and
  normalized candidate detection, comparison validation, POST-only merge,
  relation transfer, conflict defaults, explicit overwrite choices, bad
  `extra` JSON handling, state copying, duplicate deletion, and i18n labels.

### Changed

- Kept Phase 2-D2 limited to local SQLite metadata duplicate detection and
  manual merge, with no AI synonym detection, fuzzy matching dependency,
  automatic bulk merge, external information lookup, external content source,
  URL import, crawler, adapter, recommendation system, cloud sync, multi-user
  system, database schema change, or new dependency.
- Kept Phase 2-D1 limited to local SQLite duplicate detection and manual merge,
  with no AI dedupe, image similarity, fuzzy matching dependency, automatic
  bulk merge, external content source, URL import, crawler, adapter,
  recommendation system, cloud sync, multi-user system, database schema change,
  or new dependency.

## v0.4.0 - 2026-07-09

### Added

- Added Phase 2-C2 collection data support for JSON backup export, JSON backup
  preview, JSON restore, CSV export, CSV import, JSON import, import preview,
  and import result summaries.
- Added `collections` and `item_collections` tables to JSON backup payloads
  while keeping old backups without those tables compatible.
- Added collection restore merge logic with duplicate collection protection,
  duplicate item-collection relation protection, bad relation skipping, and
  collection-specific restore counters.
- Added `collections` to CSV export and CSV / JSON import templates, with CSV
  semicolon-separated collection names and JSON collection arrays.
- Added import preview and result counters for collections to create,
  collection links, skipped collections, and collections field errors.
- Added tests for collection backup export / preview / restore, old backup
  compatibility, bad collection relation skipping, CSV export, CSV / JSON
  collection imports, template updates, preview no-write behavior, and
  Chinese / English collection backup copy.
- Added Phase 2-C1 local collections / list management backed by local SQLite
  tables `collections` and `item_collections`.
- Added collection create, edit, delete, list, and detail pages with login
  protection, empty states, duplicate-name handling, and Chinese / English UI
  text.
- Added item-to-collection management from both collection detail pages and item
  detail pages, including duplicate relation checks and safe removal of missing
  relations.
- Added item list filtering by collection, with query-string preservation across
  keyword, tag, creator, status, sorting, and pagination flows.
- Added current-page bulk add / remove collection actions using existing
  collections only.
- Added collection overview metrics and collection ranking to the local stats
  dashboard and stats summary payload.
- Added tests for collection login protection, CRUD, delete safety, detail
  rendering, item membership management, list filtering, bulk collection
  actions, stats, i18n coverage, and new table creation.

### Changed

- Backup and import pages now document that JSON backups include collection
  data, CSV exports include `collections`, JSON restore merges local collection
  data, and old backup / import files remain compatible.
- Kept Phase 2-C2 limited to local backup / import support for collection data,
  with no external content sources, URL import, crawlers, adapters,
  recommendation system, AI assistant, cloud sync, multi-user system, new
  dependency, or database schema change.
- Item detail pages now show linked collections and allow adding or removing one
  existing collection.
- Item API responses now include linked collection metadata for local clients.
- Kept Phase 2-C1 limited to local manual collections, with no external content
  sources, URL import, crawlers, adapters, recommendation system, AI assistant,
  cloud sync, multi-user system, new dependency, or front-end build flow.

## v0.3.0 - 2026-07-08

### Added

- Added a local SQLite stats service for overview metrics, status
  distribution, rating distribution, tag ranking, creator ranking, recent
  activity, and data completeness counts.
- Added an enhanced stats dashboard with pure HTML / CSS bars, local ranking
  lists, recent created / updated activity blocks, and empty data states.
- Added Chinese / English text and tests for empty stats, overview counts,
  status and rating distributions, tag / creator ranking order, recent activity
  counts, data completeness counts, and stats page rendering.
- Added lightweight responsive structure tests for the dashboard, item list,
  item detail, import preview, backup, stats, tags, and creators pages.

### Changed

- Kept Phase 2-B2 limited to local SQLite statistics, with no external content
  sources, URL import, crawlers, adapters, recommendation system, AI analysis,
  prediction model, chart library, new dependency, database structure change,
  cloud sync, or multi-user support.
- Polished shared responsive CSS for the top navigation, main content spacing,
  cards, grids, forms, buttons, pills, flash messages, pagination, and item
  selection controls.
- Improved narrow-screen layouts for the item list filters, current-page bulk
  editing panel, item cards, detail page sections, relation forms, import page
  preview / mapping tables, item forms, backup page, stats page, tag list, and
  creator list.
- Contained long local titles, tags, creator names, JSON blocks, and table
  content with wrapping or local table scrolling so mobile pages avoid obvious
  whole-page horizontal overflow.
- Kept Phase 2-B1 limited to responsive UI and page layout polish, with no new
  business features, dependencies, database structure changes, external content
  sources, URL import, crawlers, adapters, recommendation systems, AI
  assistants, cloud sync, or multi-user support.

## v0.2.0 - 2026-07-08

### Added

- Added Phase 2-A1 local list page advanced filtering for keyword, status, one
  tag, one creator, minimum rating, and created / updated time range.
- Added list sorting by created time, updated time, title, and rating in both
  directions.
- Added page size selection for `10`, `20`, `50`, and `100` items per page with
  query-string state preservation.
- Added current filter summary, clear filters action, and empty result prompt on
  the item list page.
- Added Chinese / English UI text and tests for the new list filters, sorting,
  pagination, retained form state, invalid pagination fallback, and empty state.
- Added Phase 2-A2 current-page item selection and local bulk actions for status
  updates, adding one existing tag, removing one existing tag, setting rating,
  and deleting selected items.
- Added browser confirmation and visible dangerous-action copy for bulk delete.
- Added bulk action success / error flash messages with processed and skipped
  counts in Chinese / English.
- Added tests for bulk login protection, missing selection, invalid inputs,
  tag handling, rating updates, delete cleanup, preserved list URLs, and i18n
  labels.
- Added Phase 2-A3 detail page sections for basic information, state
  information, tags, creators, and actions.
- Added detail page status, rating, and short review editing with safe invalid
  value handling.
- Added detail page management for adding / removing one existing tag and
  attaching / detaching one existing creator.
- Added safe detail-page `next` handling so returning to the item list can keep
  search, filters, sorting, page, and page size.
- Added Chinese / English UI text and tests for detail rendering, state edits,
  tag / creator relation management, safe `next`, and i18n labels.
- Added Phase 2-A4 CSV / JSON import template downloads with local-only example
  data and login protection.
- Added import field guidance for supported CSV / JSON fields, required
  `title`, valid internal `status` values, `rating` rules, tag / creator
  handling, preview flow, and local-only boundaries.
- Added CSV field mapping during preview, including `title`, `summary`,
  `status`, `rating`, `note`, `tags`, `creators`, `extra`, and ignored columns.
- Added enhanced import previews with total rows, importable rows, error rows,
  tags and creators to create, first five recognized rows, and readable error
  rows.
- Added import result summaries with imported, skipped, created tag, created
  creator, tag link, creator link, state record, and error counts.
- Added tests for import template auth and downloads, CSV automatic and manual
  mapping, mapping failures, CSV / JSON error paths, preview no-write behavior,
  partial valid imports, result summaries, and Chinese / English copy.

### Changed

- Moved item list query normalization and SQLAlchemy query construction into a
  dedicated local service.
- Moved bulk item mutation logic into a dedicated local service.
- Moved detail page mutation logic into a dedicated local service.
- Kept the Phase 2-A1 implementation local-only with no external content
  sources, crawlers, adapters, remote image fetching, recommendation system, AI
  assistant, cloud sync, or multi-user support.
- Kept the Phase 2-A2 implementation local-only and limited to selected items on
  the current page.
- Kept the Phase 2-A3 implementation local-only and limited to lightweight
  detail page display, state edits, relation management, and safe list-return
  context.
- Reworked the import service so parsing, preview validation, field mapping,
  error rows, and result summaries share one local-only code path.
- Kept the Phase 2-A4 implementation local-only and limited to uploaded CSV /
  JSON files, with no URL import, external content sources, crawlers, adapters,
  remote image fetching, automatic sync, recommendations, AI assistants, cloud
  sync, or multi-user support.

## v0.1.0 - 2026-07-08

### Added

- Completed the Phase 1 local single-user MVP.
- Added session-based login protection with `APP_PASSWORD` and `SECRET_KEY`.
- Added Chinese / English UI switching with session persistence.
- Added local item CRUD, tag management, creator management, item state
  tracking, search, and simple stats.
- Added CSV / JSON import with preview and confirmation flow.
- Added JSON backup export, readable CSV export, JSON backup preview, and
  append / merge JSON restore.
- Added configurable backup upload size limit through `MAX_BACKUP_UPLOAD_MB`.
- Added Dockerfile, Docker Compose deployment, SQLite persistence under
  `./data`, and N100 / LAN deployment documentation.
- Added GitHub Actions CI and basic automated test coverage.

### Changed

- Clarified Phase 1 local-only boundaries in README, TASKS, and REVIEW.
- Unified page feedback for success, error, and info messages.
- Improved import, backup, restore, and form operation user feedback.

### Fixed

- Added clear page-level feedback for login failure, import preview failure,
  and backup preview failure.
- Confirmed invalid backup restore paths do not damage existing database contents.

### Security

- Kept passwords and session signing secrets in environment variables.
- Kept `.env` ignored by git and documented that it must not be committed.
- Kept all main pages and APIs behind login protection.
- Documented that direct public internet exposure is not recommended.

### Known limitations

- Only one local user is supported.
- The app is intended for LAN / local deployment.
- Direct public internet exposure is not recommended.
- Backup restore is append / merge based, not an overwrite restore.
- There are no external content sources, crawlers, recommendation systems, or
  AI assistants.
- The current FastAPI / Starlette TestClient warning does not affect
  functionality; revisit it after the dependency path stabilizes.
