from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import models

MAX_SOURCE_URL_LENGTH = 2048
MAX_SOURCE_TITLE_LENGTH = 255
MAX_SOURCE_IMPORT_ROWS = 5000
MAX_EXTERNAL_ID_LENGTH = 512
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
_PROVIDER_KEY = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_METADATA_HASH = re.compile(r"v1:sha256:[0-9a-f]{64}\Z")
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class SourceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SourceTrackingMetadata:
    provider_key: str | None
    external_id: str | None
    last_checked_at: datetime | None
    metadata_hash: str | None


def validate_source_tracking_metadata(
    *,
    provider_key: Any,
    external_id: Any,
    last_checked_at: Any,
    metadata_hash: Any,
) -> SourceTrackingMetadata:
    if provider_key is not None and not isinstance(provider_key, str):
        raise SourceError("invalid_provider_key")
    if external_id is not None and not isinstance(external_id, str):
        raise SourceError("invalid_external_id")
    if metadata_hash is not None and not isinstance(metadata_hash, str):
        raise SourceError("invalid_metadata_hash")
    provider = provider_key
    external = external_id
    checked_value = None if last_checked_at is None else last_checked_at
    hash_value = metadata_hash

    if (provider is None) != (external is None):
        raise SourceError("invalid_provider_identity")
    if provider is None:
        if checked_value is not None or hash_value is not None:
            raise SourceError("provider_metadata_without_identity")
        return SourceTrackingMetadata(None, None, None, None)

    if not _PROVIDER_KEY.fullmatch(provider):
        raise SourceError("invalid_provider_key")
    if (
        not external
        or len(external) > MAX_EXTERNAL_ID_LENGTH
        or _CONTROL_CHARACTER.search(external)
    ):
        raise SourceError("invalid_external_id")

    checked: datetime | None = None
    if checked_value is not None:
        try:
            checked = (
                checked_value
                if isinstance(checked_value, datetime)
                else datetime.fromisoformat(str(checked_value))
            )
        except (TypeError, ValueError):
            raise SourceError("invalid_last_checked_at") from None
        if checked.tzinfo is None or checked.utcoffset() is None:
            raise SourceError("invalid_last_checked_at")
        checked = checked.astimezone(timezone.utc)

    if hash_value is not None and not _METADATA_HASH.fullmatch(hash_value):
        raise SourceError("invalid_metadata_hash")
    return SourceTrackingMetadata(provider, external, checked, hash_value)


@dataclass(frozen=True)
class ParsedSource:
    row: int
    title: str | None
    url: str


@dataclass(frozen=True)
class SourcePreviewRow:
    row: int
    title: str
    url: str
    normalized_url: str
    status: str
    target_item: str
    detail: str = ""


@dataclass(frozen=True)
class SourceImportPreview:
    total: int
    new: int
    duplicate: int
    invalid: int
    conflict: int
    new_items: int
    rows: tuple[SourcePreviewRow, ...]
    payload: str

    @property
    def can_import(self) -> bool:
        return self.new > 0


class _BookmarkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        href = next(
            (value for key, value in attrs if key.casefold() == "href" and value),
            None,
        )
        if href is not None:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        self.entries.append((" ".join(self._text).strip(), self._href))
        self._href = None
        self._text = []


def source_feature_available(db: Session) -> bool:
    inspector = inspect(db.get_bind())
    if "item_sources" not in inspector.get_table_names():
        return False
    actual_columns = {
        column["name"] for column in inspector.get_columns("item_sources")
    }
    required_columns = {column.name for column in models.ItemSource.__table__.columns}
    return required_columns.issubset(actual_columns)


def _normalize_percent_escapes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        byte = int(match.group()[1:], 16)
        character = chr(byte)
        return character if character in _UNRESERVED else f"%{byte:02X}"

    return _PERCENT_ESCAPE.sub(replace, value)


