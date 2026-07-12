from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.catalog import serialize_extra, split_names
from app.services.item_query import STATUS_OPTIONS
from app.services.sources import SourceError, normalize_source_url

IMPORT_FIELDS = [
    "title",
    "summary",
    "status",
    "rating",
    "note",
    "tags",
    "creators",
    "collections",
    "sources",
    "extra",
]
CSV_TEMPLATE_FILENAME = "nsfwtrack-import-template.csv"
JSON_TEMPLATE_FILENAME = "nsfwtrack-import-template.json"
IGNORE_FIELD = "ignore"
TARGET_FIELDS = [*IMPORT_FIELDS, IGNORE_FIELD]
PREVIEW_LIMIT = 5

_STATUS_VALUES = set(STATUS_OPTIONS)
_SOURCE_FIELDS = set(IMPORT_FIELDS) | {"review"}


class ImportDataError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ImportResult(dict[str, Any]):
    pass


async def read_import_upload(file: UploadFile) -> bytes:
    max_bytes = get_settings().max_import_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ImportDataError("file_too_large")
    return content


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
            "sources": json.dumps(
                [{"title": "Example source", "url": "https://example.com/item"}],
                ensure_ascii=False,
            ),
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
            "sources": "",
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
                    "sources": [
                        {"title": "Example source", "url": "https://example.com/item"}
                    ],
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
                    "sources": [],
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


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


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


def _normalize_name_list(value: Any, field_name: str, source_type: str) -> list[str]:
    if source_type == "json":
        if value is None:
            return []
        if isinstance(value, str):
            return split_names(value)
        if not isinstance(value, list):
            raise ImportDataError(f"invalid_{field_name}")
        for entry in value:
            if not isinstance(entry, str):
                raise ImportDataError(f"invalid_{field_name}")
        return split_names(value)
    return split_names(value)


def _normalize_sources(value: Any, source_type: str) -> list[dict[str, str | None]]:
    if value is None or value == "":
        return []
    parsed: Any = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                raise ImportDataError("invalid_sources") from None
        elif source_type == "csv":
            parsed = [{"url": entry.strip()} for entry in stripped.split(";") if entry.strip()]
    if not isinstance(parsed, list):
        raise ImportDataError("invalid_sources")
    normalized: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for entry in parsed:
        if isinstance(entry, str):
            title = None
            url = entry
        elif isinstance(entry, dict):
            title = " ".join(str(entry.get("title") or "").split())[:255] or None
            url = str(entry.get("url") or "").strip()
        else:
            raise ImportDataError("invalid_sources")
        try:
            normalized_url = normalize_source_url(url)
        except SourceError:
            raise ImportDataError("invalid_sources") from None
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        normalized.append(
            {"title": title, "url": url, "normalized_url": normalized_url}
        )
    return normalized


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
        "tags": _normalize_name_list(row.get("tags"), "tags", source_type),
        "creators": _normalize_name_list(row.get("creators"), "creators", source_type),
        "collections": _normalize_collections(row.get("collections"), source_type),
        "sources": _normalize_sources(row.get("sources"), source_type),
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


