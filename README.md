# NSFWTrack

Phase 1 local single-user media record manager.

NSFWTrack is intentionally local-only in Phase 1. It supports manual records,
tags, creators, states, local search, simple stats, CSV/JSON import, login
protection, local JSON/CSV export, JSON backup restore, Docker Compose
deployment, and Chinese / English UI switching.

Phase 1 still forbids external content sources, crawlers, adapters, remote image
fetching, third-party cookie/token management, automatic sync, multi-source
search, random exploration, recommendation systems, and AI assistants.

## Local Run

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export APP_PASSWORD='change-me'
export SECRET_KEY='change-this-secret'
export DATABASE_URL='sqlite:///data/nsfwtrack.db'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and log in with `APP_PASSWORD`.

## Backup And Export

Open `/backup` after logging in.

Available local-only actions:

- Export a complete JSON backup: `GET /api/backup/export/json`
- Export a readable items CSV: `GET /api/backup/export/csv`
- Preview a JSON backup without writing data: `POST /api/backup/preview/json`
- Restore a JSON backup exported by NSFWTrack: upload the file on `/backup`, or use `POST /api/backup/restore/json`

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

## Docker Compose

```bash
cp .env.example .env
docker compose build
docker compose up
```

The SQLite database is stored under `data/`.

## Tests

```bash
pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
