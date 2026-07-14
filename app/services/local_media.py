from __future__ import annotations

import hashlib
import os
import secrets
import stat
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from fastapi import UploadFile


LOCAL_MEDIA_PREFIX = "/media/"
LOCAL_MEDIA_ROOT = Path("data/media")
LOCAL_MEDIA_LIBRARY_DIR = "library"
ALLOWED_MEDIA_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_MEDIA_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_MEDIA_UPLOAD_FILES = 20
LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX = ".cleanup-anchor-"
LOCAL_MEDIA_RECOVERY_PREFIX = "recovered-"
LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX = ".upload-"
LOCAL_MEDIA_UPLOAD_RESIDUE_SUFFIX = ".tmp"
_MIME_BY_FORMAT = {
    "avif": "image/avif",
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_FORMATS_BY_EXTENSION = {
    ".avif": {"avif"},
    ".gif": {"gif"},
    ".jpeg": {"jpeg"},
    ".jpg": {"jpeg"},
    ".png": {"png"},
    ".webp": {"webp"},
}


class LocalMediaPathError(ValueError):
    pass


class LocalMediaUploadError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LocalMediaDeleteError(OSError):
    def __init__(self, code: str, *, removed: bool = False) -> None:
        self.code = code
        self.removed = removed
        super().__init__(code)


class LocalMediaSafetyAnchorError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LocalMediaEntry:
    media_path: str
    filename: str
    size: int
    sha256: str
    mime_type: str
    available: bool
    detail: str = ""
    is_cleanup_anchor: bool = False
    is_recovered: bool = False


MediaScanSkipReason = Literal[
    "symlink",
    "unsupported_extension",
    "special_file",
    "directory_unreadable",
    "entry_error",
]


@dataclass(frozen=True)
class LocalMediaScanSkip:
    path: str
    reason: MediaScanSkipReason
    extension: str
    size: int | None
    device: int | None
    inode: int | None
    modified_ns: int | None
    changed_ns: int | None


@dataclass(frozen=True)
class LocalMediaScan:
    entries: tuple[LocalMediaEntry, ...]
    skipped_symlinks: int
    skipped_unsupported: int
    invalid: int
    skipped_entries: tuple[LocalMediaScanSkip, ...] = ()


@dataclass(frozen=True)
class _MediaScanIdentity:
    mode: int
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, file_stat: os.stat_result) -> _MediaScanIdentity:
        return cls(
            mode=file_stat.st_mode,
            size=file_stat.st_size,
            device=file_stat.st_dev,
            inode=file_stat.st_ino,
            modified_ns=file_stat.st_mtime_ns,
            changed_ns=file_stat.st_ctime_ns,
        )

    def matches(self, file_stat: os.stat_result) -> bool:
        return self == self.from_stat(file_stat)


@dataclass(frozen=True)
class _LocalMediaScanCandidate:
    root: Path
    parts: tuple[str, ...]
    display_path: str
    extension: str
    directory_identities: tuple[_MediaScanIdentity, ...]
    file_identity: _MediaScanIdentity


class _MediaScanCandidateChanged(OSError):
    pass


@dataclass(frozen=True)
class LocalMediaUploadResult:
    uploaded: int
    duplicate: int
    media_paths: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedLocalMediaFile:
    media_path: str
    path: Path
    size: int
    sha256: str
    device: int
    inode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class _PublishedMedia:
    path: Path
    device: int
    inode: int


