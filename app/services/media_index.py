from __future__ import annotations

import hashlib
import hmac
import json
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Literal

from sqlalchemy import delete, inspect, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MediaIndexEntry, MediaIndexState
from app.services import local_media


MEDIA_INDEX_FORMAT_VERSION = 1
MEDIA_INDEX_STATE_ID = 1
MEDIA_INDEX_REFRESH_SOURCES = frozenset(
    {
        "manual_incremental",
        "manual_full",
        "post_upload",
        "post_rename",
        "post_move",
        "post_batch",
        "post_cleanup",
        "post_recovery",
        "post_root_init",
        "post_directory",
    }
)
_HEX_DIGITS = frozenset("0123456789abcdef")
_SKIP_REASONS = frozenset(
    {
        "symlink",
        "unsupported_extension",
        "special_file",
        "directory_unreadable",
        "entry_error",
    }
)


class MediaIndexError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaIndexStatus:
    schema_available: bool
    valid: bool
    integrity_valid: bool
    stale_reason: str
    index_format_version: int
    current_media_root_identity: str
    last_incremental_scan_at: datetime | None
    last_full_verification_at: datetime | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_scan_kind: str | None
    last_refresh_source: str | None
    last_scan_result: str
    last_scan_error: str
    duration_ms: int
    entry_count: int
    valid_count: int
    damaged_count: int
    recovered_count: int
    skipped_count: int
    reused_count: int
    new_count: int
    changed_count: int
    removed_count: int
    rehashed_count: int
    change_details: tuple[dict[str, str], ...]

    @property
    def usable(self) -> bool:
        return self.schema_available and self.valid and self.integrity_valid

    @property
    def possibly_stale(self) -> bool:
        return not self.usable or bool(self.stale_reason)


@dataclass(frozen=True)
class MediaIndexSnapshot:
    scan: local_media.LocalMediaScan
    directories: tuple[local_media.ValidatedLocalMediaDirectory, ...]
    status: MediaIndexStatus
    source: Literal["index", "filesystem"]


@dataclass(frozen=True)
class MediaIndexRefreshResult:
    status: MediaIndexStatus
    scan: local_media.LocalMediaScan
    directories: tuple[local_media.ValidatedLocalMediaDirectory, ...]


