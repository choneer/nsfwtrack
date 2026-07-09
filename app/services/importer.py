from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.services.catalog import serialize_extra, split_names
from app.services.item_query import STATUS_OPTIONS

IMPORT_FIELDS = [
    "title",
    "summary",
    "status",
    "rating",
    "note",
    "tags",
    "creators",
    "collections",
    "extra",
]
CSV_TEMPLATE_FILENAME = "nsfwtrack-import-template.csv"
JSON_TEMPLATE_FILENAME = "nsfwtrack-import-template.json"
IGNORE_FIELD = "ignore"
TARGET_FIELDS = [*IMPORT_FIELDS, IGNORE_FIELD]
PREVIEW_LIMIT = 5

_STATUS_VALUES = set(STATUS_OPTIONS)


class ImportDataError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ImportResult(dict[str, Any]):
    pass


def csv_template_content() -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "title": "Example item",
            "summary": "Example summary",
            "status": "wish",
            "rating": "4",
            "note": "Example note",
            "tags": "example;local",
            "creators": "Example creator",
            "collections": "Example collection",
            "extra": json.dumps({"source": "manual"}, ensure_ascii=False),
        }
    )
    writer.writerow(
        {
            "title": "Second local item",
            "summary": "Another local record",
            "status": "",
            "rating": "",
            "note": "",
            "tags": "local",
            "creators": "",
            "collections": "",
            "extra": "",
        }
    )
    return output.getvalue()


def json_template_content() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "title": "Example item",
                    "summary": "Example summary",
                    "status": "wish",
                    "rating": 4,
                    "note": "Example note",
                    "tags": ["example", "local"],
                    "creators": ["Example creator"],
                    "collections": ["Example collection"],
                    "extra": {"source": "manual"},
                },
                {
                    "title": "Second local item",
                    "summary": "Another local record",
                    "status": "",
                    "rating": None,
                    "note": "",
                    "tags": ["local"],
                    "creators": [],
                    "collections": [],
                    "extra": {},
                },
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


def _blank_summary(total_rows: int = 0) -> dict[str, int]:
    return {
        "total_rows": total_rows,
        "valid_rows": 0,
        "error_rows": 0,
        "new_tags": 0,
        "new_creators": 0,
        "new_collections": 0,
        "collection_links": 0,
        "collections_errors": 0,
    }


def _error(row: int | None, code: str, source: str = "") -> dict[str, Any]:
    return {"row": row, "code": code, "source": source}


