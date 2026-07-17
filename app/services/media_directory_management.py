from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.media_operation_token import (
    MediaOperationTokenError,
    decode_media_operation_token,
    encode_media_operation_token,
)


DIRECTORY_OPERATION_TOKEN_VERSION = 2
DIRECTORY_OPERATION_PURPOSE = "media-directory"
RENAME_NOREPLACE = 1
MAX_DIRECTORY_MANIFEST_DIRECTORIES = 256
MAX_DIRECTORY_MANIFEST_FILES = 5_000
MAX_DIRECTORY_MANIFEST_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_DIRECTORY_MANIFEST_FILE_BYTES = local_media.MAX_MEDIA_UPLOAD_BYTES
MAX_DIRECTORY_MANIFEST_DEPTH = 32
DIRECTORY_MANIFEST_READ_CHUNK_BYTES = 64 * 1024


class MediaDirectoryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MediaDirectoryOutcomeError(RuntimeError):
    def __init__(self, code: str, *, outcome: str) -> None:
        self.code = code
        self.outcome = outcome
        super().__init__(code)


@dataclass(frozen=True)
class DirectoryIdentity:
    mode: int
    device: int
    inode: int


@dataclass(frozen=True)
class DirectoryManifest:
    directories: int
    files: int
    total_size: int
    digest: str
    clean: bool = True


@dataclass(frozen=True)
class ReferenceMove:
    object_id: int
    old_path: str
    new_path: str


@dataclass(frozen=True)
class MediaDirectorySnapshot:
    operation: Literal["create", "rename", "move", "delete"]
    source_path: str | None
    source_parent_path: str | None
    target_parent_path: str
    target_basename: str
    source_identity: DirectoryIdentity | None
    source_parent_identity: DirectoryIdentity | None
    source_parent_mapping: str | None
    target_parent_identity: DirectoryIdentity
    target_parent_mapping: str
    target_exists: bool
    manifest: DirectoryManifest | None
    item_references: tuple[ReferenceMove, ...]
    creator_references: tuple[ReferenceMove, ...]
    item_reference_digest: str
    creator_reference_digest: str


@dataclass(frozen=True)
class DirectoryMutationResult:
    outcome: str
    source_path: str | None
    target_path: str
    changed: bool
    warning_code: str | None = None


def _identity(record: local_media.ValidatedLocalMediaDirectory) -> DirectoryIdentity:
    return DirectoryIdentity(stat.S_IFMT(record.mode), record.device, record.inode)


def _identity_payload(value: DirectoryIdentity | None) -> list[int] | None:
    return None if value is None else [value.mode, value.device, value.inode]


def _identity_from_payload(value: object) -> DirectoryIdentity | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 3:
        raise MediaDirectoryError("invalid_snapshot")
    try:
        return DirectoryIdentity(*(int(item) for item in value))
    except (TypeError, ValueError) as exc:
        raise MediaDirectoryError("invalid_snapshot") from exc


def _reference_payload(rows: tuple[ReferenceMove, ...]) -> list[list[object]]:
    return [[row.object_id, row.old_path, row.new_path] for row in rows]


def _references_from_payload(value: object) -> tuple[ReferenceMove, ...]:
    if not isinstance(value, list):
        raise MediaDirectoryError("invalid_snapshot")
    try:
        rows = tuple(
            ReferenceMove(int(row[0]), str(row[1]), str(row[2]))
            for row in value
            if isinstance(row, list) and len(row) == 3
        )
    except (TypeError, ValueError) as exc:
        raise MediaDirectoryError("invalid_snapshot") from exc
    if len(rows) != len(value) or len({row.object_id for row in rows}) != len(rows):
        raise MediaDirectoryError("invalid_snapshot")
    return rows


def _parent_path(record: local_media.ValidatedLocalMediaDirectory) -> str:
    if not record.parts:
        raise MediaDirectoryError("protected_media_root")
    return "/media" if len(record.parts) == 1 else f"/media/{PurePosixPath(*record.parts[:-1]).as_posix()}"


