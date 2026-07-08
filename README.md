# NSFWTrack

NSFWTrack is a local single-user content record manager / collection tracker.

Current status: `v0.3.0 / Phase 2-B local UI and stats enhancements`.

NSFWTrack remains intentionally local-only. It is designed for manual records,
local SQLite persistence, LAN deployment, and simple personal collection
management.

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

`v0.2.0` is still a local single-user release. It does not include external
content sources, crawlers, adapters, remote image fetching, third-party
cookie/token management, automatic sync, multi-source search, random
exploration, recommendation systems, AI assistants, URL import, cloud backup,
scheduled backup, overwrite restore, complex permissions, or multi-user
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
For development and CI, use `requirements-dev.txt` so `pytest` and the
TestClient dependency are installed.

## Configuration

Create a local `.env` from `.env.example` for Docker Compose, or export the same
variables before running `uvicorn` locally.

- `APP_PASSWORD`: the single local login password. Use a strong value on any
  LAN.
- `SECRET_KEY`: signs the session cookie. Use a long random value and rotate it
  if it leaks.
- `DATABASE_URL`: defaults to the SQLite database under `data/nsfwtrack.db`.
- `MAX_BACKUP_UPLOAD_MB`: maximum uploaded JSON backup size. The default is `5`.

Do not commit `.env`. It is intentionally ignored by git.

## Docker Compose

```bash
cp .env.example .env
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
title,summary,status,rating,note,tags,creators,extra
```

The JSON template uses an `items` array with the same field names. Field names
are not translated. `title` is required. `status` must be one of the internal
values `wish`, `watching`, `watched`, `like`, `dislike`, or `ignore`.
`rating` must be `1` to `5`. `tags` and `creators` are created or linked using
the current local import logic.

CSV preview includes a field mapping table. If a source CSV has custom column
names, choose which source column maps to `title`, `summary`, `status`,
`rating`, `note`, `tags`, `creators`, or `extra`; columns can also be ignored.
The mapping is used only for the current import and is not saved.

Preview does not write to the database. It shows total rows, importable rows,
error rows, tags and creators that would be created, the first five recognized
rows, and error rows with row number, reason, and brief source content. If some
rows are invalid, confirmation imports only valid rows and reports the skipped
rows. If every row is invalid, confirmation is disabled.

Import only accepts uploaded local files. NSFWTrack does not import from URLs,
external data sources, crawlers, adapters, cloud sync, or remote fetchers.

## Backup And Export

Open `/backup` after logging in.

Available local-only actions:

- Export a complete JSON backup: `GET /api/backup/export/json`
- Export a readable items CSV: `GET /api/backup/export/csv`
- Preview a JSON backup without writing data: `POST /api/backup/preview/json`
- Restore a JSON backup exported by NSFWTrack: upload the file on `/backup`, or
  use `POST /api/backup/restore/json`

JSON backups include `items`, `tags`, `creators`, `item_tags`,
`item_creators`, and `user_item_states`. Restore uses an append / merge strategy;
it is not an overwrite restore and does not clear the current database.

Backup restore only accepts uploaded local JSON files exported by NSFWTrack. It
never restores from a URL, cloud sync, or an external data source. Uploaded JSON
backup files are limited to 5 MB by default.

Configure the upload limit with:

```bash
export MAX_BACKUP_UPLOAD_MB=5
```

## Language

The default UI language is Chinese.

Use the language switch in the top bar to change between `中文` and `English`.
The preference is saved in the session, so refreshing the page keeps the chosen
language.

Direct routes are also available:

```text
/set-language?lang=zh
/set-language?lang=en
```

## Tests And CI

```bash
pip install -r requirements-dev.txt
python -m pytest
```

GitHub Actions runs on Python 3.12, installs `requirements-dev.txt`, and runs
`python -m pytest`.

Current local test runs may show a FastAPI / Starlette TestClient deprecation
warning from `fastapi.testclient` about `httpx` and `httpx2`. The warning does
not affect current NSFWTrack functionality. It is intentionally not hidden or
worked around with a broad test rewrite; revisit it after the FastAPI /
Starlette TestClient dependency path stabilizes.

## Known Limitations

- Only one local user is supported.
- The app is intended for local network / LAN deployment.
- Direct public internet exposure is not recommended.
- Backup restore is append / merge based, not an overwrite restore.
- There are no external content sources, crawlers, recommendation systems, or
  AI assistants.
- The current TestClient warning does not affect functionality and can be
  revisited after dependencies stabilize.
