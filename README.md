# NSFWTrack

Phase 1 local single-user media record manager.

NSFWTrack is intentionally local-only in Phase 1. It supports manual records,
tags, creators, states, local search, simple stats, CSV/JSON import, login
protection, Docker Compose deployment, and Chinese / English UI switching.

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