def _basename(value: str | None) -> str:
    if value is None:
        raise MediaDirectoryError("invalid_basename")
    value = value.strip()
    if (
        not value or value in {".", ".."} or "/" in value or "\\" in value
        or "%" in value or value.startswith(".")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or len(value.encode("utf-8")) > 255
        or value.casefold().startswith((
            local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX.casefold(),
            local_media.LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX.casefold(),
        ))
    ):
        raise MediaDirectoryError("invalid_basename")
    return value


def _target_path(parent: str, basename: str) -> str:
    return f"/media/{basename}" if parent == "/media" else f"{parent}/{basename}"


def _stat_matches_file(first: os.stat_result, current: os.stat_result) -> bool:
    return (
        stat.S_ISREG(first.st_mode) and stat.S_ISREG(current.st_mode)
        and stat.S_IFMT(first.st_mode) == stat.S_IFMT(current.st_mode)
        and first.st_dev == current.st_dev and first.st_ino == current.st_ino
        and first.st_size == current.st_size
        and first.st_mtime_ns == current.st_mtime_ns
        and first.st_ctime_ns == current.st_ctime_ns
    )


def _reserved_name(name: str) -> bool:
    folded = name.casefold()
    return (
        name.startswith(".")
        or folded.startswith(local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX.casefold())
        or folded.startswith(local_media.LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX.casefold())
    )


def _reserved_path(record: local_media.ValidatedLocalMediaDirectory) -> bool:
    return any(_reserved_name(part) for part in record.parts)


def _raise_limit(code: str) -> None:
    raise MediaDirectoryError(code)


