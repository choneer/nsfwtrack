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


DIRECTORY_OPERATION_TOKEN_VERSION = 1
DIRECTORY_OPERATION_PURPOSE = "media-directory"
RENAME_NOREPLACE = 1


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
    clean: bool


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
    item_reference_digest: str
    creator_reference_digest: str


@dataclass(frozen=True)
class DirectoryMutationResult:
    outcome: str
    source_path: str | None
    target_path: str
    changed: bool


def _identity(record: local_media.ValidatedLocalMediaDirectory) -> DirectoryIdentity:
    return DirectoryIdentity(
        mode=stat.S_IFMT(record.mode),
        device=record.device,
        inode=record.inode,
    )


def _identity_payload(value: DirectoryIdentity | None) -> list[int] | None:
    return None if value is None else [value.mode, value.device, value.inode]


def _identity_from_payload(value: object) -> DirectoryIdentity | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 3:
        raise MediaDirectoryError("invalid_snapshot")
    try:
        mode, device, inode = (int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise MediaDirectoryError("invalid_snapshot") from exc
    return DirectoryIdentity(mode, device, inode)


def _parent_path(record: local_media.ValidatedLocalMediaDirectory) -> str:
    if not record.parts:
        raise MediaDirectoryError("protected_media_root")
    parts = record.parts[:-1]
    return "/media" if not parts else f"/media/{PurePosixPath(*parts).as_posix()}"


def _basename(value: str | None) -> str:
    if value is None:
        raise MediaDirectoryError("invalid_basename")
    value = value.strip()
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "%" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.startswith(".")
        or len(value.encode("utf-8")) > 255
        or value.casefold().startswith(
            (local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX.casefold(),
             local_media.LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX.casefold())
        )
    ):
        raise MediaDirectoryError("invalid_basename")
    return value


def _target_path(parent: str, basename: str) -> str:
    return f"{parent.rstrip('/')}/{basename}" if parent != "/media" else f"/media/{basename}"


def _reference_digest(values: list[tuple[int, str | None]]) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _references(db: Session, prefix: str) -> tuple[str, str]:
    item_rows = [
        (int(row[0]), str(row[1]))
        for row in db.execute(
            select(Item.id, Item.cover_path).where(Item.cover_path.is_not(None))
        ).all()
        if str(row[1]) == prefix or str(row[1]).startswith(prefix + "/")
    ]
    creator_rows = [
        (int(row[0]), str(row[1]))
        for row in db.execute(
            select(Creator.id, Creator.avatar_path).where(Creator.avatar_path.is_not(None))
        ).all()
        if str(row[1]) == prefix or str(row[1]).startswith(prefix + "/")
    ]
    return _reference_digest(item_rows), _reference_digest(creator_rows)


