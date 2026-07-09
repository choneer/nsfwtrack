from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.models import AppSetting
from app.services.item_query import DEFAULT_PAGE_SIZE, DEFAULT_SORT, PAGE_SIZE_OPTIONS

SETTING_KEYS = (
    "default_language",
    "default_page_size",
    "default_sort",
    "default_sort_dir",
    "default_home",
)

SORT_FIELDS = ("updated_at", "created_at", "title", "rating")
SORT_DIRECTIONS = ("desc", "asc")
HOME_OPTIONS = ("workbench", "items", "stats", "activity")
HOME_URLS = {
    "workbench": "/#workbench",
    "items": "/items",
    "stats": "/stats",
    "activity": "/activity",
}

DEFAULT_SETTING_VALUES: dict[str, str] = {
    "default_language": DEFAULT_LANGUAGE,
    "default_page_size": str(DEFAULT_PAGE_SIZE),
    "default_sort": "updated_at",
    "default_sort_dir": "desc",
    "default_home": "workbench",
}

SETTING_OPTIONS: dict[str, tuple[str, ...]] = {
    "default_language": tuple(sorted(SUPPORTED_LANGUAGES)),
    "default_page_size": tuple(str(value) for value in PAGE_SIZE_OPTIONS),
    "default_sort": SORT_FIELDS,
    "default_sort_dir": SORT_DIRECTIONS,
    "default_home": HOME_OPTIONS,
}

_SORT_VALUE_BY_SETTING = {
    ("updated_at", "desc"): "updated_desc",
    ("updated_at", "asc"): "updated_asc",
    ("created_at", "desc"): "created_desc",
    ("created_at", "asc"): "created_asc",
    ("title", "desc"): "title_desc",
    ("title", "asc"): "title_asc",
    ("rating", "desc"): "rating_desc",
    ("rating", "asc"): "rating_asc",
}


@dataclass(frozen=True)
class AppSettings:
    default_language: str
    default_page_size: int
    default_sort: str
    default_sort_dir: str
    default_home: str

    @property
    def item_list_sort(self) -> str:
        return _SORT_VALUE_BY_SETTING.get(
            (self.default_sort, self.default_sort_dir),
            DEFAULT_SORT,
        )

    @property
    def default_home_url(self) -> str:
        return HOME_URLS.get(self.default_home, HOME_URLS["workbench"])

    def form_values(self) -> dict[str, str]:
        return {
            "default_language": self.default_language,
            "default_page_size": str(self.default_page_size),
            "default_sort": self.default_sort,
            "default_sort_dir": self.default_sort_dir,
            "default_home": self.default_home,
        }


class AppSettingsError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_setting_value(key: str, value: Any) -> str:
    cleaned_key = str(key or "").strip()
    if cleaned_key not in SETTING_KEYS:
        raise AppSettingsError("invalid_key")

    cleaned_value = str(value or "").strip()
    if cleaned_value not in SETTING_OPTIONS[cleaned_key]:
        raise AppSettingsError("invalid_value")
    return cleaned_value


def normalize_settings_payload(values: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        cleaned_key = str(key or "").strip()
        normalized[cleaned_key] = validate_setting_value(cleaned_key, value)
    return normalized


def get_app_settings(db: Session) -> AppSettings:
    values = dict(DEFAULT_SETTING_VALUES)
    rows = db.scalars(
        select(AppSetting).where(AppSetting.key.in_(SETTING_KEYS))
    ).all()
    for row in rows:
        try:
            values[row.key] = validate_setting_value(row.key, row.value)
        except AppSettingsError:
            continue
    return AppSettings(
        default_language=values["default_language"],
        default_page_size=int(values["default_page_size"]),
        default_sort=values["default_sort"],
        default_sort_dir=values["default_sort_dir"],
        default_home=values["default_home"],
    )


def get_default_language(db: Session | None) -> str | None:
    if db is None:
        return None
    return get_app_settings(db).default_language


def upsert_setting_row(db: Session, key: str, value: Any) -> str:
    cleaned_key = str(key or "").strip()
    cleaned_value = validate_setting_value(cleaned_key, value)
    row = db.scalar(select(AppSetting).where(AppSetting.key == cleaned_key))
    if row is None:
        db.add(AppSetting(key=cleaned_key, value=cleaned_value))
        return "created"
    if row.value == cleaned_value:
        return "unchanged"
    row.value = cleaned_value
    return "updated"


def save_app_settings(db: Session, values: Mapping[str, Any]) -> dict[str, int]:
    normalized = normalize_settings_payload(values)
    result = {"created": 0, "updated": 0, "unchanged": 0}
    try:
        for key, value in normalized.items():
            action = upsert_setting_row(db, key, value)
            result[action] += 1
        db.commit()
    except AppSettingsError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise AppSettingsError("save_failed") from exc
    return result


def reset_app_settings(db: Session, *, confirm: bool) -> int:
    if not confirm:
        raise AppSettingsError("confirm_required")
    try:
        result = db.execute(delete(AppSetting).where(AppSetting.key.in_(SETTING_KEYS)))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise AppSettingsError("save_failed") from exc
    rowcount = result.rowcount
    if rowcount is None or rowcount < 0:
        return 0
    return rowcount
