# NSFWTrack

NSFWTrack is a local single-user content record manager / collection tracker.

Current status: `v0.1.0 / Phase 1 MVP`.

Phase 1 is intentionally local-only. It is designed for manual records, local
SQLite persistence, LAN deployment, and simple personal collection management.

## Unreleased: Phase 2 List Enhancements

### Phase 2-A1 Advanced List Filters

The current `main` branch includes local list page improvements for finding and
reviewing existing records:

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

The current `main` branch also includes local bulk management for items on the
current list page:

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

The current `main` branch also improves the local item detail page:

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

## Phase 1 Boundaries

`v0.1.0` is still a local MVP. It does not include external content sources,
crawlers, adapters, remote image fetching, third-party cookie/token management,
automatic sync, multi-source search, random exploration, recommendation systems,
AI assistants, URL backup import, cloud backup, scheduled backup, overwrite
restore, complex permissions, or multi-user support.

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

Phase 1 is a local single-user MVP. Do not expose it directly to the public
internet. If you put it behind a reverse proxy, frpc, VPN, or any other remote
access layer, confirm `APP_PASSWORD` is strong first and keep the remote access
layer protected as well.

NSFWTrack does not need third-party cookies, tokens, crawlers, or external
content source credentials in Phase 1.

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