@dataclass(frozen=True)
class _TrustedMediaRow:
    entry: local_media.LocalMediaEntry
    first_seen_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat(timespec="microseconds") if value is not None else None


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _signature(payload: object) -> str:
    return hmac.new(
        get_settings().secret_key.encode("utf-8"),
        _canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()


def _valid_token(value: str) -> bool:
    normalized = value.casefold()
    return len(normalized) == 64 and all(character in _HEX_DIGITS for character in normalized)


def _row_payload(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _datetime_text(value) if isinstance(value, datetime) else value
        for key, value in values.items()
        if key not in {"id", "cache_signature"}
    }


def _row_values(row: MediaIndexEntry) -> dict[str, Any]:
    return {
        "record_type": row.record_type,
        "media_path": row.media_path,
        "basename": row.basename,
        "parent_directory": row.parent_directory,
        "extension": row.extension,
        "mime_type": row.mime_type,
        "size": row.size,
        "sha256": row.sha256,
        "valid": row.valid,
        "detail": row.detail,
        "recovered": row.recovered,
        "mode": row.mode,
        "device": row.device,
        "inode": row.inode,
        "modified_ns": row.modified_ns,
        "changed_ns": row.changed_ns,
        "directory_mapping_token": row.directory_mapping_token,
        "directory_identity_json": row.directory_identity_json,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "indexed_at": row.indexed_at,
    }


def _row_is_signed(row: MediaIndexEntry) -> bool:
    return _valid_token(row.cache_signature) and hmac.compare_digest(
        row.cache_signature.casefold(),
        _signature(_row_payload(_row_values(row))),
    )


def _state_values(state: MediaIndexState) -> dict[str, Any]:
    return {
        "id": state.id,
        "index_format_version": state.index_format_version,
        "valid": state.valid,
        "stale_reason": state.stale_reason,
        "current_media_root_identity": state.current_media_root_identity,
        "last_incremental_scan_at": state.last_incremental_scan_at,
        "last_full_verification_at": state.last_full_verification_at,
        "last_attempt_at": state.last_attempt_at,
        "last_success_at": state.last_success_at,
        "last_scan_kind": state.last_scan_kind,
        "last_scan_result": state.last_scan_result,
        "last_scan_error": state.last_scan_error,
        "duration_ms": state.duration_ms,
        "entry_count": state.entry_count,
        "valid_count": state.valid_count,
        "damaged_count": state.damaged_count,
        "recovered_count": state.recovered_count,
        "skipped_count": state.skipped_count,
        "reused_count": state.reused_count,
        "new_count": state.new_count,
        "changed_count": state.changed_count,
        "removed_count": state.removed_count,
        "rehashed_count": state.rehashed_count,
        "change_details_json": state.change_details_json,
        "skipped_details_json": state.skipped_details_json,
    }


def _state_payload(
    values: dict[str, Any],
    row_signatures: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "state": {
            key: _datetime_text(value) if isinstance(value, datetime) else value
            for key, value in values.items()
        },
        "row_signatures": sorted(row_signatures),
    }


def _decode_change_payload(value: str) -> tuple[str | None, object]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None, ()
    if isinstance(payload, dict):
        source = payload.get("refresh_source")
        rows = payload.get("entries", ())
        return (
            source if isinstance(source, str) and source in MEDIA_INDEX_REFRESH_SOURCES else None,
            rows,
        )
    return None, payload


def _decode_change_details(value: str) -> tuple[dict[str, str], ...]:
    _, rows = _decode_change_payload(value)
    if not isinstance(rows, list):
        return ()
    details: list[dict[str, str]] = []
    for row in rows[:200]:
        if not isinstance(row, dict):
            continue
        change = row.get("change")
        path = row.get("path")
        if isinstance(change, str) and isinstance(path, str):
            details.append({"change": change[:32], "path": path[:500]})
    return tuple(details)


def _decode_refresh_source(value: str, scan_kind: str | None) -> str | None:
    source, _ = _decode_change_payload(value)
    if source is not None:
        return source
    return {
        "incremental": "manual_incremental",
        "full": "manual_full",
    }.get(scan_kind)


def _encode_change_payload(
    source: str,
    rows: list[dict[str, str]] | tuple[dict[str, str], ...],
) -> str:
    return json.dumps(
        {"refresh_source": source, "entries": list(rows)},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _status_from_state(
    state: MediaIndexState | None,
    *,
    schema_available: bool,
    integrity_valid: bool,
    stale_reason: str | None = None,
) -> MediaIndexStatus:
    if state is None:
        return MediaIndexStatus(
            schema_available=schema_available,
            valid=False,
            integrity_valid=integrity_valid,
            stale_reason=stale_reason or "never_scanned",
            index_format_version=MEDIA_INDEX_FORMAT_VERSION,
            current_media_root_identity="",
            last_incremental_scan_at=None,
            last_full_verification_at=None,
            last_attempt_at=None,
            last_success_at=None,
            last_scan_kind=None,
            last_refresh_source=None,
            last_scan_result="never",
            last_scan_error="",
            duration_ms=0,
            entry_count=0,
            valid_count=0,
            damaged_count=0,
            recovered_count=0,
            skipped_count=0,
            reused_count=0,
            new_count=0,
            changed_count=0,
            removed_count=0,
            rehashed_count=0,
            change_details=(),
        )
    return MediaIndexStatus(
        schema_available=schema_available,
        valid=bool(state.valid),
        integrity_valid=integrity_valid,
        stale_reason=stale_reason if stale_reason is not None else state.stale_reason,
        index_format_version=state.index_format_version,
        current_media_root_identity=state.current_media_root_identity,
        last_incremental_scan_at=state.last_incremental_scan_at,
        last_full_verification_at=state.last_full_verification_at,
        last_attempt_at=state.last_attempt_at,
        last_success_at=state.last_success_at,
        last_scan_kind=state.last_scan_kind,
        last_refresh_source=_decode_refresh_source(
            state.change_details_json,
            state.last_scan_kind,
        ),
        last_scan_result=state.last_scan_result,
        last_scan_error=state.last_scan_error,
        duration_ms=state.duration_ms,
        entry_count=state.entry_count,
        valid_count=state.valid_count,
        damaged_count=state.damaged_count,
        recovered_count=state.recovered_count,
        skipped_count=state.skipped_count,
        reused_count=state.reused_count,
        new_count=state.new_count,
        changed_count=state.changed_count,
        removed_count=state.removed_count,
        rehashed_count=state.rehashed_count,
        change_details=_decode_change_details(state.change_details_json),
    )


def _schema_available(db: Session) -> bool:
    try:
        tables = set(inspect(db.get_bind()).get_table_names())
    except SQLAlchemyError:
        return False
    return {MediaIndexEntry.__tablename__, MediaIndexState.__tablename__}.issubset(tables)


def _media_entry_from_row(row: MediaIndexEntry) -> local_media.LocalMediaEntry:
    if row.record_type != "media" or not _row_is_signed(row):
        raise MediaIndexError("index_corrupt")
    try:
        normalized = local_media.normalize_local_media_path(row.media_path)
    except local_media.LocalMediaPathError:
        raise MediaIndexError("index_corrupt") from None
    if normalized != row.media_path or normalized is None:
        raise MediaIndexError("index_corrupt")
    relative = normalized.removeprefix(local_media.LOCAL_MEDIA_PREFIX)
    parent = PurePosixPath(normalized).parent.as_posix()
    try:
        directory = local_media.local_media_directory_from_index(
            parent,
            row.directory_identity_json,
        )
    except local_media.LocalMediaPathError:
        raise MediaIndexError("index_corrupt") from None
    if (
        row.basename != PurePosixPath(relative).name
        or row.parent_directory != parent
        or row.extension != PurePosixPath(relative).suffix.casefold()
        or not stat.S_ISREG(row.mode)
        or row.size < 0
        or row.device < 0
        or row.inode < 0
        or row.modified_ns < 0
        or row.changed_ns < 0
        or not _valid_token(row.directory_mapping_token)
        or local_media.local_media_directory_mapping_token(directory)
        != row.directory_mapping_token
    ):
        raise MediaIndexError("index_corrupt")
    entry = local_media.LocalMediaEntry(
        media_path=row.media_path,
        filename=relative,
        size=row.size,
        sha256=row.sha256,
        mime_type=row.mime_type,
        available=bool(row.valid),
        detail=row.detail,
        is_recovered=bool(row.recovered),
        device=row.device,
        inode=row.inode,
        modified_ns=row.modified_ns,
        changed_ns=row.changed_ns,
        mode=row.mode,
        directory_mapping_token=row.directory_mapping_token,
        directory_identity_json=row.directory_identity_json,
    )
    digest = entry.sha256.casefold()
    valid_digest = _valid_token(digest)
    if entry.available:
        if not valid_digest or not entry.mime_type or entry.detail:
            raise MediaIndexError("index_corrupt")
    elif entry.mime_type or entry.detail != "invalid_image" or (digest and not valid_digest):
        raise MediaIndexError("index_corrupt")
    return entry


def _directory_from_row(
    row: MediaIndexEntry,
) -> local_media.ValidatedLocalMediaDirectory:
    if row.record_type != "directory" or not _row_is_signed(row):
        raise MediaIndexError("index_corrupt")
    try:
        directory = local_media.local_media_directory_from_index(
            row.media_path,
            row.directory_identity_json,
        )
    except local_media.LocalMediaPathError:
        raise MediaIndexError("index_corrupt") from None
    expected_basename = "media" if row.media_path == "/media" else directory.parts[-1]
    expected_parent = PurePosixPath(row.media_path).parent.as_posix()
    if row.media_path == "/media":
        expected_parent = "/"
    if (
        not row.valid
        or row.basename != expected_basename
        or row.parent_directory != expected_parent
        or row.extension
        or row.mime_type
        or row.size != 0
        or row.sha256
        or row.detail
        or row.recovered
        or row.mode != directory.mode
        or row.device != directory.device
        or row.inode != directory.inode
        or row.modified_ns != directory.modified_ns
        or row.changed_ns != directory.changed_ns
        or local_media.local_media_directory_mapping_token(directory)
        != row.directory_mapping_token
    ):
        raise MediaIndexError("index_corrupt")
    return directory


def _decode_skips(value: str) -> tuple[local_media.LocalMediaScanSkip, ...]:
    try:
        rows = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        raise MediaIndexError("index_corrupt") from None
    if not isinstance(rows, list):
        raise MediaIndexError("index_corrupt")
    skips: list[local_media.LocalMediaScanSkip] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("reason") not in _SKIP_REASONS:
            raise MediaIndexError("index_corrupt")
        try:
            skips.append(
                local_media.LocalMediaScanSkip(
                    path=str(row["path"]),
                    reason=row["reason"],
                    extension=str(row["extension"]),
                    size=None if row["size"] is None else int(row["size"]),
                    device=None if row["device"] is None else int(row["device"]),
                    inode=None if row["inode"] is None else int(row["inode"]),
                    modified_ns=(
                        None if row["modified_ns"] is None else int(row["modified_ns"])
                    ),
                    changed_ns=(
                        None if row["changed_ns"] is None else int(row["changed_ns"])
                    ),
                )
            )
        except (KeyError, TypeError, ValueError):
            raise MediaIndexError("index_corrupt") from None
    return tuple(skips)


def _load_index_snapshot(db: Session) -> MediaIndexSnapshot | None:
    if not _schema_available(db):
        return None
    state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
    if state is None or not state.valid:
        return None
    rows = tuple(db.scalars(select(MediaIndexEntry).order_by(MediaIndexEntry.media_path)))
    row_signatures = tuple(row.cache_signature for row in rows)
    integrity_valid = (
        state.index_format_version == MEDIA_INDEX_FORMAT_VERSION
        and _valid_token(state.snapshot_signature)
        and hmac.compare_digest(
            state.snapshot_signature.casefold(),
            _signature(_state_payload(_state_values(state), row_signatures)),
        )
    )
    if not integrity_valid:
        raise MediaIndexError("index_corrupt")
    entries = tuple(_media_entry_from_row(row) for row in rows if row.record_type == "media")
    directories = tuple(
        _directory_from_row(row) for row in rows if row.record_type == "directory"
    )
    skips = _decode_skips(state.skipped_details_json)
    if (
        len(entries) != state.entry_count
        or sum(entry.available for entry in entries) != state.valid_count
        or sum(not entry.available for entry in entries) != state.damaged_count
        or sum(entry.is_recovered for entry in entries) != state.recovered_count
        or len(skips) != state.skipped_count
        or not directories
        or directories[0].media_path != "/media"
        or local_media.local_media_directory_mapping_token(directories[0])
        != state.current_media_root_identity
    ):
        raise MediaIndexError("index_corrupt")
    scan = local_media.LocalMediaScan(
        entries=entries,
        skipped_symlinks=sum(row.reason == "symlink" for row in skips),
        skipped_unsupported=sum(row.reason != "symlink" for row in skips),
        invalid=state.damaged_count,
        skipped_entries=skips,
    )
    return MediaIndexSnapshot(
        scan=scan,
        directories=directories,
        status=_status_from_state(
            state,
            schema_available=True,
            integrity_valid=True,
        ),
        source="index",
    )


def get_media_index_status(db: Session) -> MediaIndexStatus:
    if not _schema_available(db):
        return _status_from_state(
            None,
            schema_available=False,
            integrity_valid=False,
            stale_reason="schema_upgrade_required",
        )
    state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
    if state is None:
        return _status_from_state(
            None,
            schema_available=True,
            integrity_valid=False,
            stale_reason="state_missing",
        )
    if not state.valid:
        return _status_from_state(
            state,
            schema_available=True,
            integrity_valid=not state.snapshot_signature or _valid_token(state.snapshot_signature),
        )
    try:
        snapshot = _load_index_snapshot(db)
    except MediaIndexError:
        return _status_from_state(
            state,
            schema_available=True,
            integrity_valid=False,
            stale_reason="index_corrupt",
        )
    assert snapshot is not None
    return snapshot.status


def load_preferred_media_snapshot(db: Session) -> MediaIndexSnapshot:
    try:
        snapshot = _load_index_snapshot(db)
    except MediaIndexError:
        snapshot = None
        status = get_media_index_status(db)
    else:
        status = snapshot.status if snapshot is not None else get_media_index_status(db)
    if snapshot is not None:
        return snapshot

    observed = local_media.scan_local_media_incremental(force_rehash=True)
    if not observed.root_identity:
        raise local_media.LocalMediaPathError("local media root unavailable")
    directories = local_media.scan_local_media_directories()
    if (
        not directories
        or local_media.local_media_directory_mapping_token(directories[0])
        != observed.root_identity
    ):
        raise local_media.LocalMediaPathError("local media root changed during scan")
    return MediaIndexSnapshot(
        scan=observed.scan,
        directories=directories,
        status=status,
        source="filesystem",
    )


def _entry_change_key(entry: local_media.LocalMediaEntry) -> tuple[object, ...]:
    return (
        entry.filename,
        entry.size,
        entry.sha256,
        entry.mime_type,
        entry.available,
        entry.detail,
        entry.is_recovered,
        entry.mode,
        entry.device,
        entry.inode,
        entry.modified_ns,
        entry.changed_ns,
        entry.directory_mapping_token,
    )


def _trusted_old_media_rows(
    rows: tuple[MediaIndexEntry, ...],
) -> dict[str, _TrustedMediaRow]:
    trusted: dict[str, _TrustedMediaRow] = {}
    for row in rows:
        if row.record_type != "media":
            continue
        try:
            entry = _media_entry_from_row(row)
        except MediaIndexError:
            continue
        trusted[row.media_path] = _TrustedMediaRow(entry, row.first_seen_at)
    return trusted


def _media_row_values(
    entry: local_media.LocalMediaEntry,
    *,
    first_seen_at: datetime,
    observed_at: datetime,
) -> dict[str, Any]:
    relative = PurePosixPath(entry.filename)
    values: dict[str, Any] = {
        "record_type": "media",
        "media_path": entry.media_path,
        "basename": relative.name,
        "parent_directory": PurePosixPath(entry.media_path).parent.as_posix(),
        "extension": relative.suffix.casefold(),
        "mime_type": entry.mime_type,
        "size": entry.size,
        "sha256": entry.sha256,
        "valid": entry.available,
        "detail": entry.detail,
        "recovered": entry.is_recovered,
        "mode": entry.mode,
        "device": entry.device,
        "inode": entry.inode,
        "modified_ns": entry.modified_ns,
        "changed_ns": entry.changed_ns,
        "directory_mapping_token": entry.directory_mapping_token,
        "directory_identity_json": entry.directory_identity_json,
        "first_seen_at": first_seen_at,
        "last_seen_at": observed_at,
        "indexed_at": observed_at,
    }
    identity_fields = ("mode", "device", "inode", "modified_ns", "changed_ns")
    if any(values[key] is None for key in identity_fields):
        raise MediaIndexError("scan_incomplete")
    values["cache_signature"] = _signature(_row_payload(values))
    return values


def _directory_row_values(
    directory: local_media.ValidatedLocalMediaDirectory,
    *,
    first_seen_at: datetime,
    observed_at: datetime,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "record_type": "directory",
        "media_path": directory.media_path,
        "basename": "media" if not directory.parts else directory.parts[-1],
        "parent_directory": (
            "/" if not directory.parts else PurePosixPath(directory.media_path).parent.as_posix()
        ),
        "extension": "",
        "mime_type": "",
        "size": 0,
        "sha256": "",
        "valid": True,
        "detail": "",
        "recovered": False,
        "mode": directory.mode,
        "device": directory.device,
        "inode": directory.inode,
        "modified_ns": directory.modified_ns,
        "changed_ns": directory.changed_ns,
        "directory_mapping_token": local_media.local_media_directory_mapping_token(directory),
        "directory_identity_json": local_media.local_media_directory_identity_json(directory),
        "first_seen_at": first_seen_at,
        "last_seen_at": observed_at,
        "indexed_at": observed_at,
    }
    values["cache_signature"] = _signature(_row_payload(values))
    return values


def _skip_values(skip: local_media.LocalMediaScanSkip) -> dict[str, object]:
    return {
        "path": skip.path,
        "reason": skip.reason,
        "extension": skip.extension,
        "size": skip.size,
        "device": skip.device,
        "inode": skip.inode,
        "modified_ns": skip.modified_ns,
        "changed_ns": skip.changed_ns,
    }


def _assign_state_values(state: MediaIndexState, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key != "id":
            setattr(state, key, value)


def _record_scan_failure(
    db: Session,
    *,
    scan_kind: str,
    refresh_source: str,
    attempted_at: datetime,
    duration_ms: int,
    error_code: str,
) -> None:
    try:
        db.rollback()
        with db.begin():
            state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
            if state is None:
                state = MediaIndexState(id=MEDIA_INDEX_STATE_ID)
                db.add(state)
                db.flush()
            state.stale_reason = "scan_failed"
            state.last_attempt_at = attempted_at
            state.last_scan_kind = scan_kind
            state.last_scan_result = "failed"
            state.last_scan_error = error_code[:200]
            state.duration_ms = max(duration_ms, 0)
            state.change_details_json = _encode_change_payload(
                refresh_source,
                list(_decode_change_details(state.change_details_json)),
            )
            row_signatures = tuple(
                db.scalars(select(MediaIndexEntry.cache_signature)).all()
            )
            state.snapshot_signature = _signature(
                _state_payload(_state_values(state), row_signatures)
            )
    except SQLAlchemyError:
        db.rollback()


def refresh_media_index(
    db: Session,
    *,
    full: bool,
    refresh_source: str | None = None,
) -> MediaIndexRefreshResult:
    if not _schema_available(db):
        raise MediaIndexError("schema_upgrade_required")
    scan_kind = "full" if full else "incremental"
    resolved_source = refresh_source or (
        "manual_full" if full else "manual_incremental"
    )
    if (
        resolved_source not in MEDIA_INDEX_REFRESH_SOURCES
        or (full and resolved_source != "manual_full")
        or (not full and resolved_source == "manual_full")
    ):
        raise MediaIndexError("invalid_refresh_source")
    attempted_at = _now()
    started = time.monotonic()
    old_rows = tuple(db.scalars(select(MediaIndexEntry)).all())
    old_paths = {
        row.media_path for row in old_rows if row.record_type == "media"
    }
    trusted_media = _trusted_old_media_rows(old_rows)
    cached_entries = {path: row.entry for path, row in trusted_media.items()}
    trusted_directories = {
        row.media_path: row.first_seen_at
        for row in old_rows
        if row.record_type == "directory" and _row_is_signed(row)
    }
    db.rollback()
    try:
        observed = local_media.scan_local_media_incremental(
            cached_entries,
            force_rehash=full,
        )
        if not observed.root_identity:
            raise MediaIndexError("storage_unavailable")
        directories = local_media.scan_local_media_directories()
        if (
            not directories
            or local_media.local_media_directory_mapping_token(directories[0])
            != observed.root_identity
        ):
            raise MediaIndexError("media_root_changed")
        directories_by_path = {directory.media_path: directory for directory in directories}
        for entry in observed.scan.entries:
            parent = PurePosixPath(entry.media_path).parent.as_posix()
            directory = directories_by_path.get(parent)
            if (
                directory is None
                or local_media.local_media_directory_mapping_token(directory)
                != entry.directory_mapping_token
            ):
                raise MediaIndexError("parent_mapping_changed")

        observed_at = _now()
        current_by_path = {entry.media_path: entry for entry in observed.scan.entries}
        current_paths = set(current_by_path)
        new_paths = current_paths - old_paths
        removed_paths = old_paths - current_paths
        changed_paths = {
            path
            for path in current_paths & old_paths
            if path not in trusted_media
            or _entry_change_key(current_by_path[path])
            != _entry_change_key(trusted_media[path].entry)
        }
        change_details = [
            *({"change": "new", "path": path} for path in sorted(new_paths)),
            *({"change": "changed", "path": path} for path in sorted(changed_paths)),
            *({"change": "removed", "path": path} for path in sorted(removed_paths)),
        ][:200]

        media_values = [
            _media_row_values(
                entry,
                first_seen_at=(
                    trusted_media[entry.media_path].first_seen_at
                    if entry.media_path in trusted_media
                    else observed_at
                ),
                observed_at=observed_at,
            )
            for entry in observed.scan.entries
        ]
        directory_values = [
            _directory_row_values(
                directory,
                first_seen_at=(
                    trusted_directories[directory.media_path]
                    if directory.media_path in trusted_directories
                    else observed_at
                ),
                observed_at=observed_at,
            )
            for directory in directories
        ]
        all_values = [*media_values, *directory_values]
        row_signatures = tuple(value["cache_signature"] for value in all_values)
        existing_state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
        duration_ms = max(int((time.monotonic() - started) * 1000), 0)
        state_values: dict[str, Any] = {
            "id": MEDIA_INDEX_STATE_ID,
            "index_format_version": MEDIA_INDEX_FORMAT_VERSION,
            "valid": True,
            "stale_reason": "",
            "current_media_root_identity": observed.root_identity,
            "last_incremental_scan_at": (
                observed_at
                if not full
                else (
                    existing_state.last_incremental_scan_at
                    if existing_state is not None
                    else None
                )
            ),
            "last_full_verification_at": (
                observed_at
                if full
                else (
                    existing_state.last_full_verification_at
                    if existing_state is not None
                    else None
                )
            ),
            "last_attempt_at": attempted_at,
            "last_success_at": observed_at,
            "last_scan_kind": scan_kind,
            "last_scan_result": "success",
            "last_scan_error": "",
            "duration_ms": duration_ms,
            "entry_count": len(observed.scan.entries),
            "valid_count": sum(entry.available for entry in observed.scan.entries),
            "damaged_count": sum(not entry.available for entry in observed.scan.entries),
            "recovered_count": sum(
                entry.is_recovered for entry in observed.scan.entries
            ),
            "skipped_count": len(observed.scan.skipped_entries),
            "reused_count": len(observed.reused_paths),
            "new_count": len(new_paths),
            "changed_count": len(changed_paths),
            "removed_count": len(removed_paths),
            "rehashed_count": len(observed.rehashed_paths),
            "change_details_json": _encode_change_payload(
                resolved_source,
                change_details,
            ),
            "skipped_details_json": json.dumps(
                [_skip_values(skip) for skip in observed.scan.skipped_entries],
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        }
        state_values["snapshot_signature"] = _signature(
            _state_payload(state_values, row_signatures)
        )

        db.rollback()
        with db.begin():
            db.execute(delete(MediaIndexEntry))
            if all_values:
                db.execute(insert(MediaIndexEntry), all_values)
            state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
            if state is None:
                state = MediaIndexState(id=MEDIA_INDEX_STATE_ID)
                db.add(state)
            _assign_state_values(state, state_values)
    except MediaIndexError as exc:
        duration_ms = max(int((time.monotonic() - started) * 1000), 0)
        _record_scan_failure(
            db,
            scan_kind=scan_kind,
            refresh_source=resolved_source,
            attempted_at=attempted_at,
            duration_ms=duration_ms,
            error_code=exc.code,
        )
        raise
    except (OSError, SQLAlchemyError, local_media.LocalMediaPathError):
        duration_ms = max(int((time.monotonic() - started) * 1000), 0)
        _record_scan_failure(
            db,
            scan_kind=scan_kind,
            refresh_source=resolved_source,
            attempted_at=attempted_at,
            duration_ms=duration_ms,
            error_code="scan_failed",
        )
        raise MediaIndexError("scan_failed") from None
    except Exception:
        duration_ms = max(int((time.monotonic() - started) * 1000), 0)
        _record_scan_failure(
            db,
            scan_kind=scan_kind,
            refresh_source=resolved_source,
            attempted_at=attempted_at,
            duration_ms=duration_ms,
            error_code="scan_failed",
        )
        raise MediaIndexError("scan_failed") from None

    snapshot = _load_index_snapshot(db)
    if snapshot is None:
        raise MediaIndexError("commit_failed")
    return MediaIndexRefreshResult(snapshot.status, snapshot.scan, snapshot.directories)


def invalidate_media_index(db: Session, *, reason: str) -> None:
    if not _schema_available(db):
        return
    state = db.get(MediaIndexState, MEDIA_INDEX_STATE_ID)
    if state is None:
        state = MediaIndexState(id=MEDIA_INDEX_STATE_ID)
        db.add(state)
        db.flush()
    state.valid = False
    state.stale_reason = reason[:64]
    row_signatures = tuple(db.scalars(select(MediaIndexEntry.cache_signature)).all())
    state.snapshot_signature = _signature(
        _state_payload(_state_values(state), row_signatures)
    )
