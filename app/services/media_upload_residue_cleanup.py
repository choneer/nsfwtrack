from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_health import audit_local_media


class MediaUploadResidueCleanupError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _ResidueDeleteError(OSError):
    def __init__(self, code: str, *, removed: bool = False) -> None:
        self.code = code
        self.removed = removed
        super().__init__(code)


@dataclass(frozen=True)
class _DirectoryIdentity:
    mode: int
    device: int
    inode: int

    @classmethod
    def from_stat(cls, directory_stat: os.stat_result) -> _DirectoryIdentity:
        return cls(
            mode=directory_stat.st_mode,
            device=directory_stat.st_dev,
            inode=directory_stat.st_ino,
        )

    def matches(self, directory_stat: os.stat_result) -> bool:
        return (
            stat.S_ISDIR(directory_stat.st_mode)
            and stat.S_IFMT(self.mode) == stat.S_IFMT(directory_stat.st_mode)
            and self.device == directory_stat.st_dev
            and self.inode == directory_stat.st_ino
        )


@dataclass(frozen=True)
class ValidatedUploadResidue:
    residue_path: str
    media_path: str
    path: Path
    directory_identities: tuple[_DirectoryIdentity, ...]
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class UploadResidueItemReference:
    id: int
    title: str
    value: str


@dataclass(frozen=True)
class UploadResidueCreatorReference:
    id: int
    name: str
    value: str


@dataclass(frozen=True)
class MediaUploadResidueCleanupPreview:
    residue: ValidatedUploadResidue
    item_references: tuple[UploadResidueItemReference, ...]
    creator_references: tuple[UploadResidueCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)


@dataclass(frozen=True)
class MediaUploadResidueCleanupResult:
    deleted_path: str
    size: int
    warning_code: str | None = None


