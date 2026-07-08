# NSFWTrack

Local single-user media record manager for Phase 1.

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

## Docker Compose

```bash
cp .env.example .env
docker compose build
docker compose up
```

The SQLite database is stored under `data/`.

## Tests

```bash
.venv/bin/python -m pytest
```