def normalize_local_media_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = value.strip()
    if not path:
        return None
    if (
        len(path) > 500
        or not path.startswith(LOCAL_MEDIA_PREFIX)
        or path.startswith("//")
        or "\\" in path
        or "%" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise LocalMediaPathError("invalid local media path")

    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or parsed.path != path:
        raise LocalMediaPathError("invalid local media path")

    relative_path = path.removeprefix(LOCAL_MEDIA_PREFIX)
    segments = relative_path.split("/")
    if not relative_path or any(segment in {"", ".", ".."} for segment in segments):
        raise LocalMediaPathError("invalid local media path")
    if PurePosixPath(relative_path).suffix.casefold() not in ALLOWED_MEDIA_EXTENSIONS:
        raise LocalMediaPathError("unsupported local media type")
    return path


def _valid_png(content: bytes) -> bool:
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    first_chunk = True
    while offset + 12 <= len(content):
        length = int.from_bytes(content[offset : offset + 4], "big")
        chunk_end = offset + 12 + length
        if chunk_end > len(content):
            return False
        chunk_type = content[offset + 4 : offset + 8]
        chunk_data = content[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(content[offset + 8 + length : chunk_end], "big")
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False
        if first_chunk:
            if (
                chunk_type != b"IHDR"
                or length != 13
                or int.from_bytes(chunk_data[:4], "big") <= 0
                or int.from_bytes(chunk_data[4:8], "big") <= 0
            ):
                return False
            first_chunk = False
        if chunk_type == b"IEND":
            return length == 0 and chunk_end == len(content)
        offset = chunk_end
    return False


def _valid_jpeg(content: bytes) -> bool:
    return (
        len(content) >= 4
        and content.startswith(b"\xff\xd8\xff")
        and content.endswith(b"\xff\xd9")
    )


def _detect_image_format(content: bytes) -> str | None:
    if _valid_png(content):
        return "png"
    if _valid_jpeg(content):
        return "jpeg"
    if (
        len(content) >= 10
        and content[:6] in {b"GIF87a", b"GIF89a"}
        and int.from_bytes(content[6:8], "little") > 0
        and int.from_bytes(content[8:10], "little") > 0
        and content.endswith(b";")
    ):
        return "gif"
    if (
        len(content) >= 16
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
        and int.from_bytes(content[4:8], "little") + 8 == len(content)
        and content[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    ):
        return "webp"
    if len(content) >= 16 and content[4:8] == b"ftyp":
        brands = {content[index : index + 4] for index in range(8, len(content) - 3, 4)}
        if brands.intersection({b"avif", b"avis"}):
            return "avif"
    return None


def _validated_image_format(content: bytes, extension: str) -> str:
    detected = _detect_image_format(content)
    if detected is None or detected not in _FORMATS_BY_EXTENSION.get(extension, set()):
        raise LocalMediaUploadError("invalid_image")
    return detected


def _root_for_read() -> Path:
    root = LOCAL_MEDIA_ROOT
    try:
        if root.is_symlink() or not root.is_dir():
            raise LocalMediaPathError("local media directory unavailable")
        return root.resolve(strict=True)
    except OSError as exc:
        raise LocalMediaPathError("local media directory unavailable") from exc


def _safe_media_file(media_path: str) -> Path:
    normalized = normalize_local_media_path(media_path)
    if normalized is None:
        raise LocalMediaPathError("invalid local media path")
    root = _root_for_read()
    candidate = root
    try:
        for segment in normalized.removeprefix(LOCAL_MEDIA_PREFIX).split("/"):
            candidate = candidate / segment
            if candidate.is_symlink():
                raise LocalMediaPathError("symbolic links are not allowed")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise LocalMediaPathError("local media path escapes media directory")
        file_stat = resolved.stat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_MEDIA_UPLOAD_BYTES:
            raise LocalMediaPathError("local media file unavailable")
    except (OSError, RuntimeError) as exc:
        raise LocalMediaPathError("local media file unavailable") from exc
    return resolved


def _read_validated_file(path: Path, extension: str) -> tuple[bytes, str]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise LocalMediaPathError("local media file unavailable") from exc
    try:
        image_format = _validated_image_format(content, extension)
    except LocalMediaUploadError as exc:
        raise LocalMediaPathError("invalid local media image") from exc
    return content, image_format


def local_media_url(value: str | None) -> str | None:
    try:
        normalized = normalize_local_media_path(value)
        if normalized is None:
            return None
        resolve_local_media_file(normalized.removeprefix(LOCAL_MEDIA_PREFIX))
        return normalized
    except LocalMediaPathError:
        return None


def resolve_local_media_file(media_path: str) -> Path:
    normalized = normalize_local_media_path(f"{LOCAL_MEDIA_PREFIX}{media_path}")
    if normalized is None:
        raise LocalMediaPathError("invalid local media path")
    candidate = _safe_media_file(normalized)
    _read_validated_file(candidate, candidate.suffix.casefold())
    return candidate


def validate_local_media_file(
    media_path: str,
    *,
    expected_sha256: str,
) -> ValidatedLocalMediaFile:
    normalized = normalize_local_media_path(media_path)
    digest = expected_sha256.casefold()
    if normalized is None or len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise LocalMediaPathError("invalid local media validation request")

    path = _safe_media_file(normalized)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_descriptor = os.open(path, flags)
        try:
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_MEDIA_UPLOAD_BYTES:
                raise LocalMediaPathError("local media file unavailable")
            with os.fdopen(file_descriptor, "rb", closefd=False) as stream:
                content = stream.read(MAX_MEDIA_UPLOAD_BYTES + 1)
            after = os.fstat(file_descriptor)
        finally:
            os.close(file_descriptor)
    except LocalMediaPathError:
        raise
    except OSError as exc:
        raise LocalMediaPathError("local media file unavailable") from exc

    if (
        len(content) > MAX_MEDIA_UPLOAD_BYTES
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or len(content) != after.st_size
    ):
        raise LocalMediaPathError("local media file changed during validation")
    try:
        _validated_image_format(content, path.suffix.casefold())
    except LocalMediaUploadError as exc:
        raise LocalMediaPathError("invalid local media image") from exc
    actual_digest = hashlib.sha256(content).hexdigest()
    if actual_digest != digest:
        raise LocalMediaPathError("local media hash changed")
    return ValidatedLocalMediaFile(
        media_path=normalized,
        path=path,
        size=len(content),
        sha256=actual_digest,
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
        changed_ns=after.st_ctime_ns,
    )


def _record_matches_stat(
    record: ValidatedLocalMediaFile,
    file_stat: os.stat_result,
) -> bool:
    return (
        stat.S_ISREG(file_stat.st_mode)
        and file_stat.st_dev == record.device
        and file_stat.st_ino == record.inode
        and file_stat.st_size == record.size
        and file_stat.st_mtime_ns == record.modified_ns
        and file_stat.st_ctime_ns == record.changed_ns
    )


def same_local_media_file_identity(
    first: ValidatedLocalMediaFile,
    second: ValidatedLocalMediaFile,
) -> bool:
    return (
        first.media_path == second.media_path
        and first.path == second.path
        and first.sha256 == second.sha256
        and first.size == second.size
        and first.device == second.device
        and first.inode == second.inode
        and first.modified_ns == second.modified_ns
        and first.changed_ns == second.changed_ns
    )


def _read_validated_record_content(record: ValidatedLocalMediaFile) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_descriptor = os.open(record.path, flags)
        try:
            before = os.fstat(file_descriptor)
            if not _record_matches_stat(record, before):
                raise LocalMediaSafetyAnchorError("source_changed")
            with os.fdopen(file_descriptor, "rb", closefd=False) as stream:
                content = stream.read(MAX_MEDIA_UPLOAD_BYTES + 1)
            after = os.fstat(file_descriptor)
        finally:
            os.close(file_descriptor)
    except LocalMediaSafetyAnchorError:
        raise
    except OSError as exc:
        raise LocalMediaSafetyAnchorError("source_changed") from exc

    if (
        not _record_matches_stat(record, after)
        or len(content) != record.size
        or len(content) > MAX_MEDIA_UPLOAD_BYTES
    ):
        raise LocalMediaSafetyAnchorError("source_changed")
    try:
        _validated_image_format(content, record.path.suffix.casefold())
    except LocalMediaUploadError as exc:
        raise LocalMediaSafetyAnchorError("source_changed") from exc
    if hashlib.sha256(content).hexdigest() != record.sha256:
        raise LocalMediaSafetyAnchorError("source_changed")
    return content


def create_local_media_safety_anchor(
    record: ValidatedLocalMediaFile,
) -> ValidatedLocalMediaFile:
    content = _read_validated_record_content(record)
    anchor_fd = -1
    anchor_path: Path | None = None
    try:
        anchor_fd, raw_anchor_path = tempfile.mkstemp(
            prefix=LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX,
            suffix=record.path.suffix.casefold(),
            dir=record.path.parent,
        )
        anchor_path = Path(raw_anchor_path)
        os.fchmod(anchor_fd, 0o600)
        with os.fdopen(anchor_fd, "wb") as stream:
            anchor_fd = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            _fsync_directory(record.path.parent)
        except LocalMediaUploadError as exc:
            raise LocalMediaSafetyAnchorError("sync_failed") from exc
        anchor_media_path = (
            f"{PurePosixPath(record.media_path).parent.as_posix()}/"
            f"{anchor_path.name}"
        )
        return validate_local_media_file(
            anchor_media_path,
            expected_sha256=record.sha256,
        )
    except Exception as exc:
        if anchor_fd >= 0:
            os.close(anchor_fd)
        if anchor_path is not None:
            try:
                anchor_path.unlink(missing_ok=True)
                _fsync_directory(record.path.parent)
            except Exception:
                pass
        if isinstance(exc, LocalMediaSafetyAnchorError):
            raise
        raise LocalMediaSafetyAnchorError("create_failed") from exc


def publish_local_media_safety_anchor(
    anchor: ValidatedLocalMediaFile,
    target_media_path: str,
) -> ValidatedLocalMediaFile:
    try:
        normalized_target = normalize_local_media_path(target_media_path)
    except LocalMediaPathError as exc:
        raise LocalMediaSafetyAnchorError("invalid_target") from exc
    if normalized_target is None:
        raise LocalMediaSafetyAnchorError("invalid_target")
    target_pure_path = PurePosixPath(normalized_target)
    if target_pure_path.parent != PurePosixPath(anchor.media_path).parent:
        raise LocalMediaSafetyAnchorError("invalid_target")

    try:
        current_anchor = validate_local_media_file(
            anchor.media_path,
            expected_sha256=anchor.sha256,
        )
    except LocalMediaPathError as exc:
        raise LocalMediaSafetyAnchorError("anchor_changed") from exc
    if not same_local_media_file_identity(anchor, current_anchor):
        raise LocalMediaSafetyAnchorError("anchor_changed")
    target_path = current_anchor.path.parent / target_pure_path.name
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        directory_fd = os.open(current_anchor.path.parent, flags)
    except OSError as exc:
        raise LocalMediaSafetyAnchorError("publish_failed") from exc
    linked = False
    try:
        try:
            os.link(
                current_anchor.path.name,
                target_path.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError as exc:
            raise LocalMediaSafetyAnchorError("target_exists") from exc
        except OSError as exc:
            raise LocalMediaSafetyAnchorError("publish_failed") from exc
        try:
            target_fd_flags = os.O_RDONLY
            if hasattr(os, "O_CLOEXEC"):
                target_fd_flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                target_fd_flags |= os.O_NOFOLLOW
            target_fd = os.open(
                target_path.name,
                target_fd_flags,
                dir_fd=directory_fd,
            )
            try:
                target_stat = os.fstat(target_fd)
                if (
                    not stat.S_ISREG(target_stat.st_mode)
                    or target_stat.st_dev != current_anchor.device
                    or target_stat.st_ino != current_anchor.inode
                    or target_stat.st_size != current_anchor.size
                ):
                    raise LocalMediaSafetyAnchorError("publish_failed")
                os.fsync(target_fd)
            finally:
                os.close(target_fd)
            os.fsync(directory_fd)
        except LocalMediaSafetyAnchorError:
            raise
        except OSError as exc:
            raise LocalMediaSafetyAnchorError("sync_failed") from exc
    except Exception:
        if linked:
            try:
                target_stat = os.stat(
                    target_path.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                anchor_stat = os.stat(
                    current_anchor.path.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if (
                    target_stat.st_dev == anchor_stat.st_dev
                    and target_stat.st_ino == anchor_stat.st_ino
                ):
                    os.unlink(target_path.name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(directory_fd)

    try:
        return validate_local_media_file(
            normalized_target,
            expected_sha256=anchor.sha256,
        )
    except LocalMediaPathError as exc:
        try:
            target_stat = target_path.stat(follow_symlinks=False)
            anchor_stat = current_anchor.path.stat(follow_symlinks=False)
            if (
                target_stat.st_dev == anchor_stat.st_dev
                and target_stat.st_ino == anchor_stat.st_ino
            ):
                target_path.unlink()
                _fsync_directory(target_path.parent)
        except Exception:
            pass
        raise LocalMediaSafetyAnchorError("publish_failed") from exc


def publish_local_media_recovery(
    anchor: ValidatedLocalMediaFile,
) -> ValidatedLocalMediaFile:
    parent = PurePosixPath(anchor.media_path).parent.as_posix()
    extension = anchor.path.suffix.casefold()
    for _ in range(16):
        candidate = (
            f"{parent}/{LOCAL_MEDIA_RECOVERY_PREFIX}{anchor.sha256[:12]}-"
            f"{secrets.token_hex(8)}{extension}"
        )
        try:
            return publish_local_media_safety_anchor(anchor, candidate)
        except LocalMediaSafetyAnchorError as exc:
            if exc.code != "target_exists":
                raise
    raise LocalMediaSafetyAnchorError("publish_failed")


def _delete_validated_local_media_file(record: ValidatedLocalMediaFile) -> None:
    try:
        current = validate_local_media_file(
            record.media_path,
            expected_sha256=record.sha256,
        )
    except LocalMediaPathError as exc:
        raise LocalMediaDeleteError("changed") from exc
    if (
        current.path != record.path
        or current.device != record.device
        or current.inode != record.inode
        or current.size != record.size
        or current.modified_ns != record.modified_ns
        or current.changed_ns != record.changed_ns
    ):
        raise LocalMediaDeleteError("changed")

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        directory_fd = os.open(current.path.parent, flags)
    except OSError as exc:
        raise LocalMediaDeleteError("delete_failed") from exc
    try:
        try:
            current_stat = os.stat(
                current.path.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError as exc:
            raise LocalMediaDeleteError("missing") from exc
        except OSError as exc:
            raise LocalMediaDeleteError("delete_failed") from exc
        if (
            not stat.S_ISREG(current_stat.st_mode)
            or current_stat.st_dev != record.device
            or current_stat.st_ino != record.inode
            or current_stat.st_size != record.size
            or current_stat.st_mtime_ns != record.modified_ns
            or current_stat.st_ctime_ns != record.changed_ns
        ):
            raise LocalMediaDeleteError("changed")
        try:
            os.unlink(current.path.name, dir_fd=directory_fd)
        except FileNotFoundError as exc:
            raise LocalMediaDeleteError("missing") from exc
        except OSError as exc:
            raise LocalMediaDeleteError("delete_failed") from exc
        try:
            os.fsync(directory_fd)
        except OSError as exc:
            raise LocalMediaDeleteError("sync_failed", removed=True) from exc
    finally:
        os.close(directory_fd)


def delete_validated_local_media_file(record: ValidatedLocalMediaFile) -> None:
    _delete_validated_local_media_file(record)


def delete_local_media_safety_anchor(
    anchor: ValidatedLocalMediaFile,
) -> None:
    try:
        current_anchor = validate_local_media_file(
            anchor.media_path,
            expected_sha256=anchor.sha256,
        )
    except LocalMediaPathError as exc:
        raise LocalMediaSafetyAnchorError("anchor_changed") from exc
    try:
        _delete_validated_local_media_file(current_anchor)
    except LocalMediaDeleteError as exc:
        raise LocalMediaSafetyAnchorError(exc.code) from exc


def _has_exact_media_prefix(value: str, prefix: str) -> bool:
    name = PurePosixPath(value).name
    return name.startswith(prefix) and len(name) > len(prefix)


def is_cleanup_anchor_filename(value: str) -> bool:
    return _has_exact_media_prefix(value, LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX)


def is_recovered_media_filename(value: str) -> bool:
    return _has_exact_media_prefix(value, LOCAL_MEDIA_RECOVERY_PREFIX)


def is_upload_residue_filename(value: str) -> bool:
    name = PurePosixPath(value).name
    return (
        name.startswith(LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX)
        and name.endswith(LOCAL_MEDIA_UPLOAD_RESIDUE_SUFFIX)
        and len(name)
        > len(LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX)
        + len(LOCAL_MEDIA_UPLOAD_RESIDUE_SUFFIX)
    )


def normalize_interactive_local_media_path(value: str | None) -> str | None:
    normalized = normalize_local_media_path(value)
    if normalized is not None and is_cleanup_anchor_filename(normalized):
        raise LocalMediaPathError("cleanup anchors are internal media")
    return normalized


def _safe_scan_text(value: str) -> str:
    parts: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\\":
            parts.append("\\\\")
        elif (
            codepoint < 32
            or codepoint == 127
            or 0xD800 <= codepoint <= 0xDFFF
        ):
            parts.append(f"\\u{codepoint:04x}")
        else:
            parts.append(character)
    return "".join(parts)


def _join_scan_relative_path(parent: str, name: str) -> str:
    safe_name = _safe_scan_text(name)
    return safe_name if parent == "." else f"{parent}/{safe_name}"


def _media_scan_skip(
    *,
    path: str,
    reason: MediaScanSkipReason,
    extension: str,
    file_stat: os.stat_result | None,
) -> LocalMediaScanSkip:
    return LocalMediaScanSkip(
        path=path,
        reason=reason,
        extension=extension,
        size=file_stat.st_size if file_stat is not None else None,
        device=file_stat.st_dev if file_stat is not None else None,
        inode=file_stat.st_ino if file_stat is not None else None,
        modified_ns=file_stat.st_mtime_ns if file_stat is not None else None,
        changed_ns=file_stat.st_ctime_ns if file_stat is not None else None,
    )


def _media_scan_skip_from_identity(
    *,
    path: str,
    reason: MediaScanSkipReason,
    extension: str,
    identity: _MediaScanIdentity,
) -> LocalMediaScanSkip:
    return LocalMediaScanSkip(
        path=path,
        reason=reason,
        extension=extension,
        size=identity.size,
        device=identity.device,
        inode=identity.inode,
        modified_ns=identity.modified_ns,
        changed_ns=identity.changed_ns,
    )


def _scan_directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _scan_file_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _close_scan_descriptors(
    directory_descriptors: list[int],
    file_descriptor: int | None,
) -> None:
    if file_descriptor is not None:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
    for directory_descriptor in reversed(directory_descriptors):
        try:
            os.close(directory_descriptor)
        except OSError:
            pass


def _open_verified_scan_candidate(
    candidate: _LocalMediaScanCandidate,
) -> tuple[list[int], int]:
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        root_descriptor = os.open(candidate.root, _scan_directory_flags())
        directory_descriptors.append(root_descriptor)
        if not candidate.directory_identities[0].matches(
            os.fstat(root_descriptor)
        ):
            raise _MediaScanCandidateChanged()
        for index, segment in enumerate(candidate.parts[:-1], start=1):
            child_descriptor = os.open(
                segment,
                _scan_directory_flags(),
                dir_fd=directory_descriptors[-1],
            )
            directory_descriptors.append(child_descriptor)
            if not candidate.directory_identities[index].matches(
                os.fstat(child_descriptor)
            ):
                raise _MediaScanCandidateChanged()
        file_descriptor = os.open(
            candidate.parts[-1],
            _scan_file_flags(),
            dir_fd=directory_descriptors[-1],
        )
        file_stat = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size > MAX_MEDIA_UPLOAD_BYTES
            or not candidate.file_identity.matches(file_stat)
        ):
            raise _MediaScanCandidateChanged()
        return directory_descriptors, file_descriptor
    except _MediaScanCandidateChanged:
        _close_scan_descriptors(directory_descriptors, file_descriptor)
        raise
    except (OSError, IndexError):
        _close_scan_descriptors(directory_descriptors, file_descriptor)
        raise _MediaScanCandidateChanged() from None


def _read_scan_file_descriptor(file_descriptor: int) -> bytes:
    with os.fdopen(file_descriptor, "rb", closefd=False) as stream:
        return stream.read(MAX_MEDIA_UPLOAD_BYTES + 1)


def _verify_open_scan_candidate(
    candidate: _LocalMediaScanCandidate,
    directory_descriptors: list[int],
    file_descriptor: int,
    content: bytes,
) -> None:
    if len(directory_descriptors) != len(candidate.directory_identities):
        raise _MediaScanCandidateChanged()
    if any(
        not identity.matches(os.fstat(directory_descriptor))
        for identity, directory_descriptor in zip(
            candidate.directory_identities,
            directory_descriptors,
            strict=True,
        )
    ):
        raise _MediaScanCandidateChanged()
    file_stat = os.fstat(file_descriptor)
    if (
        len(content) > MAX_MEDIA_UPLOAD_BYTES
        or len(content) != file_stat.st_size
        or not candidate.file_identity.matches(file_stat)
    ):
        raise _MediaScanCandidateChanged()


def _verify_scan_candidate_mapping(
    candidate: _LocalMediaScanCandidate,
) -> None:
    directories, file_descriptor = _open_verified_scan_candidate(candidate)
    _close_scan_descriptors(directories, file_descriptor)


def _read_verified_scan_candidate(
    candidate: _LocalMediaScanCandidate,
) -> tuple[bytes, str, str]:
    directories, file_descriptor = _open_verified_scan_candidate(candidate)
    try:
        content = _read_scan_file_descriptor(file_descriptor)
        _verify_open_scan_candidate(
            candidate,
            directories,
            file_descriptor,
            content,
        )
        _verify_scan_candidate_mapping(candidate)
        try:
            image_format = _validated_image_format(
                content,
                candidate.extension,
            )
        except LocalMediaUploadError as exc:
            raise LocalMediaPathError("invalid local media image") from exc
        digest = hashlib.sha256(content).hexdigest()
        _verify_open_scan_candidate(
            candidate,
            directories,
            file_descriptor,
            content,
        )
        _verify_scan_candidate_mapping(candidate)
        return content, image_format, digest
    except _MediaScanCandidateChanged:
        raise
    except OSError:
        raise LocalMediaPathError("local media file unavailable") from None
    finally:
        _close_scan_descriptors(directories, file_descriptor)


def _sorted_scan_entries(directory_fd: int) -> list[os.DirEntry[str]]:
    with os.scandir(directory_fd) as iterator:
        return sorted(
            iterator,
            key=lambda entry: (entry.name.casefold(), entry.name),
        )


def _entry_lstat(entry: os.DirEntry[str]) -> os.stat_result:
    return entry.stat(follow_symlinks=False)


def _iter_media_files(
    *,
    include_cleanup_anchors: bool = False,
) -> tuple[list[_LocalMediaScanCandidate], tuple[LocalMediaScanSkip, ...]]:
    if not LOCAL_MEDIA_ROOT.exists():
        return [], ()
    root = _root_for_read()
    files: list[_LocalMediaScanCandidate] = []
    skipped: list[LocalMediaScanSkip] = []
    try:
        root_fd = os.open(root, _scan_directory_flags())
    except OSError:
        try:
            root_stat: os.stat_result | None = root.stat(follow_symlinks=False)
        except OSError:
            root_stat = None
        return files, (
            _media_scan_skip(
                path=".",
                reason="directory_unreadable",
                extension="",
                file_stat=root_stat,
            ),
        )

    def append_symlink(
        *,
        name: str,
        path: str,
        extension: str,
        file_stat: os.stat_result,
        directory_parts: tuple[str, ...],
        directory_identities: tuple[_MediaScanIdentity, ...],
    ) -> None:
        cleanup_anchor = is_cleanup_anchor_filename(name)
        recovered = is_recovered_media_filename(name)
        if cleanup_anchor and not include_cleanup_anchors:
            return
        skipped.append(
            _media_scan_skip(
                path=path,
                reason="symlink",
                extension=extension,
                file_stat=file_stat,
            )
        )
        if include_cleanup_anchors and (cleanup_anchor or recovered):
            files.append(
                _LocalMediaScanCandidate(
                    root=root,
                    parts=directory_parts + (name,),
                    display_path=path,
                    extension=PurePosixPath(name).suffix.casefold(),
                    directory_identities=directory_identities,
                    file_identity=_MediaScanIdentity.from_stat(file_stat),
                )
            )

    def walk_directory(
        directory_fd: int,
        directory_parts: tuple[str, ...],
        directory_identities: tuple[_MediaScanIdentity, ...],
        directory_relative: str,
        directory_extension: str,
        directory_stat: os.stat_result,
    ) -> None:
        try:
            entries = _sorted_scan_entries(directory_fd)
        except OSError:
            skipped.append(
                _media_scan_skip(
                    path=directory_relative,
                    reason="directory_unreadable",
                    extension=directory_extension,
                    file_stat=directory_stat,
                )
            )
            return
        for entry in entries:
            relative = _join_scan_relative_path(directory_relative, entry.name)
            extension = _safe_scan_text(PurePosixPath(entry.name).suffix)
            try:
                file_stat = _entry_lstat(entry)
                if stat.S_ISLNK(file_stat.st_mode):
                    append_symlink(
                        name=entry.name,
                        path=relative,
                        extension=extension,
                        file_stat=file_stat,
                        directory_parts=directory_parts,
                        directory_identities=directory_identities,
                    )
                elif stat.S_ISDIR(file_stat.st_mode):
                    try:
                        child_fd = os.open(
                            entry.name,
                            _scan_directory_flags(),
                            dir_fd=directory_fd,
                        )
                    except OSError:
                        try:
                            current_stat = os.stat(
                                entry.name,
                                dir_fd=directory_fd,
                                follow_symlinks=False,
                            )
                        except OSError:
                            skipped.append(
                                _media_scan_skip(
                                    path=relative,
                                    reason="entry_error",
                                    extension=extension,
                                    file_stat=None,
                                )
                            )
                        else:
                            if stat.S_ISLNK(current_stat.st_mode):
                                append_symlink(
                                    name=entry.name,
                                    path=relative,
                                    extension=extension,
                                    file_stat=current_stat,
                                    directory_parts=directory_parts,
                                    directory_identities=directory_identities,
                                )
                            else:
                                skipped.append(
                                    _media_scan_skip(
                                        path=relative,
                                        reason="directory_unreadable",
                                        extension=extension,
                                        file_stat=current_stat,
                                    )
                                )
                        continue
                    try:
                        child_stat = os.fstat(child_fd)
                        if (
                            not stat.S_ISDIR(child_stat.st_mode)
                            or not _MediaScanIdentity.from_stat(
                                file_stat
                            ).matches(child_stat)
                        ):
                            skipped.append(
                                _media_scan_skip(
                                    path=relative,
                                    reason="entry_error",
                                    extension=extension,
                                    file_stat=child_stat,
                                )
                            )
                            continue
                        try:
                            walk_directory(
                                child_fd,
                                directory_parts + (entry.name,),
                                directory_identities
                                + (_MediaScanIdentity.from_stat(child_stat),),
                                relative,
                                extension,
                                child_stat,
                            )
                        except RecursionError:
                            skipped.append(
                                _media_scan_skip(
                                    path=relative,
                                    reason="directory_unreadable",
                                    extension=extension,
                                    file_stat=child_stat,
                                )
                            )
                    finally:
                        try:
                            os.close(child_fd)
                        except OSError:
                            pass
                elif stat.S_ISREG(file_stat.st_mode):
                    cleanup_anchor = is_cleanup_anchor_filename(entry.name)
                    recovered = is_recovered_media_filename(entry.name)
                    if cleanup_anchor and not include_cleanup_anchors:
                        continue
                    suffix = PurePosixPath(entry.name).suffix.casefold()
                    if (
                        suffix in ALLOWED_MEDIA_EXTENSIONS
                        or (
                            include_cleanup_anchors
                            and (cleanup_anchor or recovered)
                        )
                    ):
                        files.append(
                            _LocalMediaScanCandidate(
                                root=root,
                                parts=directory_parts + (entry.name,),
                                display_path=relative,
                                extension=suffix,
                                directory_identities=directory_identities,
                                file_identity=_MediaScanIdentity.from_stat(
                                    file_stat
                                ),
                            )
                        )
                    else:
                        skipped.append(
                            _media_scan_skip(
                                path=relative,
                                reason="unsupported_extension",
                                extension=extension,
                                file_stat=file_stat,
                            )
                        )
                else:
                    skipped.append(
                        _media_scan_skip(
                            path=relative,
                            reason="special_file",
                            extension=extension,
                            file_stat=file_stat,
                        )
                    )
            except OSError:
                skipped.append(
                    _media_scan_skip(
                        path=relative,
                        reason="entry_error",
                        extension=extension,
                        file_stat=None,
                    )
                )
    try:
        root_stat = os.fstat(root_fd)
        walk_directory(
            root_fd,
            (),
            (_MediaScanIdentity.from_stat(root_stat),),
            ".",
            "",
            root_stat,
        )
    finally:
        try:
            os.close(root_fd)
        except OSError:
            pass
    unique_skips = {
        (entry.path, entry.reason): entry
        for entry in skipped
    }
    ordered_skips = tuple(
        sorted(
            unique_skips.values(),
            key=lambda entry: (entry.path.casefold(), entry.path, entry.reason),
        )
    )
    return files, ordered_skips


def scan_local_media(
    *,
    include_cleanup_anchors: bool = False,
) -> LocalMediaScan:
    files, skipped_entries = _iter_media_files(
        include_cleanup_anchors=include_cleanup_anchors,
    )
    entries: list[LocalMediaEntry] = []
    invalid = 0
    mutable_skipped_entries = list(skipped_entries)
    for candidate in files:
        relative = PurePosixPath(*candidate.parts).as_posix()
        media_path = f"{LOCAL_MEDIA_PREFIX}{relative}"
        cleanup_anchor = is_cleanup_anchor_filename(candidate.parts[-1])
        recovered = is_recovered_media_filename(candidate.parts[-1])
        observed_size = (
            candidate.file_identity.size
            if stat.S_ISREG(candidate.file_identity.mode)
            else 0
        )
        if (
            not stat.S_ISREG(candidate.file_identity.mode)
            or candidate.file_identity.size > MAX_MEDIA_UPLOAD_BYTES
        ):
            invalid += 1
            entries.append(
                LocalMediaEntry(
                    media_path=media_path,
                    filename=relative,
                    size=(observed_size if cleanup_anchor or recovered else 0),
                    sha256="",
                    mime_type="",
                    available=False,
                    detail="invalid_image",
                    is_cleanup_anchor=cleanup_anchor,
                    is_recovered=recovered,
                )
            )
            continue
        try:
            content, image_format, digest = _read_verified_scan_candidate(
                candidate
            )
        except _MediaScanCandidateChanged:
            mutable_skipped_entries.append(
                _media_scan_skip_from_identity(
                    path=candidate.display_path,
                    reason="entry_error",
                    extension=_safe_scan_text(candidate.extension),
                    identity=candidate.file_identity,
                )
            )
            continue
        except (LocalMediaPathError, OSError):
            invalid += 1
            entries.append(
                LocalMediaEntry(
                    media_path=media_path,
                    filename=relative,
                    size=(observed_size if cleanup_anchor or recovered else 0),
                    sha256="",
                    mime_type="",
                    available=False,
                    detail="invalid_image",
                    is_cleanup_anchor=cleanup_anchor,
                    is_recovered=recovered,
                )
            )
            continue
        entries.append(
            LocalMediaEntry(
                media_path=media_path,
                filename=relative,
                size=len(content),
                sha256=digest,
                mime_type=_MIME_BY_FORMAT[image_format],
                available=True,
                is_cleanup_anchor=cleanup_anchor,
                is_recovered=recovered,
            )
        )
    entries.sort(key=lambda entry: entry.filename.casefold())
    skipped_entries = tuple(
        sorted(
            {
                (entry.path, entry.reason): entry
                for entry in mutable_skipped_entries
            }.values(),
            key=lambda entry: (entry.path.casefold(), entry.path, entry.reason),
        )
    )
    return LocalMediaScan(
        entries=tuple(entries),
        skipped_symlinks=sum(
            entry.reason == "symlink" for entry in skipped_entries
        ),
        skipped_unsupported=sum(
            entry.reason != "symlink" for entry in skipped_entries
        ),
        invalid=invalid,
        skipped_entries=skipped_entries,
    )


def _ensure_library_directory() -> Path:
    root = LOCAL_MEDIA_ROOT
    try:
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            raise LocalMediaUploadError("storage_unavailable")
        root.mkdir(parents=True, exist_ok=True)
        library = root / LOCAL_MEDIA_LIBRARY_DIR
        if library.exists() and (library.is_symlink() or not library.is_dir()):
            raise LocalMediaUploadError("storage_unavailable")
        library.mkdir(mode=0o700, exist_ok=True)
        root_resolved = root.resolve(strict=True)
        library_resolved = library.resolve(strict=True)
        if not library_resolved.is_relative_to(root_resolved):
            raise LocalMediaUploadError("storage_unavailable")
        return library_resolved
    except OSError as exc:
        raise LocalMediaUploadError("storage_unavailable") from exc


def _open_temporary_stream(file_descriptor: int):
    return os.fdopen(file_descriptor, "wb")


def _sync_temporary_stream(stream: object) -> None:
    stream.flush()
    os.fsync(stream.fileno())


def _atomic_publish(temporary_path: Path, target: Path) -> None:
    os.link(temporary_path, target, follow_symlinks=False)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        directory_fd = os.open(directory, flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise LocalMediaUploadError("storage_unavailable") from exc


def _write_temporary_media(library: Path, content: bytes) -> Path:
    file_descriptor = -1
    stream = None
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=library,
            prefix=".upload-",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        stream = _open_temporary_stream(file_descriptor)
        file_descriptor = -1
        stream.write(content)
        _sync_temporary_stream(stream)
        stream.close()
        stream = None
        return temporary_path
    except BaseException:
        if stream is not None:
            try:
                stream.close()
            except BaseException:
                pass
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _verify_existing_final(
    media_path: str,
    extension: str,
    digest: str,
) -> None:
    try:
        existing = _safe_media_file(media_path)
        existing_content, _ = _read_validated_file(existing, extension)
    except LocalMediaPathError as exc:
        raise LocalMediaUploadError("storage_unavailable") from exc
    if hashlib.sha256(existing_content).hexdigest() != digest:
        raise LocalMediaUploadError("storage_unavailable")


def _publish_media_file(
    library: Path,
    extension: str,
    digest: str,
    content: bytes,
) -> _PublishedMedia | None:
    target = library / f"{digest}{extension}"
    media_path = f"{LOCAL_MEDIA_PREFIX}{LOCAL_MEDIA_LIBRARY_DIR}/{target.name}"
    temporary_path: Path | None = None
    target_created = False
    try:
        temporary_path = _write_temporary_media(library, content)
        try:
            _atomic_publish(temporary_path, target)
        except FileExistsError:
            _verify_existing_final(media_path, extension, digest)
            return None
        target_created = True
        temporary_path.unlink()
        temporary_path = None
        target_stat = target.stat(follow_symlinks=False)
        if not stat.S_ISREG(target_stat.st_mode):
            raise LocalMediaUploadError("storage_unavailable")
        _fsync_directory(library)
        return _PublishedMedia(target, target_stat.st_dev, target_stat.st_ino)
    except BaseException:
        if target_created:
            try:
                target.unlink(missing_ok=True)
                _fsync_directory(library)
            except BaseException:
                pass
        raise
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _rollback_published_media(
    library: Path,
    published: list[_PublishedMedia],
) -> None:
    cleanup_failed = False
    for record in reversed(published):
        try:
            current = record.path.stat(follow_symlinks=False)
            if current.st_dev == record.device and current.st_ino == record.inode:
                record.path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            cleanup_failed = True
    try:
        _fsync_directory(library)
    except LocalMediaUploadError:
        cleanup_failed = True
    if cleanup_failed:
        raise LocalMediaUploadError("storage_unavailable")


async def store_media_uploads(files: list[UploadFile]) -> LocalMediaUploadResult:
    uploads = [upload for upload in files if upload.filename]
    if not uploads:
        raise LocalMediaUploadError("file_required")
    if len(uploads) > MAX_MEDIA_UPLOAD_FILES:
        raise LocalMediaUploadError("too_many_files")

    prepared: list[tuple[str, str, bytes]] = []
    for upload in uploads:
        extension = PurePosixPath(upload.filename or "").suffix.casefold()
        if extension not in ALLOWED_MEDIA_EXTENSIONS:
            raise LocalMediaUploadError("unsupported_type")
        content = await upload.read(MAX_MEDIA_UPLOAD_BYTES + 1)
        if not content:
            raise LocalMediaUploadError("invalid_image")
        if len(content) > MAX_MEDIA_UPLOAD_BYTES:
            raise LocalMediaUploadError("file_too_large")
        image_format = _validated_image_format(content, extension)
        declared_mime = (upload.content_type or "").split(";", 1)[0].strip().casefold()
        if declared_mime != _MIME_BY_FORMAT[image_format]:
            raise LocalMediaUploadError("mime_mismatch")
        prepared.append((extension, hashlib.sha256(content).hexdigest(), content))

    try:
        scan = scan_local_media()
    except LocalMediaPathError as exc:
        raise LocalMediaUploadError("storage_unavailable") from exc
    paths_by_hash = {
        entry.sha256: entry.media_path
        for entry in scan.entries
        if entry.available and entry.sha256
    }
    library = _ensure_library_directory()
    uploaded = 0
    duplicate = 0
    media_paths: list[str] = []
    published: list[_PublishedMedia] = []
    try:
        for extension, digest, content in prepared:
            existing_path = paths_by_hash.get(digest)
            if existing_path is not None:
                duplicate += 1
                media_paths.append(existing_path)
                continue
            media_path = (
                f"{LOCAL_MEDIA_PREFIX}{LOCAL_MEDIA_LIBRARY_DIR}/"
                f"{digest}{extension}"
            )
            created = _publish_media_file(
                library,
                extension,
                digest,
                content,
            )
            if created is None:
                duplicate += 1
            else:
                published.append(created)
                uploaded += 1
            paths_by_hash[digest] = media_path
            media_paths.append(media_path)
    except BaseException as exc:
        try:
            _rollback_published_media(library, published)
        except LocalMediaUploadError as cleanup_exc:
            raise cleanup_exc from exc
        if isinstance(exc, LocalMediaUploadError):
            raise
        if isinstance(exc, Exception):
            raise LocalMediaUploadError("storage_unavailable") from exc
        raise
    return LocalMediaUploadResult(uploaded, duplicate, tuple(media_paths))
