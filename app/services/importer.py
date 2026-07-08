from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas import ItemCreate, StateCreate
from app.services.catalog import create_item, set_state, split_names


class ImportResult(dict[str, Any]):
    pass


def _coerce_rating(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def _build_payload(row: dict[str, Any]) -> tuple[ItemCreate, StateCreate | None]:
    item = ItemCreate(
        title=str(row.get("title", "")).strip(),
        cover_path=(str(row.get("cover_path", "")).strip() or None),
        summary=(str(row.get("summary", "")).strip() or None),
        release_date=(str(row.get("release_date", "")).strip() or None),
        extra=row.get("extra") if isinstance(row.get("extra"), dict) else None,
        tags=split_names(row.get("tags")),
        creators=split_names(row.get("creators")),
    )
    status = str(row.get("status", "")).strip()
    state = None
    if status:
        state = StateCreate(
            status=status,
            rating=_coerce_rating(row.get("rating")),
            review=(str(row.get("review", "")).strip() or None),
        )
    return item, state


def import_rows(db: Session, rows: list[dict[str, Any]]) -> ImportResult:
    imported = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        try:
            item_payload, state_payload = _build_payload(row)
            item = create_item(db, item_payload)
            if state_payload is not None:
                set_state(db, item, state_payload)
            imported += 1
        except (ValueError, ValidationError) as exc:
            skipped += 1
            errors.append({"row": index, "error": str(exc)})
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


def parse_csv_rows(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


def parse_json_rows(content: bytes) -> list[dict[str, Any]]:
    payload = json.loads(content.decode("utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [row for row in payload["items"] if isinstance(row, dict)]
    return []


def import_csv(db: Session, content: bytes) -> ImportResult:
    return import_rows(db, parse_csv_rows(content))


def import_json(db: Session, content: bytes) -> ImportResult:
    return import_rows(db, parse_json_rows(content))
