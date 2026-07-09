# Changelog / 变更记录

## Unreleased

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
