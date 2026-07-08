from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    secret_key: str
    max_backup_upload_mb: int


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set and cannot be empty")
    return value


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/nsfwtrack.db").strip()
        or "sqlite:///data/nsfwtrack.db",
        app_password=_read_required_env("APP_PASSWORD"),
        secret_key=_read_required_env("SECRET_KEY"),
        max_backup_upload_mb=_read_positive_int_env("MAX_BACKUP_UPLOAD_MB", 5),
    )