def normalize_source_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url or len(url) > MAX_SOURCE_URL_LENGTH or _CONTROL_OR_SPACE.search(url):
        raise SourceError("invalid_url")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise SourceError("invalid_url") from None
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceError("invalid_url")
    if parsed.username is not None or parsed.password is not None:
        raise SourceError("invalid_url")
    if _BAD_PERCENT_ESCAPE.search(parsed.path) or _BAD_PERCENT_ESCAPE.search(
        parsed.query
    ):
        raise SourceError("invalid_url")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        raise SourceError("invalid_url") from None
    if ":" in hostname:
        hostname = f"[{hostname}]"
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = _normalize_percent_escapes(parsed.path or "/")
    query = _normalize_percent_escapes(parsed.query)
    normalized = urlunsplit((scheme, netloc, path, query, ""))
    if len(normalized) > MAX_SOURCE_URL_LENGTH:
        raise SourceError("invalid_url")
    return normalized


def _clean_title(value: Any) -> str | None:
    title = " ".join(str(value or "").split())
    return title[:MAX_SOURCE_TITLE_LENGTH] or None


def placeholder_title(normalized_url: str) -> str:
    parsed = urlsplit(normalized_url)
    readable = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        readable = f"{readable}?{parsed.query}"
    return readable[:MAX_SOURCE_TITLE_LENGTH] or normalized_url[:MAX_SOURCE_TITLE_LENGTH]


def parse_source_text(text: str) -> list[ParsedSource]:
    rows: list[ParsedSource] = []
    for row_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        title: str | None = None
        url = line
        if "\t" in line:
            raw_title, url = line.split("\t", 1)
            title = _clean_title(raw_title)
            url = url.strip()
        rows.append(ParsedSource(row_number, title, url))
        if len(rows) > MAX_SOURCE_IMPORT_ROWS:
            raise SourceError("too_many_rows")
    return rows


def parse_bookmarks_html(content: bytes) -> list[ParsedSource]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-16")
        except UnicodeDecodeError:
            raise SourceError("invalid_encoding") from None
    parser = _BookmarkParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        raise SourceError("invalid_bookmarks") from None
    if len(parser.entries) > MAX_SOURCE_IMPORT_ROWS:
        raise SourceError("too_many_rows")
    return [
        ParsedSource(index, _clean_title(title), url.strip())
        for index, (title, url) in enumerate(parser.entries, start=1)
    ]


def serialize_parsed_sources(rows: list[ParsedSource]) -> str:
    return "\n".join(
        f"{row.title}\t{row.url}" if row.title else row.url for row in rows
    )


def _index_items_by_title(
    items: list[models.Item],
) -> dict[str, list[models.Item]]:
    items_by_title: dict[str, list[models.Item]] = {}
    for item in items:
        items_by_title.setdefault(item.title.casefold(), []).append(item)
    return items_by_title


def build_source_preview(db: Session, rows: list[ParsedSource]) -> SourceImportPreview:
    if not source_feature_available(db):
        raise SourceError("schema_upgrade_required")
    existing_items = db.scalars(select(models.Item).order_by(models.Item.id)).all()
    items_by_title = _index_items_by_title(existing_items)
    existing_sources = {
        source.normalized_url: source
        for source in db.scalars(select(models.ItemSource)).all()
    }
    item_titles = {item.id: item.title for item in existing_items}
    seen_urls: dict[str, str] = {}
    planned_titles: set[str] = set()
    preview_rows: list[SourcePreviewRow] = []
    counts = {"new": 0, "duplicate": 0, "invalid": 0, "conflict": 0}

    for row in rows:
        try:
            normalized = normalize_source_url(row.url)
        except SourceError:
            counts["invalid"] += 1
            preview_rows.append(
                SourcePreviewRow(
                    row.row,
                    row.title or "",
                    row.url,
                    "",
                    "invalid",
                    "",
                    "invalid_url",
                )
            )
            continue

        title = row.title or placeholder_title(normalized)
        title_key = title.casefold()
        existing_source = existing_sources.get(normalized)
        previous_title = seen_urls.get(normalized)
        matching_items = items_by_title.get(title_key, [])
        target_item = matching_items[0] if len(matching_items) == 1 else None

        if len(matching_items) > 1:
            counts["conflict"] += 1
            preview_rows.append(
                SourcePreviewRow(
                    row.row,
                    title,
                    row.url,
                    normalized,
                    "conflict",
                    title,
                    "ambiguous_existing_title",
                )
            )
            continue

        if previous_title is not None:
            status = "duplicate" if previous_title == title_key else "conflict"
            counts[status] += 1
            preview_rows.append(
                SourcePreviewRow(
                    row.row,
                    title,
                    row.url,
                    normalized,
                    status,
                    target_item.title if target_item else title,
                    "batch_duplicate" if status == "duplicate" else "batch_title_conflict",
                )
            )
            continue
        seen_urls[normalized] = title_key

        if existing_source is not None:
            existing_item_title = item_titles.get(existing_source.item_id, "")
            if row.title and existing_item_title.casefold() != title_key:
                status = "conflict"
                detail = "existing_url_other_item"
            else:
                status = "duplicate"
                detail = "existing_url"
            counts[status] += 1
            preview_rows.append(
                SourcePreviewRow(
                    row.row,
                    title,
                    row.url,
                    normalized,
                    status,
                    existing_item_title,
                    detail,
                )
            )
            continue

        counts["new"] += 1
        if target_item is None:
            planned_titles.add(title_key)
        preview_rows.append(
            SourcePreviewRow(
                row.row,
                title,
                row.url,
                normalized,
                "new",
                target_item.title if target_item else title,
                "existing_item" if target_item else "new_item",
            )
        )

    return SourceImportPreview(
        total=len(rows),
        new=counts["new"],
        duplicate=counts["duplicate"],
        invalid=counts["invalid"],
        conflict=counts["conflict"],
        new_items=len(planned_titles),
        rows=tuple(preview_rows),
        payload=serialize_parsed_sources(rows),
    )


