from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from fastapi import UploadFile


LOCAL_MEDIA_PREFIX = "/media/"
LOCAL_MEDIA_ROOT = Path("data/media")
LOCAL_MEDIA_LIBRARY_DIR = "library"
ALLOWED_MEDIA_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_MEDIA_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_MEDIA_UPLOAD_FILES = 20
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


@dataclass(frozen=True)
class LocalMediaEntry:
    media_path: str
    filename: str
    size: int
    sha256: str
    mime_type: str
    available: bool
    detail: str = ""


@dataclass(frozen=True)
class LocalMediaScan:
    entries: tuple[LocalMediaEntry, ...]
    skipped_symlinks: int
    skipped_unsupported: int
    invalid: int


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


def delete_validated_local_media_file(record: ValidatedLocalMediaFile) -> None:
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


def _iter_media_files() -> tuple[list[Path], int, int]:
    if not LOCAL_MEDIA_ROOT.exists():
        return [], 0, 0
    root = _root_for_read()
    files: list[Path] = []
    skipped_symlinks = 0
    skipped_unsupported = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError:
            skipped_unsupported += 1
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    skipped_symlinks += 1
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    path = Path(entry.path)
                    if path.suffix.casefold() in ALLOWED_MEDIA_EXTENSIONS:
                        files.append(path)
                    else:
                        skipped_unsupported += 1
                else:
                    skipped_unsupported += 1
            except OSError:
                skipped_unsupported += 1
    return files, skipped_symlinks, skipped_unsupported


def scan_local_media() -> LocalMediaScan:
    files, skipped_symlinks, skipped_unsupported = _iter_media_files()
    entries: list[LocalMediaEntry] = []
    invalid = 0
    root = LOCAL_MEDIA_ROOT.resolve() if LOCAL_MEDIA_ROOT.exists() else LOCAL_MEDIA_ROOT
    for path in files:
        relative = path.relative_to(root).as_posix()
        media_path = f"{LOCAL_MEDIA_PREFIX}{relative}"
        try:
            file_stat = path.stat(follow_symlinks=False)
            if file_stat.st_size > MAX_MEDIA_UPLOAD_BYTES:
                raise LocalMediaPathError("local media file too large")
            content, image_format = _read_validated_file(path, path.suffix.casefold())
            digest = hashlib.sha256(content).hexdigest()
        except (LocalMediaPathError, OSError):
            invalid += 1
            entries.append(
                LocalMediaEntry(
                    media_path=media_path,
                    filename=relative,
                    size=0,
                    sha256="",
                    mime_type="",
                    available=False,
                    detail="invalid_image",
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
            )
        )
    entries.sort(key=lambda entry: entry.filename.casefold())
    return LocalMediaScan(
        entries=tuple(entries),
        skipped_symlinks=skipped_symlinks,
        skipped_unsupported=skipped_unsupported,
        invalid=invalid,
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