def build_import_dry_run_report(
    db: Session,
    source_type: str,
    raw_rows: list[dict[str, Any]],
    valid_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    source_headers: list[str] | None = None,
    mapping: dict[str, str] | None = None,
    mapping_errors: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = [
        _dry_run_issue(
            "error",
            str(error.get("code") or "invalid_row"),
            source_type,
            row=error.get("row"),
            detail=error.get("source") or "",
        )
        for error in errors
    ]
    if source_type == "csv":
        issues.extend(
            _csv_unknown_field_issues(
                raw_rows,
                source_headers or [],
                mapping or {},
            )
        )
    else:
        issues.extend(_json_unknown_field_issues(raw_rows))
        issues.extend(_json_name_shape_warnings(raw_rows))
    issues.extend(_duplicate_title_issues(db, valid_rows))
    issues.extend(
        [
            _dry_run_issue("info", "dry_run_no_write", source_type),
            _dry_run_issue("info", "backup_recommended", source_type),
            _dry_run_issue("info", "import_read_rows", source_type, detail=str(len(raw_rows))),
            _dry_run_issue(
                "info",
                "import_valid_rows",
                source_type,
                detail=str(len(valid_rows)),
            ),
            _dry_run_issue(
                "info",
                "import_skipped_rows",
                source_type,
                detail=str(len(errors)),
            ),
        ]
    )
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    info_count = sum(1 for issue in issues if issue["severity"] == "info")
    status_value = "ready"
    if mapping_errors or not valid_rows:
        status_value = "blocked"
    elif error_count or warning_count:
        status_value = "warning"
    return {
        "status": status_value,
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "issues": issues,
    }


def _csv_unknown_field_issues(
    raw_rows: list[dict[str, Any]],
    source_headers: list[str],
    mapping: dict[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for header in source_headers:
        normalized = header.strip().casefold()
        if normalized in _SOURCE_FIELDS:
            continue
        if mapping.get(header) != IGNORE_FIELD:
            continue
        if not any(not _is_blank(row.get(header)) for row in raw_rows):
            continue
        issues.append(_dry_run_issue("warning", "unknown_field", "csv", detail=header))
    return issues


def _json_unknown_field_issues(
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows, start=1):
        for field in sorted(set(row) - _SOURCE_FIELDS):
            issues.append(
                _dry_run_issue("warning", "unknown_field", "json", row=index, detail=field)
            )
    return issues


def _json_name_shape_warnings(
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows, start=1):
        for field_name in ("tags", "creators"):
            value = row.get(field_name)
            if isinstance(value, str) and value.strip():
                issues.append(
                    _dry_run_issue(
                        "warning",
                        "json_names_string",
                        "json",
                        row=index,
                        detail=field_name,
                    )
                )
    return issues


def _duplicate_title_issues(
    db: Session,
    valid_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    duplicate_titles: set[str] = set()
    for row in valid_rows:
        title = str(row.get("title") or "").strip()
        key = title.casefold()
        if not key:
            continue
        if key in seen_titles:
            duplicate_titles.add(key)
            issues.append(
                _dry_run_issue(
                    "warning",
                    "duplicate_title",
                    "items",
                    row=row.get("row"),
                    detail=title,
                )
            )
        seen_titles.add(key)

    if not seen_titles:
        return issues
    existing_titles = {
        title.casefold()
        for title in db.scalars(select(models.Item.title)).all()
        if title and title.casefold() in seen_titles
    }
    for row in valid_rows:
        title = str(row.get("title") or "").strip()
        key = title.casefold()
        if key in existing_titles and key not in duplicate_titles:
            issues.append(
                _dry_run_issue(
                    "warning",
                    "existing_title",
                    "items",
                    row=row.get("row"),
                    detail=title,
                )
            )
    return issues


def _dry_run_issue(
    severity: str,
    code: str,
    data_type: str,
    row: Any = None,
    object_id: str = "",
    detail: Any = "",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "data_type": data_type,
        "row": row,
        "object_id": object_id,
        "detail": _short_import_value(detail),
    }


def _short_import_value(value: Any, limit: int = 160) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _preview_from_rows(
    db: Session,
    raw_rows: list[dict[str, Any]],
    source_type: str,
    mapping_errors: list[dict[str, Any]] | None = None,
    source_rows: list[dict[str, Any]] | None = None,
    source_headers: list[str] | None = None,
    mapping: dict[str, str] | None = None,
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

    dry_run_report = build_import_dry_run_report(
        db=db,
        source_type=source_type,
        raw_rows=source_rows or raw_rows,
        valid_rows=valid_rows,
        errors=row_errors,
        source_headers=source_headers or [],
        mapping=mapping or {},
        mapping_errors=bool(mapping_errors),
    )

    return {
        "source_type": source_type,
        "summary": summary,
        "preview_rows": valid_rows[:PREVIEW_LIMIT],
        "errors": row_errors,
        "dry_run_report": dry_run_report,
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
    preview = _preview_from_rows(
        db,
        mapped_rows,
        "csv",
        mapping_errors,
        source_rows=rows,
        source_headers=headers,
        mapping=active_mapping,
    )
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
    preview = _preview_from_rows(
        db,
        mapped_rows,
        "csv",
        mapping_errors,
        source_rows=rows,
        source_headers=headers,
        mapping=mapping,
    )
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
    preview = _preview_from_rows(db, rows, "json", source_rows=rows)
    preview.update(
        {
            "source_headers": [],
            "raw_rows": rows,
            "mapping": {},
        }
    )
    return preview


def preview_json_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    preview = _preview_from_rows(db, rows, "json", source_rows=rows)
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
        created_sources=0,
        skipped_sources=0,
        source_errors=len(
            [error for error in errors or [] if error.get("code") == "invalid_sources"]
        ),
        state_records=0,
        error_rows=len(errors or []),
        errors=list(errors or []),
    )
    if not valid_rows:
        return result

    try:
        known_source_urls = set(db.scalars(select(models.ItemSource.normalized_url)).all())
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

            for source_row in row["sources"]:
                normalized_url = str(source_row["normalized_url"])
                if normalized_url in known_source_urls:
                    result["skipped_sources"] += 1
                    continue
                db.add(
                    models.ItemSource(
                        item_id=item.id,
                        url=str(source_row["url"]),
                        normalized_url=normalized_url,
                        title=source_row["title"],
                    )
                )
                known_source_urls.add(normalized_url)
                result["created_sources"] += 1

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
            created_sources=0,
            skipped_sources=0,
            source_errors=len(valid_rows) + len(errors or []),
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