def import_source_rows(db: Session, rows: list[ParsedSource]) -> SourceImportPreview:
    preview = build_source_preview(db, rows)
    new_rows = [row for row in preview.rows if row.status == "new"]
    if not new_rows:
        return preview
    items_by_title = _index_items_by_title(
        list(db.scalars(select(models.Item).order_by(models.Item.id)).all())
    )
    try:
        for row in new_rows:
            title_key = row.title.casefold()
            matching_items = items_by_title.get(title_key, [])
            if len(matching_items) > 1:
                raise SourceError("ambiguous_existing_title")
            if matching_items:
                item = matching_items[0]
            else:
                item = models.Item(title=row.title)
                db.add(item)
                db.flush()
                items_by_title[title_key] = [item]
            original_title = next(
                (
                    parsed.title
                    for parsed in rows
                    if parsed.row == row.row and parsed.url == row.url
                ),
                None,
            )
            db.add(
                models.ItemSource(
                    item_id=item.id,
                    url=row.url,
                    normalized_url=row.normalized_url,
                    title=original_title,
                )
            )
        db.commit()
    except SourceError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise SourceError("import_failed") from None
    return preview


def list_item_sources(db: Session, item_id: int) -> list[models.ItemSource]:
    if not source_feature_available(db):
        return []
    return list(
        db.scalars(
            select(models.ItemSource)
            .where(models.ItemSource.item_id == item_id)
            .order_by(models.ItemSource.created_at.desc(), models.ItemSource.id.desc())
        ).all()
    )


def add_item_source(
    db: Session, item_id: int, url: str, title: str | None
) -> models.ItemSource:
    if not source_feature_available(db):
        raise SourceError("schema_upgrade_required")
    if db.get(models.Item, item_id) is None:
        raise SourceError("item_not_found")
    normalized = normalize_source_url(url)
    existing = db.scalar(
        select(models.ItemSource).where(models.ItemSource.normalized_url == normalized)
    )
    if existing is not None:
        raise SourceError("duplicate" if existing.item_id == item_id else "conflict")
    source = models.ItemSource(
        item_id=item_id,
        url=str(url).strip(),
        normalized_url=normalized,
        title=_clean_title(title),
    )
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        raise SourceError("save_failed") from None
    return source


def delete_item_source(db: Session, item_id: int, source_id: int) -> None:
    if not source_feature_available(db):
        raise SourceError("schema_upgrade_required")
    source = db.scalar(
        select(models.ItemSource).where(
            models.ItemSource.id == source_id,
            models.ItemSource.item_id == item_id,
        )
    )
    if source is None:
        raise SourceError("not_found")
    try:
        db.delete(source)
        db.commit()
    except Exception:
        db.rollback()
        raise SourceError("delete_failed") from None