def _manifest(root: local_media.ValidatedLocalMediaDirectory) -> DirectoryManifest:
    records: list[tuple[str, int, int, int, str]] = []
    directories = 0
    files = 0
    total_size = 0
    clean = True

    def walk(path: str, fd: int) -> None:
        nonlocal directories, files, total_size, clean
        directories += 1
        try:
            entries = sorted(os.scandir(fd), key=lambda item: (item.name.casefold(), item.name))
        except OSError as exc:
            raise MediaDirectoryError("directory_unreadable") from exc
        for entry in entries:
            try:
                entry_stat = entry.stat(follow_symlinks=False)
                mode = entry_stat.st_mode
                relative = f"{path}/{entry.name}" if path else entry.name
                if stat.S_ISDIR(mode):
                    records.append((relative, -1, entry_stat.st_dev, entry_stat.st_ino, "directory"))
                    child_fd = os.open(entry.name, local_media._scan_directory_flags(), dir_fd=fd)
                    try:
                        walk(relative, child_fd)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(mode):
                    extension = PurePosixPath(entry.name).suffix.casefold()
                    if extension not in local_media.ALLOWED_MEDIA_EXTENSIONS:
                        clean = False
                    else:
                        files += 1
                        total_size += entry_stat.st_size
                        content = bytearray()
                        file_fd = os.open(entry.name, local_media._scan_file_flags(), dir_fd=fd)
                        try:
                            while chunk := os.read(file_fd, 1024 * 1024):
                                content.extend(chunk)
                        finally:
                            os.close(file_fd)
                        try:
                            local_media._validated_image_format(bytes(content), extension)
                        except local_media.LocalMediaUploadError:
                            clean = False
                        records.append((
                            relative, entry_stat.st_size, entry_stat.st_dev,
                            entry_stat.st_ino, hashlib.sha256(content).hexdigest(),
                        ))
                else:
                    clean = False
            except OSError as exc:
                clean = False
                records.append((relative, -1, 0, 0, ""))

    directories_fd = local_media._open_validated_directory(root)
    try:
        walk("", directories_fd[-1])
    finally:
        local_media._close_scan_descriptors(directories_fd, None)
    digest = hashlib.sha256(
        json.dumps(records, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return DirectoryManifest(directories, files, total_size, digest, clean)


def _sign(payload: dict[str, object]) -> str:
    return encode_media_operation_token(payload, get_settings().secret_key)


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
        "item_reference_digest": snapshot.item_reference_digest,
        "creator_reference_digest": snapshot.creator_reference_digest,
    }
    return _sign(payload)


def _decode(token: str) -> MediaDirectorySnapshot:
    try:
        payload = decode_media_operation_token(token, get_settings().secret_key)
        if payload.get("format_version") != DIRECTORY_OPERATION_TOKEN_VERSION or payload.get("purpose") != DIRECTORY_OPERATION_PURPOSE:
            raise ValueError
        manifest_raw = payload.get("manifest")
        manifest = None if manifest_raw is None else DirectoryManifest(**manifest_raw)
        return MediaDirectorySnapshot(
            operation=payload["operation"], source_path=payload.get("source_path"),
            source_parent_path=payload.get("source_parent_path"), target_parent_path=payload["target_parent_path"],
            target_basename=payload["target_basename"], source_identity=_identity_from_payload(payload.get("source_identity")),
            source_parent_identity=_identity_from_payload(payload.get("source_parent_identity")),
            source_parent_mapping=payload.get("source_parent_mapping"), target_parent_identity=_identity_from_payload(payload.get("target_parent_identity")),
            target_parent_mapping=payload["target_parent_mapping"], target_exists=bool(payload["target_exists"]), manifest=manifest,
            item_reference_digest=payload["item_reference_digest"], creator_reference_digest=payload["creator_reference_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, MediaOperationTokenError) as exc:
        raise MediaDirectoryError("invalid_snapshot") from exc


def build_directory_snapshot(db: Session, *, operation: str, source_path: str | None, target_parent_path: str, target_basename: str) -> tuple[MediaDirectorySnapshot, str]:
    target_parent = local_media.validate_local_media_directory(target_parent_path)
    if target_parent.media_path == "/media":
        raise MediaDirectoryError("protected_media_root")
    target_basename = _basename(target_basename)
    target = _target_path(target_parent.media_path, target_basename)
    target_exists = False
    if operation != "delete":
        try:
            target_record = local_media.validate_local_media_directory(target)
            del target_record
            target_exists = True
        except local_media.LocalMediaPathError:
            pass
    if target_exists:
        raise MediaDirectoryError("target_exists")
    source = None
    source_parent = None
    manifest = None
    item_digest = creator_digest = hashlib.sha256(b"[]").hexdigest()
    if source_path is not None:
        source = local_media.validate_local_media_directory(source_path)
        if source.media_path in {"/media", "/media/library"}:
            raise MediaDirectoryError("protected_directory")
        source_parent = local_media.validate_local_media_directory(_parent_path(source))
        if operation in {"rename", "move"} and (
            target_parent.device != source.device
            or target_parent.parts[: len(source.parts)] == source.parts
        ):
            raise MediaDirectoryError("invalid_target_directory")
        manifest = _manifest(source)
        if operation == "delete" and (manifest.files or manifest.directories > 1):
            raise MediaDirectoryError("directory_not_empty")
        if not manifest.clean:
            raise MediaDirectoryError("unclean_directory_tree")
        item_digest, creator_digest = _references(db, source.media_path)
        empty_digest = hashlib.sha256(b"[]").hexdigest()
        if operation == "delete" and (
            item_digest != empty_digest or creator_digest != empty_digest
        ):
            raise MediaDirectoryError("directory_referenced")
    snapshot = MediaDirectorySnapshot(
        operation=operation, source_path=source_path, source_parent_path=None if source_parent is None else source_parent.media_path,
        target_parent_path=target_parent.media_path, target_basename=target_basename,
        source_identity=None if source is None else _identity(source), source_parent_identity=None if source_parent is None else _identity(source_parent),
        source_parent_mapping=None if source_parent is None else local_media.local_media_directory_mapping_token(source_parent),
        target_parent_identity=_identity(target_parent), target_parent_mapping=local_media.local_media_directory_mapping_token(target_parent),
        target_exists=target_exists, manifest=manifest, item_reference_digest=item_digest, creator_reference_digest=creator_digest,
    )
    return snapshot, _encode(snapshot)


def _rename_noreplace(source_fd: int, source_name: str, target_fd: int, target_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise MediaDirectoryError("no_overwrite_unsupported")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(source_fd, source_name.encode(), target_fd, target_name.encode(), RENAME_NOREPLACE)
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise MediaDirectoryError("target_exists")
        raise OSError(error, os.strerror(error))


def _update_references(db: Session, source: str, target: str) -> None:
    item_rows = db.scalars(select(Item).where(Item.cover_path.is_not(None))).all()
    creator_rows = db.scalars(select(Creator).where(Creator.avatar_path.is_not(None))).all()
    for item in item_rows:
        if item.cover_path == source or item.cover_path.startswith(source + "/"):
            item.cover_path = target + item.cover_path[len(source):]
    for creator in creator_rows:
        if creator.avatar_path == source or creator.avatar_path.startswith(source + "/"):
            creator.avatar_path = target + creator.avatar_path[len(source):]


def _independent_reference_state(source: str, target: str) -> str:
    try:
        with SessionLocal() as verification_db:
            values = [
                value
                for value in verification_db.scalars(
                    select(Item.cover_path).where(Item.cover_path.is_not(None))
                ).all()
            ] + [
                value
                for value in verification_db.scalars(
                    select(Creator.avatar_path).where(Creator.avatar_path.is_not(None))
                ).all()
            ]
    except Exception:
        return "unknown"
    source_count = sum(value == source or value.startswith(source + "/") for value in values)
    target_count = sum(value == target or value.startswith(target + "/") for value in values)
    if source_count and target_count:
        return "mixed"
    if target_count:
        return "target"
    if source_count:
        return "source"
    return "none"


def execute_directory_mutation(db: Session, *, token: str, confirmation: str | None = None) -> DirectoryMutationResult:
    snapshot = _decode(token)
    if confirmation != snapshot.operation:
        raise MediaDirectoryError("confirmation_required")
    fresh, _ = build_directory_snapshot(
        db,
        operation=snapshot.operation,
        source_path=snapshot.source_path,
        target_parent_path=snapshot.target_parent_path,
        target_basename=snapshot.target_basename,
    )
    if fresh != snapshot:
        raise MediaDirectoryError("stale_preview")
    target_parent = local_media.validate_local_media_directory(snapshot.target_parent_path)
    if _identity(target_parent) != snapshot.target_parent_identity or local_media.local_media_directory_mapping_token(target_parent) != snapshot.target_parent_mapping:
        raise MediaDirectoryError("stale_preview")
    target = _target_path(snapshot.target_parent_path, snapshot.target_basename)
    if snapshot.target_exists:
        raise MediaDirectoryError("target_exists")
    if snapshot.operation == "create":
        if snapshot.source_path is not None:
            raise MediaDirectoryError("invalid_snapshot")
        parent_fds = local_media._open_validated_directory(target_parent)
        try:
            try:
                os.mkdir(snapshot.target_basename, 0o700, dir_fd=parent_fds[-1])
            except FileExistsError as exc:
                raise MediaDirectoryError("target_exists") from exc
            created_fd = os.open(
                snapshot.target_basename,
                local_media._scan_directory_flags(),
                dir_fd=parent_fds[-1],
            )
            try:
                os.fsync(created_fd)
            finally:
                os.close(created_fd)
            try:
                os.fsync(parent_fds[-1])
            except OSError as exc:
                raise MediaDirectoryOutcomeError(
                    "sync_failed", outcome="filesystem_changed_partial_known"
                ) from exc
        finally:
            local_media._close_scan_descriptors(parent_fds, None)
        return DirectoryMutationResult("committed", None, target, True)
    if snapshot.source_path is None or snapshot.source_parent_path is None or snapshot.source_identity is None:
        raise MediaDirectoryError("invalid_snapshot")
    source = local_media.validate_local_media_directory(snapshot.source_path)
    source_parent = local_media.validate_local_media_directory(snapshot.source_parent_path)
    if _identity(source) != snapshot.source_identity or _identity(source_parent) != snapshot.source_parent_identity or local_media.local_media_directory_mapping_token(source_parent) != snapshot.source_parent_mapping:
        raise MediaDirectoryError("stale_preview")
    if snapshot.operation == "delete":
        if _parent_path(source) != snapshot.target_parent_path:
            raise MediaDirectoryError("invalid_snapshot")
        parent_fds = local_media._open_validated_directory(source_parent)
        try:
            os.rmdir(source.parts[-1], dir_fd=parent_fds[-1])
            try:
                os.fsync(parent_fds[-1])
            except OSError as exc:
                raise MediaDirectoryOutcomeError(
                    "sync_failed", outcome="filesystem_changed_partial_known"
                ) from exc
        finally:
            local_media._close_scan_descriptors(parent_fds, None)
        return DirectoryMutationResult("committed", snapshot.source_path, target, True)
    source_fds = local_media._open_validated_directory(source_parent)
    target_fds = local_media._open_validated_directory(target_parent)
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        try:
            _rename_noreplace(source_fds[-1], source.parts[-1], target_fds[-1], snapshot.target_basename)
        except Exception:
            db.rollback()
            raise
        try:
            _update_references(db, snapshot.source_path, target)
            db.commit()
        except Exception as exc:
            db.rollback()
            reference_state = _independent_reference_state(snapshot.source_path, target)
            if reference_state == "target" or (
                reference_state == "none"
                and snapshot.item_reference_digest == hashlib.sha256(b"[]").hexdigest()
                and snapshot.creator_reference_digest == hashlib.sha256(b"[]").hexdigest()
            ):
                return DirectoryMutationResult(
                    "committed_after_error", snapshot.source_path, target, True
                )
            if reference_state != "source":
                raise MediaDirectoryOutcomeError(
                    "mixed_or_unknown_references", outcome="directory_outcome_unknown"
                ) from exc
            try:
                _rename_noreplace(target_fds[-1], snapshot.target_basename, source_fds[-1], source.parts[-1])
            except Exception as rollback_exc:
                raise MediaDirectoryOutcomeError("rollback_failed", outcome="directory_outcome_unknown") from rollback_exc
            raise MediaDirectoryOutcomeError("not_committed_rolled_back", outcome="not_committed_rolled_back") from exc
        try:
            os.fsync(source_fds[-1])
            if target_fds[-1] != source_fds[-1]:
                os.fsync(target_fds[-1])
        except OSError as exc:
            raise MediaDirectoryOutcomeError(
                "sync_failed", outcome="filesystem_changed_partial_known"
            ) from exc
    finally:
        local_media._close_scan_descriptors(source_fds, None)
        local_media._close_scan_descriptors(target_fds, None)
    return DirectoryMutationResult("committed", snapshot.source_path, target, True)
