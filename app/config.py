from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_password: str
    secret_key: str


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set and cannot be empty")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/nsfwtrack.db").strip()
        or "sqlite:///data/nsfwtrack.db",
        app_password=_read_required_env("APP_PASSWORD"),
        secret_key=_read_required_env("SECRET_KEY"),
    )
