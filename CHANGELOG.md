# Changelog / 变更记录

## Unreleased

No unreleased changes.

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