def _normalize_residue_path(value: str | None) -> str:
    if value is None or not value or value != value.strip():
        raise MediaUploadResidueCleanupError("invalid_request")
    if (
        len(value) > 500
        or value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "%" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise MediaUploadResidueCleanupError("invalid_request")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise MediaUploadResidueCleanupError("invalid_request")
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise MediaUploadResidueCleanupError("invalid_request")
    if not local_media.is_upload_residue_filename(segments[-1]):
        raise MediaUploadResidueCleanupError("not_residue")
    return value


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _file_flags() -> int:
    flags = getattr(os, "O_PATH", os.O_RDONLY)
    if not hasattr(os, "O_PATH") and hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _close_directories(directory_descriptors: list[int]) -> None:
    for directory_descriptor in reversed(directory_descriptors):
        try:
            os.close(directory_descriptor)
        except OSError:
            pass


def _open_parent_directory(
    residue_path: str,
    *,
    expected_identities: tuple[_DirectoryIdentity, ...] | None = None,
) -> tuple[list[int], str, tuple[_DirectoryIdentity, ...]]:
    segments = residue_path.split("/")
    directory_descriptors: list[int] = []
    identities: list[_DirectoryIdentity] = []
    try:
        directory_fd = os.open(local_media.LOCAL_MEDIA_ROOT, _directory_flags())
    except FileNotFoundError as exc:
        raise MediaUploadResidueCleanupError("storage_unavailable") from exc
    except OSError as exc:
        raise MediaUploadResidueCleanupError("storage_unavailable") from exc
    directory_descriptors.append(directory_fd)
    try:
        root_stat = os.fstat(directory_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise MediaUploadResidueCleanupError("storage_unavailable")
        identities.append(_DirectoryIdentity.from_stat(root_stat))
        if expected_identities is not None and (
            not expected_identities
            or not expected_identities[0].matches(root_stat)
        ):
            raise MediaUploadResidueCleanupError("residue_invalid")
        for index, segment in enumerate(segments[:-1], start=1):
            try:
                next_fd = os.open(
                    segment,
                    _directory_flags(),
                    dir_fd=directory_descriptors[-1],
                )
            except FileNotFoundError as exc:
                raise MediaUploadResidueCleanupError("residue_not_found") from exc
            except OSError as exc:
                raise MediaUploadResidueCleanupError("residue_invalid") from exc
            directory_descriptors.append(next_fd)
            directory_stat = os.fstat(next_fd)
            identity = _DirectoryIdentity.from_stat(directory_stat)
            identities.append(identity)
            if expected_identities is not None and (
                index >= len(expected_identities)
                or not expected_identities[index].matches(directory_stat)
            ):
                raise MediaUploadResidueCleanupError("residue_invalid")
        if expected_identities is not None and len(expected_identities) != len(
            directory_descriptors
        ):
            raise MediaUploadResidueCleanupError("residue_invalid")
        return directory_descriptors, segments[-1], tuple(identities)
    except Exception:
        _close_directories(directory_descriptors)
        raise


def _observe_residue(residue_path: str) -> ValidatedUploadResidue:
    directories, basename, directory_identities = _open_parent_directory(
        residue_path
    )
    try:
        try:
            file_descriptor = os.open(
                basename,
                _file_flags(),
                dir_fd=directories[-1],
            )
        except FileNotFoundError as exc:
            raise MediaUploadResidueCleanupError("residue_not_found") from exc
        except OSError as exc:
            raise MediaUploadResidueCleanupError("residue_invalid") from exc
        try:
            file_stat = os.fstat(file_descriptor)
        finally:
            os.close(file_descriptor)
    finally:
        _close_directories(directories)
    if not stat.S_ISREG(file_stat.st_mode):
        raise MediaUploadResidueCleanupError("residue_invalid")
    residue = ValidatedUploadResidue(
        residue_path=residue_path,
        media_path=f"{local_media.LOCAL_MEDIA_PREFIX}{residue_path}",
        path=local_media.LOCAL_MEDIA_ROOT / PurePosixPath(residue_path),
        directory_identities=directory_identities,
        size=file_stat.st_size,
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        modified_ns=file_stat.st_mtime_ns,
        changed_ns=file_stat.st_ctime_ns,
    )
    _verify_residue_mapping(residue)
    return residue


def _same_identity(
    first: ValidatedUploadResidue,
    second: ValidatedUploadResidue,
) -> bool:
    return (
        first.residue_path == second.residue_path
        and first.media_path == second.media_path
        and first.directory_identities == second.directory_identities
        and first.size == second.size
        and first.device == second.device
        and first.inode == second.inode
        and first.modified_ns == second.modified_ns
        and first.changed_ns == second.changed_ns
    )


def _stat_matches_residue(
    residue: ValidatedUploadResidue,
    file_stat: os.stat_result,
) -> bool:
    return (
        stat.S_ISREG(file_stat.st_mode)
        and file_stat.st_dev == residue.device
        and file_stat.st_ino == residue.inode
        and file_stat.st_size == residue.size
        and file_stat.st_mtime_ns == residue.modified_ns
        and file_stat.st_ctime_ns == residue.changed_ns
    )


def _verify_residue_mapping(residue: ValidatedUploadResidue) -> None:
    directories, basename, _ = _open_parent_directory(
        residue.residue_path,
        expected_identities=residue.directory_identities,
    )
    try:
        try:
            current_stat = os.stat(
                basename,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
        except FileNotFoundError as exc:
            raise MediaUploadResidueCleanupError("residue_not_found") from exc
        except OSError as exc:
            raise MediaUploadResidueCleanupError("residue_invalid") from exc
        if not _stat_matches_residue(residue, current_stat):
            raise MediaUploadResidueCleanupError("residue_invalid")
    finally:
        _close_directories(directories)


def _reference_values(residue: ValidatedUploadResidue) -> tuple[str, str]:
    return residue.residue_path, residue.media_path


def _load_references(
    db: Session,
    residue: ValidatedUploadResidue,
) -> tuple[
    tuple[UploadResidueItemReference, ...],
    tuple[UploadResidueCreatorReference, ...],
]:
    values = _reference_values(residue)
    items = tuple(
        UploadResidueItemReference(
            id=row.id,
            title=row.title,
            value=row.cover_path,
        )
        for row in db.execute(
            select(Item.id, Item.title, Item.cover_path)
            .where(Item.cover_path.in_(values))
            .order_by(Item.title, Item.id)
        ).all()
    )
    creators = tuple(
        UploadResidueCreatorReference(
            id=row.id,
            name=row.name,
            value=row.avatar_path,
        )
        for row in db.execute(
            select(Creator.id, Creator.name, Creator.avatar_path)
            .where(Creator.avatar_path.in_(values))
            .order_by(Creator.name, Creator.id)
        ).all()
    )
    return items, creators


def _is_reported_residue(db: Session, residue_path: str) -> bool:
    return any(
        finding.code == "media_upload_residue"
        and finding.object_type == "media_file"
        and finding.object_id == residue_path
        for finding in audit_local_media(db)
    )


def build_media_upload_residue_cleanup_preview(
    db: Session,
    *,
    residue_path: str | None,
) -> MediaUploadResidueCleanupPreview:
    normalized = _normalize_residue_path(residue_path)
    residue = _observe_residue(normalized)
    if not _is_reported_residue(db, normalized):
        raise MediaUploadResidueCleanupError("not_residue")
    items, creators = _load_references(db, residue)
    return MediaUploadResidueCleanupPreview(
        residue=residue,
        item_references=items,
        creator_references=creators,
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaUploadResidueCleanupError("invalid_request")
    raw = str(value)
    if len(raw) > 30 or not raw.isascii() or not raw.isdecimal():
        raise MediaUploadResidueCleanupError("invalid_request")
    return int(raw)


def _snapshot_matches(
    residue: ValidatedUploadResidue,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        residue.size == _parse_identity_number(expected_size)
        and residue.device == _parse_identity_number(expected_device)
        and residue.inode == _parse_identity_number(expected_inode)
        and residue.modified_ns == _parse_identity_number(expected_modified_ns)
        and residue.changed_ns == _parse_identity_number(expected_changed_ns)
    )


def _delete_residue(residue: ValidatedUploadResidue) -> None:
    try:
        current = _observe_residue(residue.residue_path)
    except MediaUploadResidueCleanupError as exc:
        code = "missing" if exc.code == "residue_not_found" else "changed"
        raise _ResidueDeleteError(code) from exc
    if not _same_identity(residue, current):
        raise _ResidueDeleteError("changed")

    try:
        directories, basename, _ = _open_parent_directory(
            residue.residue_path,
            expected_identities=residue.directory_identities,
        )
    except MediaUploadResidueCleanupError as exc:
        code = "missing" if exc.code == "residue_not_found" else "changed"
        raise _ResidueDeleteError(code) from exc
    try:
        try:
            current_stat = os.stat(
                basename,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
        except FileNotFoundError as exc:
            raise _ResidueDeleteError("missing") from exc
        except OSError as exc:
            raise _ResidueDeleteError("delete_failed") from exc
        if not _stat_matches_residue(residue, current_stat):
            raise _ResidueDeleteError("changed")
        try:
            _verify_residue_mapping(residue)
        except MediaUploadResidueCleanupError as exc:
            raise _ResidueDeleteError("changed") from exc
        try:
            os.unlink(basename, dir_fd=directories[-1])
        except FileNotFoundError as exc:
            raise _ResidueDeleteError("missing") from exc
        except OSError as exc:
            raise _ResidueDeleteError("delete_failed") from exc
        try:
            os.fsync(directories[-1])
        except OSError as exc:
            raise _ResidueDeleteError("sync_failed", removed=True) from exc
    finally:
        _close_directories(directories)


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def execute_media_upload_residue_cleanup(
    db: Session,
    *,
    residue_path: str | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaUploadResidueCleanupResult:
    preview = build_media_upload_residue_cleanup_preview(
        db,
        residue_path=residue_path,
    )
    if not _snapshot_matches(
        preview.residue,
        expected_size=expected_size,
        expected_device=expected_device,
        expected_inode=expected_inode,
        expected_modified_ns=expected_modified_ns,
        expected_changed_ns=expected_changed_ns,
    ):
        raise MediaUploadResidueCleanupError("stale_residue")

    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaUploadResidueCleanupError("reference_check_failed") from exc

    try:
        items, creators = _load_references(db, preview.residue)
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaUploadResidueCleanupError("reference_check_failed") from exc
    if items or creators:
        _rollback_quietly(db)
        raise MediaUploadResidueCleanupError("residue_referenced")

    try:
        try:
            current = _observe_residue(preview.residue.residue_path)
        except MediaUploadResidueCleanupError as exc:
            raise MediaUploadResidueCleanupError("stale_residue") from exc
        if not _same_identity(preview.residue, current):
            raise MediaUploadResidueCleanupError("stale_residue")
        _delete_residue(current)
    except MediaUploadResidueCleanupError:
        _rollback_quietly(db)
        raise
    except _ResidueDeleteError as exc:
        _rollback_quietly(db)
        if exc.removed:
            return MediaUploadResidueCleanupResult(
                deleted_path=preview.residue.residue_path,
                size=preview.residue.size,
                warning_code=exc.code,
            )
        code = (
            "stale_residue"
            if exc.code in {"changed", "missing"}
            else "delete_failed"
        )
        raise MediaUploadResidueCleanupError(code) from exc
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaUploadResidueCleanupError("delete_failed") from exc

    warning_code = None
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        warning_code = "lock_release_failed"
    return MediaUploadResidueCleanupResult(
        deleted_path=preview.residue.residue_path,
        size=preview.residue.size,
        warning_code=warning_code,
    )
