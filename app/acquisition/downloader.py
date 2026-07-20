from __future__ import annotations

import hashlib
import asyncio
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.acquisition.contracts import (
    DownloadOpenResult,
    DownloadServiceError,
    DownloadServiceErrorCode,
)
from app.acquisition.registry import AcquisitionRegistry
from app.models import DownloadTaskFact, ItemLocalAsset, ItemSource, OperationTask
from app.services.media_operation_lock import media_operation_lock
from app.services.media_write_coordination import (
    MediaFilesystemOutcome,
    synchronize_media_index_after_mutation,
)
from app.tasks import PersistentTaskService, TaskState

_ALLOWED_MIME_EXTENSIONS = {
    "image/avif": {".avif"},
    "image/gif": {".gif"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


def _raise(code: DownloadServiceErrorCode) -> None:
    raise DownloadServiceError(code)


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _file_flags(*, create: bool, append: bool = False) -> int:
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    if append:
        flags |= os.O_APPEND
    return flags


def _validate_directory(fd: int) -> os.stat_result:
    value = os.fstat(fd)
    if not stat.S_ISDIR(value.st_mode) or value.st_uid != os.geteuid():
        _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
    return value


def _validate_temp(fd: int, *, expected_device: int | None = None, expected_inode: int | None = None) -> os.stat_result:
    value = os.fstat(fd)
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or value.st_nlink != 1
        or (stat.S_IMODE(value.st_mode) & 0o077) != 0
        or (expected_device is not None and value.st_dev != expected_device)
        or (expected_inode is not None and value.st_ino != expected_inode)
    ):
        _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
    return value


def _open_target_parent(root_fd: int, target: str) -> tuple[int, str]:
    parts = PurePosixPath(target).parts
    if not parts:
        _raise(DownloadServiceErrorCode.TARGET_INVALID)
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, _directory_flags(), dir_fd=current)
            os.close(current)
            current = next_fd
            _validate_directory(current)
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def _detected_mime(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None


@dataclass(frozen=True, slots=True)
class DownloadExecutionResult:
    task_id: int
    relative_path: str
    size_bytes: int
    sha256: str
    mime_type: str


class SafeDownloadExecutor:
    def __init__(
        self,
        db: Session,
        registry: AcquisitionRegistry,
        *,
        media_root: Path,
        temp_root: Path,
        chunk_bytes: int,
        timeout_seconds: int,
        max_concurrency: int,
    ) -> None:
        if (
            not isinstance(db, Session)
            or not isinstance(registry, AcquisitionRegistry)
            or not isinstance(media_root, Path)
            or not isinstance(temp_root, Path)
            or not 4_096 <= chunk_bytes <= 4 * 1024 * 1024
            or not 1 <= timeout_seconds <= 3_600
        ):
            _raise(DownloadServiceErrorCode.INVALID_REQUEST)
        self.db = db
        self.registry = registry
        self.media_root = media_root
        self.temp_root = temp_root
        self.chunk_bytes = chunk_bytes
        self.timeout_seconds = timeout_seconds
        self.tasks = PersistentTaskService(db, max_concurrency=max_concurrency)

    def _load(self, task_id: int) -> tuple[OperationTask, DownloadTaskFact, ItemSource]:
        task = self.tasks.get(task_id)
        fact = self.db.get(DownloadTaskFact, task_id)
        source = self.db.get(ItemSource, task.source_id) if task.source_id else None
        if (
            task.task_type != "asset_download"
            or fact is None
            or source is None
            or task.item_id is None
            or source.item_id != task.item_id
            or source.provider_key != task.provider_key
            or source.external_id is None
        ):
            _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
        return task, fact, source

    def _prepare_roots(self) -> tuple[int, int]:
        try:
            media_parts = self.media_root.absolute().parts
            temp_parts = self.temp_root.absolute().parts
            if (
                media_parts == temp_parts
                or media_parts == temp_parts[: len(media_parts)]
                or temp_parts == media_parts[: len(temp_parts)]
            ):
                _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
            self.media_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.temp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            media_fd = os.open(self.media_root, _directory_flags())
            temp_fd = os.open(self.temp_root, _directory_flags())
            _validate_directory(media_fd)
            _validate_directory(temp_fd)
            if os.fstat(media_fd).st_dev != os.fstat(temp_fd).st_dev:
                _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
            return media_fd, temp_fd
        except DownloadServiceError:
            raise
        except OSError:
            _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)

    def _open_temp(
        self, temp_fd: int, fact: DownloadTaskFact
    ) -> tuple[int, str, int, hashlib._Hash, bytes]:
        try:
            if fact.temp_name is not None:
                fd = os.open(fact.temp_name, _file_flags(create=False, append=True), dir_fd=temp_fd)
                identity = _validate_temp(
                    fd,
                    expected_device=fact.temp_device,
                    expected_inode=fact.temp_inode,
                )
                if identity.st_size != fact.resume_offset:
                    os.close(fd)
                    _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
                digest = hashlib.sha256()
                os.lseek(fd, 0, os.SEEK_SET)
                header = os.read(fd, 32)
                os.lseek(fd, 0, os.SEEK_SET)
                while True:
                    chunk = os.read(fd, self.chunk_bytes)
                    if not chunk:
                        break
                    digest.update(chunk)
                os.lseek(fd, 0, os.SEEK_END)
                return fd, fact.temp_name, identity.st_size, digest, header
            name = f".download-{secrets.token_hex(24)}.tmp"
            fd = os.open(name, _file_flags(create=True), 0o600, dir_fd=temp_fd)
            identity = _validate_temp(fd)
            fact.temp_name = name
            fact.temp_device = identity.st_dev
            fact.temp_inode = identity.st_ino
            fact.resume_offset = 0
            self.db.commit()
            return fd, name, 0, hashlib.sha256(), b""
        except DownloadServiceError:
            raise
        except OSError:
            _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)

    @staticmethod
    def _validate_response(response: DownloadOpenResult, *, offset: int, max_bytes: int) -> None:
        if offset:
            if (
                response.status_code != 206
                or response.range_start != offset
                or response.range_end is None
                or response.range_total is None
            ):
                _raise(DownloadServiceErrorCode.RANGE_INVALID)
            if response.range_end < offset or response.range_end >= response.range_total:
                _raise(DownloadServiceErrorCode.RANGE_INVALID)
        elif response.status_code == 206:
            if (
                response.range_start != 0
                or response.range_end is None
                or response.range_total is None
                or response.range_end >= response.range_total
            ):
                _raise(DownloadServiceErrorCode.RANGE_INVALID)
        if response.content_length is not None and response.content_length + offset > max_bytes:
            _raise(DownloadServiceErrorCode.TOO_LARGE)
        if response.range_total is not None and response.range_total > max_bytes:
            _raise(DownloadServiceErrorCode.TOO_LARGE)
        if (
            response.status_code == 206
            and response.content_length is not None
            and response.range_start is not None
            and response.range_end is not None
            and response.range_end - response.range_start + 1 != response.content_length
        ):
            _raise(DownloadServiceErrorCode.RANGE_INVALID)

    async def execute(self, task_id: int, *, lease_owner: str, lease_generation: int) -> DownloadExecutionResult:
        task, fact, source = self._load(task_id)
        if (
            task.state != TaskState.RUNNING.value
            or task.lease_owner != lease_owner
            or task.lease_generation != lease_generation
        ):
            _raise(DownloadServiceErrorCode.INVALID_REQUEST)
        package = self.registry.require(task.provider_key or "", download=True)
        if hashlib.sha256(source.external_id.encode()).hexdigest() != task.external_identity_hash:
            _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
        if hashlib.sha256(fact.asset_id.encode()).hexdigest() != task.asset_identity_hash:
            _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
        declared_mime = task.mime_type or None
        if declared_mime is None:
            declared_mime = self.db.scalar(
                select(OperationTask.mime_type).where(OperationTask.id == task.id)
            )
        if declared_mime is None:
            declared_mime = "application/octet-stream"
        allowed_extensions = _ALLOWED_MIME_EXTENSIONS.get(declared_mime)
        suffix = PurePosixPath(task.relative_target or "").suffix.casefold()
        if allowed_extensions is None or suffix not in allowed_extensions:
            _raise(DownloadServiceErrorCode.TYPE_REJECTED)

        media_fd = temp_fd = file_fd = None
        temp_name = None
        published = False
        parent_fd = None
        try:
            media_fd, temp_fd = self._prepare_roots()
            file_fd, temp_name, offset, digest, existing_header = self._open_temp(temp_fd, fact)
            try:
                response = await asyncio.wait_for(
                    package.adapter.open_asset(
                        source.external_id,
                        fact.asset_id,
                        offset=offset,
                        timeout_seconds=self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
            if type(response) is not DownloadOpenResult:
                _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
            self._validate_response(response, offset=offset, max_bytes=fact.max_bytes)
            if response.mime_type != declared_mime:
                _raise(DownloadServiceErrorCode.TYPE_REJECTED)
            total = offset
            header = bytearray(existing_header)
            stream = response.chunks.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream.__anext__(),
                        timeout=self.timeout_seconds,
                    )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
                if not isinstance(chunk, bytes) or not chunk or len(chunk) > self.chunk_bytes:
                    _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
                self.db.refresh(task)
                if task.state == TaskState.PAUSED.value:
                    _raise(DownloadServiceErrorCode.PAUSED)
                if task.cancel_requested or task.state == TaskState.CANCELLING.value:
                    _raise(DownloadServiceErrorCode.CANCELLED)
                total += len(chunk)
                if total > fact.max_bytes:
                    _raise(DownloadServiceErrorCode.TOO_LARGE)
                if len(header) < 32:
                    header.extend(chunk[: 32 - len(header)])
                view = memoryview(chunk)
                while view:
                    written = os.write(file_fd, view)
                    if written < 1:
                        _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
                    view = view[written:]
                digest.update(chunk)
                task.bytes_processed = total
                task.stage = "downloading"
                fact.resume_offset = total
                self.db.commit()
            if total == 0 or total == offset:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if response.content_length is not None and total - offset != response.content_length:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if task.expected_bytes is not None and total != task.expected_bytes:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if fact.expected_sha256 is not None and digest.hexdigest() != fact.expected_sha256:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if _detected_mime(bytes(header)) != declared_mime:
                _raise(DownloadServiceErrorCode.TYPE_REJECTED)
            os.fsync(file_fd)
            _validate_temp(file_fd, expected_device=fact.temp_device, expected_inode=fact.temp_inode)
            task.stage = "verified"
            task.sha256 = digest.hexdigest()
            task.expected_bytes = total
            task.mime_type = declared_mime
            self.db.commit()

            with media_operation_lock() as lock:
                lock.verify()
                parent_fd, basename = _open_target_parent(media_fd, task.relative_target or "")
                try:
                    os.link(temp_name, basename, src_dir_fd=temp_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
                except FileExistsError:
                    _raise(DownloadServiceErrorCode.TARGET_EXISTS)
                except OSError:
                    _raise(DownloadServiceErrorCode.PUBLISH_FAILED)
                published = True
                destination = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
                source_identity = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(destination.st_mode)
                    or destination.st_dev != source_identity.st_dev
                    or destination.st_ino != source_identity.st_ino
                    or destination.st_size != total
                ):
                    _raise(DownloadServiceErrorCode.OUTCOME_UNKNOWN)
                os.fsync(parent_fd)
                os.unlink(temp_name, dir_fd=temp_fd)
                temp_name = None
                os.fsync(temp_fd)
                lock.verify()
            task.stage = "published"
            fact.temp_name = None
            fact.temp_device = None
            fact.temp_inode = None
            self.db.commit()

            try:
                self.db.add(
                    ItemLocalAsset(
                        item_id=task.item_id,
                        source_id=task.source_id,
                        task_id=task.id,
                        provider_key=task.provider_key,
                        asset_identity_hash=task.asset_identity_hash,
                        relative_path=task.relative_target,
                        mime_type=declared_mime,
                        size_bytes=total,
                        sha256=digest.hexdigest(),
                    )
                )
                task.stage = "db_linked"
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                _raise(DownloadServiceErrorCode.LINK_FAILED)
            coordination = synchronize_media_index_after_mutation(
                self.db,
                outcome=MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
                source="asset_download",
            )
            task = self.tasks.get(task_id)
            task.stage = "index_coordinated"
            task.error_detail = coordination.status.value if coordination.error_code else None
            self.db.commit()
            task = self.tasks.transition(
                task.id,
                TaskState.SUCCEEDED,
                expected_version=task.version,
                event_type="download_succeeded",
            )
            task.stage = "durable_verified"
            self.db.commit()
            return DownloadExecutionResult(task.id, task.relative_target or "", total, digest.hexdigest(), declared_mime)
        except Exception as caught:
            error = (
                caught
                if isinstance(caught, DownloadServiceError)
                else DownloadServiceError(
                    DownloadServiceErrorCode.STORAGE_UNSAFE
                    if isinstance(caught, OSError)
                    else DownloadServiceErrorCode.PROVIDER_ERROR
                )
            )
            try:
                self.db.rollback()
                task = self.tasks.get(task_id)
                target = (
                    TaskState.CANCELLED
                    if error.code is DownloadServiceErrorCode.CANCELLED
                    else TaskState.OUTCOME_UNKNOWN
                    if published or error.code is DownloadServiceErrorCode.OUTCOME_UNKNOWN
                    else TaskState.FAILED
                )
                if (
                    error.code is not DownloadServiceErrorCode.PAUSED
                    and task.state in {TaskState.RUNNING.value, TaskState.CANCELLING.value}
                ):
                    self.tasks.transition(
                        task.id,
                        target,
                        expected_version=task.version,
                        event_type="download_stopped",
                        error_code=error.code.value,
                    )
                    self.db.commit()
            except Exception:
                self.db.rollback()
            if (
                error.code is not DownloadServiceErrorCode.PAUSED
                and not published
                and temp_fd is not None
                and temp_name is not None
            ):
                try:
                    os.unlink(temp_name, dir_fd=temp_fd)
                    fact.temp_name = None
                    fact.temp_device = None
                    fact.temp_inode = None
                    fact.resume_offset = 0
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    pass
            raise error from None
        finally:
            for descriptor in (parent_fd, file_fd, temp_fd, media_fd):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass


def cleanup_stale_download_temps(
    db: Session,
    *,
    temp_root: Path,
    retention_hours: int,
    now_timestamp: float,
) -> int:
    if (
        not isinstance(db, Session)
        or not isinstance(temp_root, Path)
        or not isinstance(retention_hours, int)
        or not 1 <= retention_hours <= 720
        or not isinstance(now_timestamp, (int, float))
    ):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    try:
        root_fd = os.open(temp_root, _directory_flags())
        _validate_directory(root_fd)
    except OSError:
        return 0
    referenced = set(
        db.scalars(
            select(DownloadTaskFact.temp_name).where(
                DownloadTaskFact.temp_name.is_not(None)
            )
        ).all()
    )
    removed = 0
    cutoff = float(now_timestamp) - retention_hours * 3_600
    try:
        for name in os.listdir(root_fd):
            if (
                not name.startswith(".download-")
                or not name.endswith(".tmp")
                or name in referenced
            ):
                continue
            try:
                value = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(value.st_mode)
                    or value.st_uid != os.geteuid()
                    or value.st_nlink != 1
                    or value.st_mtime >= cutoff
                ):
                    continue
                os.unlink(name, dir_fd=root_fd)
                removed += 1
            except OSError:
                continue
        if removed:
            os.fsync(root_fd)
    finally:
        os.close(root_fd)
    return removed
