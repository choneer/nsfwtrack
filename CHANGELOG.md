# Changelog / 变更记录

## Unreleased

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