def _manifest(root: local_media.ValidatedLocalMediaDirectory) -> DirectoryManifest:
    records: list[tuple[object, ...]] = []
    directories = 0
    files = 0
    total_size = 0

    def walk(relative_parent: str, directory_fd: int, depth: int) -> None:
        nonlocal directories, files, total_size
        if depth > MAX_DIRECTORY_MANIFEST_DEPTH:
            _raise_limit("directory_depth_limit")
        directories += 1
        if directories > MAX_DIRECTORY_MANIFEST_DIRECTORIES:
            _raise_limit("directory_count_limit")
        try:
            with os.scandir(directory_fd) as iterator:
                names = sorted(entry.name for entry in iterator)
        except OSError as exc:
            raise MediaDirectoryError("directory_unreadable") from exc
        for name in names:
            relative = f"{relative_parent}/{name}" if relative_parent else name
            if _reserved_name(name):
                raise MediaDirectoryError("reserved_directory_entry")
            try:
                initial = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise MediaDirectoryError("entry_error") from exc
            if stat.S_ISLNK(initial.st_mode):
                raise MediaDirectoryError("symlink_not_allowed")
            if stat.S_ISDIR(initial.st_mode):
                try:
                    child_fd = os.open(name, local_media._scan_directory_flags(), dir_fd=directory_fd)
                except OSError as exc:
                    raise MediaDirectoryError("directory_unreadable") from exc
                try:
                    opened = os.fstat(child_fd)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or stat.S_IFMT(initial.st_mode) != stat.S_IFMT(opened.st_mode)
                        or initial.st_dev != opened.st_dev
                        or initial.st_ino != opened.st_ino
                    ):
                        raise MediaDirectoryError("directory_changed")
                    records.append(("d", relative, stat.S_IFMT(opened.st_mode), opened.st_dev, opened.st_ino))
                    walk(relative, child_fd, depth + 1)
                    after = os.fstat(child_fd)
                    if opened.st_dev != after.st_dev or opened.st_ino != after.st_ino:
                        raise MediaDirectoryError("directory_changed")
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(initial.st_mode):
                raise MediaDirectoryError("special_file_not_allowed")
            if PurePosixPath(name).suffix.casefold() not in local_media.ALLOWED_MEDIA_EXTENSIONS:
                raise MediaDirectoryError("unsupported_file")
            if initial.st_size > MAX_DIRECTORY_MANIFEST_FILE_BYTES:
                _raise_limit("single_file_size_limit")
            files += 1
            total_size += initial.st_size
            if files > MAX_DIRECTORY_MANIFEST_FILES:
                _raise_limit("media_file_count_limit")
            if total_size > MAX_DIRECTORY_MANIFEST_TOTAL_BYTES:
                _raise_limit("media_total_size_limit")
            try:
                file_fd = os.open(name, local_media._scan_file_flags(), dir_fd=directory_fd)
            except OSError as exc:
                raise MediaDirectoryError("entry_error") from exc
            try:
                opened = os.fstat(file_fd)
                if not _stat_matches_file(initial, opened):
                    raise MediaDirectoryError("file_changed")
                digest = hashlib.sha256()
                chunks: list[bytes] = []
                bytes_read = 0
                while True:
                    chunk = os.read(file_fd, DIRECTORY_MANIFEST_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    if bytes_read > MAX_DIRECTORY_MANIFEST_FILE_BYTES or bytes_read > initial.st_size:
                        _raise_limit("single_file_size_limit")
                    digest.update(chunk)
                    chunks.append(chunk)
                after = os.fstat(file_fd)
                if bytes_read != initial.st_size or not _stat_matches_file(initial, after):
                    raise MediaDirectoryError("file_changed")
                try:
                    local_media._validated_image_format(
                        b"".join(chunks), PurePosixPath(name).suffix.casefold()
                    )
                except local_media.LocalMediaUploadError as exc:
                    raise MediaDirectoryError("damaged_media") from exc
                records.append((
                    "f", relative, initial.st_size, stat.S_IFMT(initial.st_mode),
                    initial.st_dev, initial.st_ino, initial.st_mtime_ns,
                    initial.st_ctime_ns, digest.hexdigest(),
                ))
            finally:
                os.close(file_fd)

    root_fds = local_media._open_validated_directory(root)
    try:
        walk("", root_fds[-1], 0)
        local_media._verify_open_validated_directory(root, root_fds)
    except local_media._MediaScanCandidateChanged as exc:
        raise MediaDirectoryError("directory_changed") from exc
    finally:
        local_media._close_scan_descriptors(root_fds, None)
    refreshed = local_media.validate_local_media_directory(root.media_path)
    if (
        _identity(refreshed) != _identity(root)
        or local_media.local_media_directory_mapping_token(refreshed)
        != local_media.local_media_directory_mapping_token(root)
    ):
        raise MediaDirectoryError("directory_changed")
    digest = hashlib.sha256(
        json.dumps(records, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return DirectoryManifest(directories, files, total_size, digest, True)


def _reference_digest(rows: tuple[ReferenceMove, ...]) -> str:
    return hashlib.sha256(
        json.dumps(_reference_payload(rows), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _references(db: Session, source: str, target: str) -> tuple[tuple[ReferenceMove, ...], tuple[ReferenceMove, ...]]:
    items = tuple(
        ReferenceMove(int(object_id), path, target + path[len(source):])
        for object_id, path in db.execute(
            select(Item.id, Item.cover_path).where(Item.cover_path.is_not(None))
        ).all()
        if path == source or path.startswith(source + "/")
    )
    creators = tuple(
        ReferenceMove(int(object_id), path, target + path[len(source):])
        for object_id, path in db.execute(
            select(Creator.id, Creator.avatar_path).where(Creator.avatar_path.is_not(None))
        ).all()
        if path == source or path.startswith(source + "/")
    )
    return items, creators


def _encode(snapshot: MediaDirectorySnapshot) -> str:
    payload = {
        "format_version": DIRECTORY_OPERATION_TOKEN_VERSION,
        "purpose": DIRECTORY_OPERATION_PURPOSE,
        "operation": snapshot.operation,
        "source_path": snapshot.source_path,
        "source_parent_path": snapshot.source_parent_path,
        "target_parent_path": snapshot.target_parent_path,
        "target_basename": snapshot.target_basename,
        "source_identity": _identity_payload(snapshot.source_identity),
        "source_parent_identity": _identity_payload(snapshot.source_parent_identity),
        "source_parent_mapping": snapshot.source_parent_mapping,
        "target_parent_identity": _identity_payload(snapshot.target_parent_identity),
        "target_parent_mapping": snapshot.target_parent_mapping,
        "target_exists": snapshot.target_exists,
        "manifest": None if snapshot.manifest is None else snapshot.manifest.__dict__,
        "item_references": _reference_payload(snapshot.item_references),
        "creator_references": _reference_payload(snapshot.creator_references),
        "item_reference_digest": snapshot.item_reference_digest,
        "creator_reference_digest": snapshot.creator_reference_digest,
    }
    return encode_media_operation_token(payload, get_settings().secret_key)


def _decode(token: str) -> MediaDirectorySnapshot:
    try:
        payload = decode_media_operation_token(token, get_settings().secret_key)
        if (
            payload.get("format_version") != DIRECTORY_OPERATION_TOKEN_VERSION
            or payload.get("purpose") != DIRECTORY_OPERATION_PURPOSE
        ):
            raise ValueError
        manifest_raw = payload.get("manifest")
        manifest = None if manifest_raw is None else DirectoryManifest(**manifest_raw)
        item_refs = _references_from_payload(payload.get("item_references"))
        creator_refs = _references_from_payload(payload.get("creator_references"))
        snapshot = MediaDirectorySnapshot(
            operation=payload["operation"],
            source_path=payload.get("source_path"),
            source_parent_path=payload.get("source_parent_path"),
            target_parent_path=payload["target_parent_path"],
            target_basename=payload["target_basename"],
            source_identity=_identity_from_payload(payload.get("source_identity")),
            source_parent_identity=_identity_from_payload(payload.get("source_parent_identity")),
            source_parent_mapping=payload.get("source_parent_mapping"),
            target_parent_identity=_identity_from_payload(payload.get("target_parent_identity")),
            target_parent_mapping=payload["target_parent_mapping"],
            target_exists=bool(payload["target_exists"]), manifest=manifest,
            item_references=item_refs, creator_references=creator_refs,
            item_reference_digest=payload["item_reference_digest"],
            creator_reference_digest=payload["creator_reference_digest"],
        )
        if (
            snapshot.target_parent_identity is None
            or _reference_digest(item_refs) != snapshot.item_reference_digest
            or _reference_digest(creator_refs) != snapshot.creator_reference_digest
        ):
            raise ValueError
        return snapshot
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, MediaOperationTokenError) as exc:
        raise MediaDirectoryError("invalid_snapshot") from exc


def build_directory_snapshot(
    db: Session, *, operation: str, source_path: str | None,
    target_parent_path: str, target_basename: str,
) -> tuple[MediaDirectorySnapshot, str]:
    if operation not in {"create", "rename", "move", "delete"}:
        raise MediaDirectoryError("invalid_operation")
    target_parent = local_media.validate_local_media_directory(target_parent_path)
    if target_parent.media_path == "/media":
        raise MediaDirectoryError("protected_media_root")
    if _reserved_path(target_parent):
        raise MediaDirectoryError("reserved_directory_entry")
    target_basename = _basename(target_basename)
    target = _target_path(target_parent.media_path, target_basename)
    target_exists = False
    if operation != "delete":
        target_fds = local_media._open_validated_directory(target_parent)
        try:
            os.stat(target_basename, dir_fd=target_fds[-1], follow_symlinks=False)
            target_exists = True
        except FileNotFoundError:
            pass
        except OSError:
            target_exists = True
        finally:
            local_media._close_scan_descriptors(target_fds, None)
    if target_exists:
        raise MediaDirectoryError("target_exists")
    source = source_parent = None
    manifest = None
    item_refs: tuple[ReferenceMove, ...] = ()
    creator_refs: tuple[ReferenceMove, ...] = ()
    if source_path is not None:
        source = local_media.validate_local_media_directory(source_path)
        if source.media_path in {"/media", "/media/library"}:
            raise MediaDirectoryError("protected_directory")
        if _reserved_path(source):
            raise MediaDirectoryError("reserved_directory_entry")
        source_parent = local_media.validate_local_media_directory(_parent_path(source))
        if operation in {"rename", "move"} and (
            target_parent.device != source.device
            or target_parent.parts[: len(source.parts)] == source.parts
        ):
            raise MediaDirectoryError("invalid_target_directory")
        manifest = _manifest(source)
        refreshed_source_parent = local_media.validate_local_media_directory(_parent_path(source))
        if (
            _identity(refreshed_source_parent) != _identity(source_parent)
            or local_media.local_media_directory_mapping_token(refreshed_source_parent)
            != local_media.local_media_directory_mapping_token(source_parent)
        ):
            raise MediaDirectoryError("directory_changed")
        refreshed_target_parent = local_media.validate_local_media_directory(target_parent.media_path)
        if (
            _identity(refreshed_target_parent) != _identity(target_parent)
            or local_media.local_media_directory_mapping_token(refreshed_target_parent)
            != local_media.local_media_directory_mapping_token(target_parent)
        ):
            raise MediaDirectoryError("directory_changed")
        if operation == "delete" and (manifest.files or manifest.directories > 1):
            raise MediaDirectoryError("directory_not_empty")
        item_refs, creator_refs = _references(db, source.media_path, target)
        if operation == "delete" and (item_refs or creator_refs):
            raise MediaDirectoryError("directory_referenced")
    snapshot = MediaDirectorySnapshot(
        operation=operation, source_path=source_path,
        source_parent_path=None if source_parent is None else source_parent.media_path,
        target_parent_path=target_parent.media_path, target_basename=target_basename,
        source_identity=None if source is None else _identity(source),
        source_parent_identity=None if source_parent is None else _identity(source_parent),
        source_parent_mapping=None if source_parent is None else local_media.local_media_directory_mapping_token(source_parent),
        target_parent_identity=_identity(target_parent),
        target_parent_mapping=local_media.local_media_directory_mapping_token(target_parent),
        target_exists=target_exists, manifest=manifest,
        item_references=item_refs, creator_references=creator_refs,
        item_reference_digest=_reference_digest(item_refs),
        creator_reference_digest=_reference_digest(creator_refs),
    )
    return snapshot, _encode(snapshot)


def _rename_noreplace(source_fd: int, source_name: str, target_fd: int, target_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise MediaDirectoryError("no_overwrite_unsupported")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(source_fd, source_name.encode(), target_fd, target_name.encode(), RENAME_NOREPLACE) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise MediaDirectoryError("target_exists")
        raise OSError(error, os.strerror(error))


def _compare_snapshot(expected: MediaDirectorySnapshot, actual: MediaDirectorySnapshot) -> None:
    if expected != actual:
        raise MediaDirectoryError("stale_preview")


def _update_exact_references(db: Session, snapshot: MediaDirectorySnapshot) -> None:
    for row in snapshot.item_references:
        item = db.get(Item, row.object_id)
        if item is None or item.cover_path != row.old_path:
            raise MediaDirectoryError("stale_preview")
        item.cover_path = row.new_path
    for row in snapshot.creator_references:
        creator = db.get(Creator, row.object_id)
        if creator is None or creator.avatar_path != row.old_path:
            raise MediaDirectoryError("stale_preview")
        creator.avatar_path = row.new_path


def _path_state(path: str, identity: DirectoryIdentity, manifest: DirectoryManifest) -> bool:
    try:
        record = local_media.validate_local_media_directory(path)
        return _identity(record) == identity and _manifest(record) == manifest
    except (MediaDirectoryError, local_media.LocalMediaPathError, OSError):
        return False


def _path_missing(path: str) -> bool:
    try:
        local_media.validate_local_media_directory(path)
    except local_media.LocalMediaPathError:
        return True
    return False


def _independent_outcome(snapshot: MediaDirectorySnapshot, target: str) -> str:
    if snapshot.source_path is None or snapshot.source_identity is None or snapshot.manifest is None:
        return "directory_outcome_unknown"
    try:
        with SessionLocal() as verification_db:
            actual_items = {
                row.object_id: verification_db.get(Item, row.object_id).cover_path
                if verification_db.get(Item, row.object_id) is not None else None
                for row in snapshot.item_references
            }
            actual_creators = {
                row.object_id: verification_db.get(Creator, row.object_id).avatar_path
                if verification_db.get(Creator, row.object_id) is not None else None
                for row in snapshot.creator_references
            }
            all_paths = [
                ("item", int(row[0]), str(row[1]))
                for row in verification_db.execute(
                    select(Item.id, Item.cover_path).where(Item.cover_path.is_not(None))
                ).all()
            ] + [
                ("creator", int(row[0]), str(row[1]))
                for row in verification_db.execute(
                    select(Creator.id, Creator.avatar_path).where(Creator.avatar_path.is_not(None))
                ).all()
            ]
    except Exception:
        return "directory_outcome_unknown"
    expected_keys = {
        *(('item', row.object_id) for row in snapshot.item_references),
        *(('creator', row.object_id) for row in snapshot.creator_references),
    }
    unexpected = {
        (kind, object_id)
        for kind, object_id, path in all_paths
        if (path == snapshot.source_path or path.startswith(snapshot.source_path + "/")
            or path == target or path.startswith(target + "/"))
        and (kind, object_id) not in expected_keys
    }
    if unexpected:
        return "directory_outcome_unknown"
    items_source = all(actual_items[row.object_id] == row.old_path for row in snapshot.item_references)
    items_target = all(actual_items[row.object_id] == row.new_path for row in snapshot.item_references)
    creators_source = all(actual_creators[row.object_id] == row.old_path for row in snapshot.creator_references)
    creators_target = all(actual_creators[row.object_id] == row.new_path for row in snapshot.creator_references)
    source_ok = _path_state(snapshot.source_path, snapshot.source_identity, snapshot.manifest)
    target_ok = _path_state(target, snapshot.source_identity, snapshot.manifest)
    source_missing = _path_missing(snapshot.source_path)
    target_missing = _path_missing(target)
    if items_target and creators_target and target_ok and source_missing:
        return "committed_after_error"
    if items_source and creators_source and (
        (target_ok and source_missing) or (source_ok and target_missing)
    ):
        return "not_committed"
    return "directory_outcome_unknown"


def _final_snapshot(db: Session, snapshot: MediaDirectorySnapshot) -> MediaDirectorySnapshot:
    fresh, _ = build_directory_snapshot(
        db, operation=snapshot.operation, source_path=snapshot.source_path,
        target_parent_path=snapshot.target_parent_path,
        target_basename=snapshot.target_basename,
    )
    _compare_snapshot(snapshot, fresh)
    return fresh


def execute_directory_mutation(
    db: Session, *, token: str, confirmation: str | None = None,
) -> DirectoryMutationResult:
    snapshot = _decode(token)
    if confirmation != snapshot.operation:
        raise MediaDirectoryError("confirmation_required")
    target = _target_path(snapshot.target_parent_path, snapshot.target_basename)
    if snapshot.operation == "create":
        fresh = _final_snapshot(db, snapshot)
        target_parent = local_media.validate_local_media_directory(fresh.target_parent_path)
        parent_fds = local_media._open_validated_directory(target_parent)
        try:
            os.mkdir(fresh.target_basename, 0o700, dir_fd=parent_fds[-1])
            created_fd = os.open(fresh.target_basename, local_media._scan_directory_flags(), dir_fd=parent_fds[-1])
            try:
                os.fsync(created_fd)
                os.fsync(parent_fds[-1])
            except OSError as exc:
                raise MediaDirectoryOutcomeError(
                    "directory_sync_failed", outcome="filesystem_changed_partial_known"
                ) from exc
            finally:
                os.close(created_fd)
        finally:
            local_media._close_scan_descriptors(parent_fds, None)
        return DirectoryMutationResult("committed", None, target, True)

    db.execute(text("BEGIN IMMEDIATE"))
    try:
        fresh = _final_snapshot(db, snapshot)
    except Exception:
        db.rollback()
        raise
    assert fresh.source_path is not None and fresh.source_parent_path is not None
    assert fresh.source_identity is not None and fresh.manifest is not None
    source = local_media.validate_local_media_directory(fresh.source_path)
    source_parent = local_media.validate_local_media_directory(fresh.source_parent_path)
    target_parent = local_media.validate_local_media_directory(fresh.target_parent_path)

    if fresh.operation == "delete":
        parent_fds = local_media._open_validated_directory(source_parent)
        try:
            os.rmdir(source.parts[-1], dir_fd=parent_fds[-1])
            db.commit()
            try:
                os.fsync(parent_fds[-1])
            except OSError as exc:
                raise MediaDirectoryOutcomeError(
                    "directory_sync_failed", outcome="filesystem_changed_partial_known"
                ) from exc
        except MediaDirectoryOutcomeError:
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            local_media._close_scan_descriptors(parent_fds, None)
        return DirectoryMutationResult("committed", fresh.source_path, target, True)

    source_fds = local_media._open_validated_directory(source_parent)
    target_fds = local_media._open_validated_directory(target_parent)
    try:
        try:
            _rename_noreplace(source_fds[-1], source.parts[-1], target_fds[-1], fresh.target_basename)
        except Exception:
            db.rollback()
            raise
        try:
            _update_exact_references(db, fresh)
            db.commit()
        except Exception as commit_error:
            db.rollback()
            outcome = _independent_outcome(fresh, target)
            if outcome == "committed_after_error":
                return DirectoryMutationResult(
                    "committed_after_error", fresh.source_path, target, True,
                    "committed_after_error",
                )
            if outcome == "not_committed":
                try:
                    _rename_noreplace(target_fds[-1], fresh.target_basename, source_fds[-1], source.parts[-1])
                    os.fsync(source_fds[-1])
                    if source_fds[-1] != target_fds[-1]:
                        os.fsync(target_fds[-1])
                except Exception as rollback_error:
                    raise MediaDirectoryOutcomeError(
                        "rollback_failed", outcome="directory_outcome_unknown"
                    ) from rollback_error
                raise MediaDirectoryOutcomeError(
                    "not_committed_rolled_back", outcome="not_committed_rolled_back"
                ) from commit_error
            raise MediaDirectoryOutcomeError(
                "directory_outcome_unknown", outcome="directory_outcome_unknown"
            ) from commit_error
        try:
            os.fsync(source_fds[-1])
            os.fsync(target_fds[-1])
        except OSError as exc:
            raise MediaDirectoryOutcomeError(
                "directory_sync_failed", outcome="filesystem_changed_partial_known"
            ) from exc
    finally:
        local_media._close_scan_descriptors(source_fds, None)
        local_media._close_scan_descriptors(target_fds, None)
    return DirectoryMutationResult("committed", fresh.source_path, target, True)


def classify_directory_result(result: DirectoryMutationResult) -> str:
    if result.outcome in {"committed", "committed_after_error"}:
        return "filesystem_changed_known"
    if result.outcome == "filesystem_changed_partial_known":
        return "filesystem_changed_partial_known"
    if result.outcome == "not_committed_rolled_back":
        return "no_filesystem_change"
    return "directory_outcome_unknown"