def _row_source(row: dict[str, Any]) -> str:
    for key in ("title", "summary", "note", "review"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for value in row.values():
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportDataError("file_decode_error") from exc


def parse_csv_rows(content: bytes) -> list[dict[str, Any]]:
    return parse_csv_upload(content)["rows"]


def parse_csv_upload(content: bytes) -> dict[str, Any]:
    text = _decode_text(content)
    if not text.strip():
        raise ImportDataError("csv_empty")

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        raise ImportDataError("csv_missing_header")

    headers = [header.strip() for header in reader.fieldnames if header and header.strip()]
    if not headers:
        raise ImportDataError("csv_missing_header")

    rows: list[dict[str, Any]] = []
    for row in reader:
        cleaned_row: dict[str, Any] = {}
        for key, value in row.items():
            if key is None:
                continue
            header = key.strip()
            if header:
                cleaned_row[header] = value or ""
        if any(str(value).strip() for value in cleaned_row.values()):
            rows.append(cleaned_row)

    if not rows:
        raise ImportDataError("csv_empty")
    return {"headers": headers, "rows": rows}


def parse_json_rows(content: bytes) -> list[dict[str, Any]]:
    return parse_json_upload(content)


def parse_json_upload(content: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImportDataError("json_format_error") from exc

    if not isinstance(payload, dict) or "items" not in payload:
        raise ImportDataError("json_missing_items")
    if not isinstance(payload["items"], list):
        raise ImportDataError("json_items_not_array")
    return [row for row in payload["items"] if isinstance(row, dict)]


def default_csv_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = header.strip()
        key = normalized.casefold()
        if key in IMPORT_FIELDS:
            mapping[header] = key
        elif key == "review":
            mapping[header] = "note"
        else:
            mapping[header] = IGNORE_FIELD
    return mapping


def build_mapping(source_headers: list[str], target_fields: list[str]) -> dict[str, str]:
    return {
        source: target
        for source, target in zip(source_headers, target_fields, strict=False)
        if source
    }


def validate_csv_mapping(mapping: dict[str, str]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    targets = [target for target in mapping.values() if target != IGNORE_FIELD]
    invalid_targets = [target for target in targets if target not in IMPORT_FIELDS]
    if invalid_targets:
        errors.append(_error(None, "csv_invalid_mapping", ", ".join(invalid_targets)))

    repeated = sorted({target for target in targets if targets.count(target) > 1})
    if repeated:
        errors.append(_error(None, "csv_duplicate_mapping", ", ".join(repeated)))

    if "title" not in targets:
        errors.append(_error(None, "csv_missing_title_mapping"))
    return errors


def apply_csv_mapping(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for source, target in mapping.items():
        if target == IGNORE_FIELD or target not in IMPORT_FIELDS:
            continue
        mapped[target] = row.get(source, "")
    return mapped


def _normalize_rating(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        rating = int(str(value).strip())
    except ValueError as exc:
        raise ImportDataError("invalid_rating") from exc
    if rating < 1 or rating > 5:
        raise ImportDataError("invalid_rating")
    return rating


def _normalize_extra(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ImportDataError("invalid_extra_json") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ImportDataError("invalid_extra_json")


def _normalize_collections(value: Any, source_type: str) -> list[str]:
    if source_type == "json":
        if value is None:
            return []
        if not isinstance(value, list):
            raise ImportDataError("collections_not_array")
        for entry in value:
            if not isinstance(entry, str):
                raise ImportDataError("collections_non_string")
        return split_names(value)
    return split_names(value)


def _normalize_row(row: dict[str, Any], row_number: int, source_type: str) -> dict[str, Any]:
    title = str(row.get("title") or "").strip()
    if not title:
        code = "json_item_missing_title" if source_type == "json" else "missing_title"
        raise ImportDataError(code)

    status = str(row.get("status") or "").strip()
    if status and status not in _STATUS_VALUES:
        raise ImportDataError("invalid_status")

    normalized = {
        "row": row_number,
        "title": title,
        "summary": (str(row.get("summary") or "").strip() or None),
        "status": status or None,
        "rating": _normalize_rating(row.get("rating")),
        "note": (str(row.get("note", row.get("review", "")) or "").strip() or None),
        "tags": split_names(row.get("tags")),
        "creators": split_names(row.get("creators")),
        "collections": _normalize_collections(row.get("collections"), source_type),
        "extra": _normalize_extra(row.get("extra")),
    }
    return normalized


def _existing_names(
    db: Session,
    model: type[models.Tag] | type[models.Creator] | type[models.Collection],
) -> set[str]:
    rows = db.scalars(select(model.name)).all()
    return {name.casefold() for name in rows}


def _summary_for_rows(
    db: Session,
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    existing_tags = _existing_names(db, models.Tag)
    existing_creators = _existing_names(db, models.Creator)
    existing_collections = _existing_names(db, models.Collection)
    tag_names = {
        name.casefold()
        for row in rows
        for name in row["tags"]
        if name.casefold() not in existing_tags
    }
    creator_names = {
        name.casefold()
        for row in rows
        for name in row["creators"]
        if name.casefold() not in existing_creators
    }
    collection_names = {
        name.casefold()
        for row in rows
        for name in row["collections"]
        if name.casefold() not in existing_collections
    }
    collection_error_codes = {"collections_not_array", "collections_non_string"}
    return {
        "total_rows": len(rows) + len([error for error in errors if error.get("row")]),
        "valid_rows": len(rows),
        "error_rows": len(errors),
        "new_tags": len(tag_names),
        "new_creators": len(creator_names),
        "new_collections": len(collection_names),
        "collection_links": sum(len(row["collections"]) for row in rows),
        "collections_errors": len(
            [error for error in errors if error.get("code") in collection_error_codes]
        ),
    }


def _preview_from_rows(
    db: Session,
    raw_rows: list[dict[str, Any]],
    source_type: str,
    mapping_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    valid_rows: list[dict[str, Any]] = []
    row_errors = list(mapping_errors or [])
    if not mapping_errors:
        for index, row in enumerate(raw_rows, start=1):
            try:
                valid_rows.append(_normalize_row(row, index, source_type))
            except ImportDataError as exc:
                row_errors.append(_error(index, exc.code, _row_source(row)))

    summary = _summary_for_rows(db, valid_rows, row_errors)
    if mapping_errors:
        summary["total_rows"] = len(raw_rows)
        summary["valid_rows"] = 0
        summary["error_rows"] = len(row_errors)
        summary["new_tags"] = 0
        summary["new_creators"] = 0
        summary["new_collections"] = 0
        summary["collection_links"] = 0
        summary["collections_errors"] = 0

    return {
        "source_type": source_type,
        "summary": summary,
        "preview_rows": valid_rows[:PREVIEW_LIMIT],
        "errors": row_errors,
        "valid_rows": valid_rows,
        "can_import": bool(valid_rows) and not mapping_errors,
        "mapping_errors": bool(mapping_errors),
        "partial_errors": bool(valid_rows and row_errors),
    }


def preview_csv_import(
    db: Session,
    content: bytes,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    parsed = parse_csv_upload(content)
    headers = parsed["headers"]
    rows = parsed["rows"]
    active_mapping = mapping or default_csv_mapping(headers)
    mapping_errors = validate_csv_mapping(active_mapping)
    mapped_rows = [apply_csv_mapping(row, active_mapping) for row in rows]
    preview = _preview_from_rows(db, mapped_rows, "csv", mapping_errors)
    preview.update(
        {
            "source_headers": headers,
            "raw_rows": rows,
            "mapping": active_mapping,
        }
    )
    return preview


def preview_csv_rows(
    db: Session,
    rows: list[dict[str, Any]],
    headers: list[str],
    mapping: dict[str, str],
) -> dict[str, Any]:
    mapping_errors = validate_csv_mapping(mapping)
    mapped_rows = [apply_csv_mapping(row, mapping) for row in rows]
    preview = _preview_from_rows(db, mapped_rows, "csv", mapping_errors)
    preview.update(
        {
            "source_headers": headers,
            "raw_rows": rows,
            "mapping": mapping,
        }
    )
    return preview


def preview_json_import(db: Session, content: bytes) -> dict[str, Any]:
    rows = parse_json_upload(content)
    preview = _preview_from_rows(db, rows, "json")
    preview.update(
        {
            "source_headers": [],
            "raw_rows": rows,
            "mapping": {},
        }
    )
    return preview


def preview_json_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    preview = _preview_from_rows(db, rows, "json")
    preview.update(
        {
            "source_headers": [],
            "raw_rows": rows,
            "mapping": {},
        }
    )
    return preview


def _get_or_create_tag(db: Session, name: str, result: ImportResult) -> models.Tag:
    cleaned = name.strip()
    tag = db.scalar(select(models.Tag).where(func.lower(models.Tag.name) == cleaned.lower()))
    if tag is not None:
        return tag
    tag = models.Tag(name=cleaned)
    db.add(tag)
    db.flush()
    result["created_tags"] += 1
    return tag


def _get_or_create_creator(db: Session, name: str, result: ImportResult) -> models.Creator:
    cleaned = name.strip()
    creator = db.scalar(
        select(models.Creator).where(func.lower(models.Creator.name) == cleaned.lower())
    )
    if creator is not None:
        return creator
    creator = models.Creator(name=cleaned, type="other")
    db.add(creator)
    db.flush()
    result["created_creators"] += 1
    return creator


def _get_or_create_collection(
    db: Session,
    name: str,
    result: ImportResult,
) -> models.Collection:
    cleaned = name.strip()
    collection = db.scalar(
        select(models.Collection).where(func.lower(models.Collection.name) == cleaned.lower())
    )
    if collection is not None:
        return collection
    collection = models.Collection(name=cleaned)
    db.add(collection)
    db.flush()
    result["created_collections"] += 1
    return collection


def import_valid_rows(
    db: Session,
    valid_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]] | None = None,
) -> ImportResult:
    result = ImportResult(
        imported=0,
        skipped=len(errors or []),
        created_tags=0,
        created_creators=0,
        linked_tags=0,
        linked_creators=0,
        created_collections=0,
        linked_collections=0,
        skipped_collections=0,
        collections_errors=len(
            [
                error
                for error in errors or []
                if error.get("code") in {"collections_not_array", "collections_non_string"}
            ]
        ),
        state_records=0,
        error_rows=len(errors or []),
        errors=list(errors or []),
    )
    if not valid_rows:
        return result

    try:
        for row in valid_rows:
            item = models.Item(
                title=row["title"],
                summary=row["summary"],
                extra=serialize_extra(row["extra"]),
            )
            db.add(item)
            db.flush()

            tags = [_get_or_create_tag(db, name, result) for name in row["tags"]]
            creators = [
                _get_or_create_creator(db, name, result) for name in row["creators"]
            ]
            collections = [
                _get_or_create_collection(db, name, result)
                for name in row["collections"]
            ]
            item.tags = tags
            item.creators = creators
            item.collections = collections
            result["linked_tags"] += len(tags)
            result["linked_creators"] += len(creators)
            result["linked_collections"] += len(collections)

            if row["status"]:
                state = models.UserItemState(
                    item_id=item.id,
                    status=row["status"],
                    rating=row["rating"],
                    review=row["note"],
                )
                db.add(state)
                result["state_records"] += 1

            result["imported"] += 1
        db.commit()
    except Exception:
        db.rollback()
        return ImportResult(
            imported=0,
            skipped=len(valid_rows) + len(errors or []),
            created_tags=0,
            created_creators=0,
            linked_tags=0,
            linked_creators=0,
            created_collections=0,
            linked_collections=0,
            skipped_collections=0,
            collections_errors=len(valid_rows) + len(errors or []),
            state_records=0,
            error_rows=len(valid_rows) + len(errors or []),
            errors=[*(errors or []), _error(None, "import_failed")],
        )
    return result


def import_rows(db: Session, rows: list[dict[str, Any]]) -> ImportResult:
    preview = preview_json_rows(db, rows)
    return import_valid_rows(db, preview["valid_rows"], preview["errors"])


def import_csv(db: Session, content: bytes) -> ImportResult:
    preview = preview_csv_import(db, content)
    return import_valid_rows(db, preview["valid_rows"], preview["errors"])


def import_json(db: Session, content: bytes) -> ImportResult:
    preview = preview_json_import(db, content)
    return import_valid_rows(db, preview["valid_rows"], preview["errors"])
