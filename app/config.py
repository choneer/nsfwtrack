from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


_EXAMPLE_PLACEHOLDERS = {
    "APP_PASSWORD": "your_secure_password_here",
    "SECRET_KEY": "change_this_to_a_random_secret_key",
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    secret_key: str
    max_backup_upload_mb: int
    max_import_upload_mb: int
    session_cookie_secure: bool
    task_max_concurrency: int = 2
    download_max_bytes: int = 100 * 1024 * 1024
    download_chunk_bytes: int = 64 * 1024
    download_timeout_seconds: int = 60
    download_temp_retention_hours: int = 24
    task_history_retention_days: int = 30


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set and cannot be empty")
    if value == _EXAMPLE_PLACEHOLDERS.get(name):
        raise RuntimeError(f"{name} must not use the shipped example placeholder")
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


def _read_bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    value = _read_positive_int_env(name, default)
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().casefold()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/nsfwtrack.db").strip()
        or "sqlite:///data/nsfwtrack.db",
        app_password=_read_required_env("APP_PASSWORD"),
        secret_key=_read_required_env("SECRET_KEY"),
        max_backup_upload_mb=_read_positive_int_env("MAX_BACKUP_UPLOAD_MB", 5),
        max_import_upload_mb=_read_positive_int_env("MAX_IMPORT_UPLOAD_MB", 5),
        session_cookie_secure=_read_bool_env("SESSION_COOKIE_SECURE", False),
        task_max_concurrency=_read_bounded_int_env(
            "TASK_MAX_CONCURRENCY", 2, 1, 32
        ),
        download_max_bytes=_read_bounded_int_env(
            "DOWNLOAD_MAX_BYTES", 100 * 1024 * 1024, 1_024, 10 * 1024 * 1024 * 1024
        ),
        download_chunk_bytes=_read_bounded_int_env(
            "DOWNLOAD_CHUNK_BYTES", 64 * 1024, 4_096, 4 * 1024 * 1024
        ),
        download_timeout_seconds=_read_bounded_int_env(
            "DOWNLOAD_TIMEOUT_SECONDS", 60, 1, 3_600
        ),
        download_temp_retention_hours=_read_bounded_int_env(
            "DOWNLOAD_TEMP_RETENTION_HOURS", 24, 1, 720
        ),
        task_history_retention_days=_read_bounded_int_env(
            "TASK_HISTORY_RETENTION_DAYS", 30, 1, 3_650
        ),
    )
