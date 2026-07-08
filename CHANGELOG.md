# Changelog / 变更记录

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
- There are no external content sources, crawlers, recommendation systems, or AI assistants.
- The current FastAPI / Starlette TestClient warning does not affect
  functionality; revisit it after the dependency path stabilizes.
