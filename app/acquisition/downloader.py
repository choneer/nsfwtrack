from __future__ import annotations

import hashlib
import asyncio
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.acquisition.contracts import (
    DownloadOpenResult,
    DownloadServiceError,
    DownloadServiceErrorCode,
)
from app.acquisition.registry import AcquisitionRegistry
from app.models import (
    DownloadTaskFact,
    ItemLocalAsset,
    ItemSource,
    MediaIndexEntry,
    MediaIndexState,
    OperationTask,
)
from app.services.media_operation_lock import media_operation_lock
from app.services.media_write_coordination import (
    MediaFilesystemOutcome,
    synchronize_media_index_after_mutation,
)
from app.tasks import PersistentTaskService, TaskState, TaskTransitionError

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
    commit_status: str = "committed_verified"


class _IndependentVerificationFailed(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _DownloadPreState:
    task_state: str
    task_stage: str
    task_version: int
    task_bytes: int
    task_expected_bytes: int | None
    task_mime_type: str | None
    task_sha256: str | None
    lease_owner: str | None
    lease_generation: int
    lease_expires_at: datetime | None
    fact_temp_name: str | None
    fact_temp_device: int | None
    fact_temp_inode: int | None
    fact_resume_offset: int
    target_identity: tuple[int, int, int, str] | None


def _hash_open_file(fd: int, *, chunk_bytes: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, chunk_bytes)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _verify_download_file(
    *,
    media_root: Path,
    relative_path: str,
    expected_size: int,
    expected_sha256: str,
    chunk_bytes: int,
) -> os.stat_result:
    root_fd = parent_fd = file_fd = None
    try:
        root_fd = os.open(media_root, _directory_flags())
        _validate_directory(root_fd)
        parent_fd, basename = _open_target_parent(root_fd, relative_path)
        file_fd = os.open(
            basename,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        identity = os.fstat(file_fd)
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_nlink != 1
            or identity.st_size != expected_size
            or _hash_open_file(file_fd, chunk_bytes=chunk_bytes) != expected_sha256
        ):
            raise _IndependentVerificationFailed
        return identity
    except _IndependentVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentVerificationFailed from error
    finally:
        for descriptor in (file_fd, parent_fd, root_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def _read_target_identity(
    *,
    media_root: Path,
    relative_path: str,
    chunk_bytes: int,
) -> tuple[int, int, int, str] | None:
    root_fd = parent_fd = file_fd = None
    try:
        root_fd = os.open(media_root, _directory_flags())
        _validate_directory(root_fd)
        parent_fd, basename = _open_target_parent(root_fd, relative_path)
        file_fd = os.open(
            basename,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        identity = os.fstat(file_fd)
        if not stat.S_ISREG(identity.st_mode):
            raise _IndependentVerificationFailed
        return (
            identity.st_dev,
            identity.st_ino,
            identity.st_size,
            _hash_open_file(file_fd, chunk_bytes=chunk_bytes),
        )
    except FileNotFoundError:
        return None
    except _IndependentVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentVerificationFailed from error
    finally:
        for descriptor in (file_fd, parent_fd, root_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def _capture_download_pre_state(
    *,
    task: OperationTask,
    fact: DownloadTaskFact,
    media_root: Path,
    relative_path: str,
    chunk_bytes: int,
) -> _DownloadPreState:
    return _DownloadPreState(
        task_state=task.state,
        task_stage=task.stage,
        task_version=task.version,
        task_bytes=task.bytes_processed,
        task_expected_bytes=task.expected_bytes,
        task_mime_type=task.mime_type,
        task_sha256=task.sha256,
        lease_owner=task.lease_owner,
        lease_generation=task.lease_generation,
        lease_expires_at=task.lease_expires_at,
        fact_temp_name=fact.temp_name,
        fact_temp_device=fact.temp_device,
        fact_temp_inode=fact.temp_inode,
        fact_resume_offset=fact.resume_offset,
        target_identity=_read_target_identity(
            media_root=media_root,
            relative_path=relative_path,
            chunk_bytes=chunk_bytes,
        ),
    )


def _verify_download_pre_state(
    bind: object,
    *,
    task_id: int,
    expected: _DownloadPreState,
    media_root: Path,
    relative_path: str,
    chunk_bytes: int,
) -> None:
    try:
        with Session(bind=bind) as verification:
            task = verification.get(OperationTask, task_id)
            fact = verification.get(DownloadTaskFact, task_id)
            link_count = verification.scalar(
                select(func.count())
                .select_from(ItemLocalAsset)
                .where(ItemLocalAsset.task_id == task_id)
            )
            if task is None or fact is None or int(link_count or 0) != 0:
                raise _IndependentVerificationFailed
            actual = _DownloadPreState(
                task_state=task.state,
                task_stage=task.stage,
                task_version=task.version,
                task_bytes=task.bytes_processed,
                task_expected_bytes=task.expected_bytes,
                task_mime_type=task.mime_type,
                task_sha256=task.sha256,
                lease_owner=task.lease_owner,
                lease_generation=task.lease_generation,
                lease_expires_at=task.lease_expires_at,
                fact_temp_name=fact.temp_name,
                fact_temp_device=fact.temp_device,
                fact_temp_inode=fact.temp_inode,
                fact_resume_offset=fact.resume_offset,
                target_identity=_read_target_identity(
                    media_root=media_root,
                    relative_path=relative_path,
                    chunk_bytes=chunk_bytes,
                ),
            )
            if actual != expected:
                raise _IndependentVerificationFailed
    except _IndependentVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentVerificationFailed from error


def _verify_download_committed_state(
    bind: object,
    *,
    task_id: int,
    expected_state: TaskState,
    expected_stage: str,
    expected_version: int,
    lease_owner: str | None,
    lease_generation: int | None,
    media_root: Path,
    relative_path: str,
    item_id: int,
    source_id: int,
    provider_key: str,
    asset_identity_hash: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    chunk_bytes: int,
    require_index: bool = True,
) -> None:
    try:
        with Session(bind=bind) as verification:
            task = verification.get(OperationTask, task_id)
            links = tuple(
                verification.scalars(
                    select(ItemLocalAsset).where(ItemLocalAsset.task_id == task_id)
                ).all()
            )
            index_rows = (
                tuple(
                    verification.scalars(
                        select(MediaIndexEntry).where(
                            MediaIndexEntry.media_path == f"/media/{relative_path}"
                        )
                    ).all()
                )
                if require_index
                else ()
            )
            index_state = verification.get(MediaIndexState, 1) if require_index else None
            if task is None:
                raise _IndependentVerificationFailed("task_missing")
            if (
                task.state != expected_state.value
                or task.stage != expected_stage
                or task.version != expected_version
                or task.item_id != item_id
                or task.source_id != source_id
                or task.provider_key != provider_key
                or task.asset_identity_hash != asset_identity_hash
                or task.relative_target != relative_path
                or task.mime_type != mime_type
                or task.expected_bytes != size_bytes
                or task.bytes_processed != size_bytes
                or task.sha256 != sha256
            ):
                raise _IndependentVerificationFailed("task_facts")
            if len(links) != 1:
                raise _IndependentVerificationFailed("link_count")
            if require_index and len(index_rows) != 1:
                raise _IndependentVerificationFailed("index_count")
            if require_index and (
                index_state is None
                or not index_state.valid
                or index_state.last_scan_result != "success"
            ):
                raise _IndependentVerificationFailed("index_state")
            if expected_state is TaskState.RUNNING:
                if (
                    task.lease_owner != lease_owner
                    or task.lease_generation != lease_generation
                    or task.cancel_requested
                    or task.lease_expires_at is None
                    or task.lease_expires_at <= datetime.now(UTC)
                ):
                    raise _IndependentVerificationFailed("lease")
            elif any(
                value is not None
                for value in (
                    task.lease_owner,
                    task.lease_started_at,
                    task.lease_heartbeat_at,
                    task.lease_expires_at,
                )
            ):
                raise _IndependentVerificationFailed("lease_clear")
            link = links[0]
            if (
                link.item_id != item_id
                or link.source_id != source_id
                or link.provider_key != provider_key
                or link.asset_identity_hash != asset_identity_hash
                or link.relative_path != relative_path
                or link.mime_type != mime_type
                or link.size_bytes != size_bytes
                or link.sha256 != sha256
            ):
                raise _IndependentVerificationFailed("link")
            identity = _verify_download_file(
                media_root=media_root,
                relative_path=relative_path,
                expected_size=size_bytes,
                expected_sha256=sha256,
                chunk_bytes=chunk_bytes,
            )
            if not require_index:
                return
            index = index_rows[0]
            if index.record_type != "media" or not index.valid:
                raise _IndependentVerificationFailed("index_validity")
            if index.mime_type != mime_type:
                raise _IndependentVerificationFailed("index_mime")
            if index.size != size_bytes:
                raise _IndependentVerificationFailed("index_size")
            if index.sha256 != sha256:
                raise _IndependentVerificationFailed("index_sha256")
            if index.device != identity.st_dev or index.inode != identity.st_ino:
                raise _IndependentVerificationFailed("index_identity")
    except _IndependentVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentVerificationFailed from error


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

    def _assert_lease(
        self,
        task_id: int,
        *,
        owner: str,
        generation: int,
        initial: bool = False,
    ) -> OperationTask:
        try:
            with Session(bind=self.db.get_bind()) as verification:
                task = verification.get(OperationTask, task_id)
                now = datetime.now(UTC)
                if (
                    task is not None
                    and task.state == TaskState.RUNNING.value
                    and task.lease_owner == owner
                    and task.lease_generation == generation
                    and task.lease_expires_at is not None
                    and task.lease_expires_at > now
                    and not task.cancel_requested
                ):
                    verification.expunge(task)
                    return task
                if task is not None and not initial:
                    if task.cancel_requested or task.state == TaskState.CANCELLING.value:
                        _raise(DownloadServiceErrorCode.CANCELLED)
                    if task.state == TaskState.PAUSED.value:
                        _raise(DownloadServiceErrorCode.PAUSED)
                    if (
                        task.lease_owner != owner
                        or task.lease_generation != generation
                        or task.lease_expires_at is None
                        or task.lease_expires_at <= now
                    ):
                        _raise(DownloadServiceErrorCode.LEASE_LOST)
        except DownloadServiceError:
            raise
        except Exception:
            _raise(DownloadServiceErrorCode.LEASE_CONFLICT)
        _raise(
            DownloadServiceErrorCode.LEASE_CONFLICT
            if initial
            else DownloadServiceErrorCode.LEASE_LOST
        )

    @staticmethod
    def _lease_ttl(task: OperationTask) -> int:
        if task.lease_expires_at is None:
            return 30
        anchor = task.lease_heartbeat_at or datetime.now(UTC)
        seconds = int((task.lease_expires_at - anchor).total_seconds())
        return max(5, min(300, seconds))

    def _commit_progress(
        self,
        task_id: int,
        *,
        fact: DownloadTaskFact,
        owner: str,
        generation: int,
        ttl_seconds: int,
        bytes_processed: int,
        stage: str,
    ) -> None:
        self._assert_lease(task_id, owner=owner, generation=generation)
        fact.resume_offset = bytes_processed
        try:
            self.tasks.heartbeat(
                task_id,
                owner=owner,
                generation=generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=bytes_processed,
                stage=stage,
            )
            self.db.commit()
        except TaskTransitionError:
            self.db.rollback()
            self._assert_lease(task_id, owner=owner, generation=generation)
            _raise(DownloadServiceErrorCode.LEASE_LOST)
        self._assert_lease(task_id, owner=owner, generation=generation)

    def _write_fenced_chunk(
        self,
        task_id: int,
        *,
        file_fd: int,
        chunk: bytes,
        owner: str,
        generation: int,
        ttl_seconds: int,
        bytes_processed: int,
    ) -> None:
        try:
            # The conditional UPDATE acquires the database write fence before
            # any file byte is written. The transaction remains open until the
            # matching resume offset and chunk are both durable.
            self.tasks.heartbeat(
                task_id,
                owner=owner,
                generation=generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=bytes_processed,
                stage="downloading",
            )
        except TaskTransitionError:
            self.db.rollback()
            self._assert_lease(task_id, owner=owner, generation=generation)
            _raise(DownloadServiceErrorCode.LEASE_LOST)
        view = memoryview(chunk)
        while view:
            written = os.write(file_fd, view)
            if written < 1:
                self.db.rollback()
                _raise(DownloadServiceErrorCode.STORAGE_UNSAFE)
            view = view[written:]
        self.db.execute(
            update(DownloadTaskFact)
            .where(DownloadTaskFact.task_id == task_id)
            .values(resume_offset=bytes_processed)
        )
        self.db.commit()
        self._assert_lease(task_id, owner=owner, generation=generation)

    async def execute(self, task_id: int, *, lease_owner: str, lease_generation: int) -> DownloadExecutionResult:
        lease = self._assert_lease(
            task_id,
            owner=lease_owner,
            generation=lease_generation,
            initial=True,
        )
        ttl_seconds = self._lease_ttl(lease)
        self.db.expire_all()
        task, fact, source = self._load(task_id)
        package = self.registry.require(task.provider_key or "", download=True)
        if hashlib.sha256(source.external_id.encode()).hexdigest() != task.external_identity_hash:
            _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
        if hashlib.sha256(fact.asset_id.encode()).hexdigest() != task.asset_identity_hash:
            _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
        declared_mime = task.mime_type or "application/octet-stream"
        allowed_extensions = _ALLOWED_MIME_EXTENSIONS.get(declared_mime)
        relative_path = task.relative_target or ""
        suffix = PurePosixPath(relative_path).suffix.casefold()
        if allowed_extensions is None or suffix not in allowed_extensions:
            _raise(DownloadServiceErrorCode.TYPE_REJECTED)

        item_id = task.item_id or 0
        source_id = task.source_id or 0
        provider_key = task.provider_key or ""
        asset_identity_hash = task.asset_identity_hash or ""
        external_id = source.external_id
        asset_id = fact.asset_id
        max_bytes = fact.max_bytes
        expected_sha256 = fact.expected_sha256
        expected_bytes = task.expected_bytes
        pre_state = _capture_download_pre_state(
            task=task,
            fact=fact,
            media_root=self.media_root,
            relative_path=relative_path,
            chunk_bytes=self.chunk_bytes,
        )
        media_fd = temp_fd = file_fd = parent_fd = None
        temp_name: str | None = None
        published = False
        total = 0
        digest = hashlib.sha256()
        final_sha256 = ""
        expected_success_version: int | None = None
        try:
            media_fd, temp_fd = self._prepare_roots()
            file_fd, temp_name, offset, digest, existing_header = self._open_temp(temp_fd, fact)
            total = offset
            self._commit_progress(
                task_id,
                fact=fact,
                owner=lease_owner,
                generation=lease_generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=total,
                stage="downloading",
            )
            try:
                response = await asyncio.wait_for(
                    package.adapter.open_asset(
                        external_id,
                        asset_id,
                        offset=offset,
                        timeout_seconds=self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
            if type(response) is not DownloadOpenResult:
                _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
            self._validate_response(response, offset=offset, max_bytes=max_bytes)
            if response.mime_type != declared_mime:
                _raise(DownloadServiceErrorCode.TYPE_REJECTED)
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
                next_total = total + len(chunk)
                if next_total > max_bytes:
                    _raise(DownloadServiceErrorCode.TOO_LARGE)
                self._write_fenced_chunk(
                    task_id,
                    file_fd=file_fd,
                    chunk=chunk,
                    owner=lease_owner,
                    generation=lease_generation,
                    ttl_seconds=ttl_seconds,
                    bytes_processed=next_total,
                )
                if len(header) < 32:
                    header.extend(chunk[: 32 - len(header)])
                digest.update(chunk)
                total = next_total

            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            if total == 0 or total == offset:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if response.content_length is not None and total - offset != response.content_length:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            task = self.tasks.get(task_id)
            fact = self.db.get(DownloadTaskFact, task_id)
            if fact is None:
                _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
            final_sha256 = digest.hexdigest()
            if expected_bytes is not None and total != expected_bytes:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if expected_sha256 is not None and final_sha256 != expected_sha256:
                _raise(DownloadServiceErrorCode.INTEGRITY_FAILED)
            if _detected_mime(bytes(header)) != declared_mime:
                _raise(DownloadServiceErrorCode.TYPE_REJECTED)
            os.fsync(file_fd)
            _validate_temp(file_fd, expected_device=fact.temp_device, expected_inode=fact.temp_inode)
            task.sha256 = final_sha256
            task.expected_bytes = total
            task.mime_type = declared_mime
            self._commit_progress(
                task_id,
                fact=fact,
                owner=lease_owner,
                generation=lease_generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=total,
                stage="verified",
            )

            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            with media_operation_lock() as lock:
                lock.verify()
                self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
                parent_fd, basename = _open_target_parent(media_fd, relative_path)
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
            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            fact = self.db.get(DownloadTaskFact, task_id)
            if fact is None:
                _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
            fact.temp_name = None
            fact.temp_device = None
            fact.temp_inode = None
            self._commit_progress(
                task_id,
                fact=fact,
                owner=lease_owner,
                generation=lease_generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=total,
                stage="published",
            )

            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            try:
                self.db.add(
                    ItemLocalAsset(
                        item_id=item_id,
                        source_id=source_id,
                        task_id=task_id,
                        provider_key=provider_key,
                        asset_identity_hash=asset_identity_hash,
                        relative_path=relative_path,
                        mime_type=declared_mime,
                        size_bytes=total,
                        sha256=final_sha256,
                    )
                )
                fact = self.db.get(DownloadTaskFact, task_id)
                if fact is None:
                    _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
                self._commit_progress(
                    task_id,
                    fact=fact,
                    owner=lease_owner,
                    generation=lease_generation,
                    ttl_seconds=ttl_seconds,
                    bytes_processed=total,
                    stage="db_linked",
                )
            except IntegrityError:
                self.db.rollback()
                _raise(DownloadServiceErrorCode.LINK_FAILED)

            task = self._assert_lease(
                task_id,
                owner=lease_owner,
                generation=lease_generation,
            )
            _verify_download_committed_state(
                self.db.get_bind(),
                task_id=task_id,
                expected_state=TaskState.RUNNING,
                expected_stage="db_linked",
                expected_version=task.version,
                lease_owner=lease_owner,
                lease_generation=lease_generation,
                media_root=self.media_root,
                relative_path=relative_path,
                item_id=item_id,
                source_id=source_id,
                provider_key=provider_key,
                asset_identity_hash=asset_identity_hash,
                mime_type=declared_mime,
                size_bytes=total,
                sha256=final_sha256,
                chunk_bytes=self.chunk_bytes,
                require_index=False,
            )
            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            coordination = synchronize_media_index_after_mutation(
                self.db,
                outcome=MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
                source="asset_download",
            )
            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            task = self.tasks.get(task_id)
            task.error_detail = coordination.status.value if coordination.error_code else None
            fact = self.db.get(DownloadTaskFact, task_id)
            if fact is None:
                _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
            self._commit_progress(
                task_id,
                fact=fact,
                owner=lease_owner,
                generation=lease_generation,
                ttl_seconds=ttl_seconds,
                bytes_processed=total,
                stage="index_coordinated",
            )

            task = self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            _verify_download_committed_state(
                self.db.get_bind(),
                task_id=task_id,
                expected_state=TaskState.RUNNING,
                expected_stage="index_coordinated",
                expected_version=task.version,
                lease_owner=lease_owner,
                lease_generation=lease_generation,
                media_root=self.media_root,
                relative_path=relative_path,
                item_id=item_id,
                source_id=source_id,
                provider_key=provider_key,
                asset_identity_hash=asset_identity_hash,
                mime_type=declared_mime,
                size_bytes=total,
                sha256=final_sha256,
                chunk_bytes=self.chunk_bytes,
            )
            self._assert_lease(task_id, owner=lease_owner, generation=lease_generation)
            self.db.expire_all()
            task = self.tasks.get(task_id)
            task = self.tasks.transition(
                task.id,
                TaskState.SUCCEEDED,
                expected_version=task.version,
                event_type="download_succeeded",
            )
            task.stage = "durable_verified"
            expected_success_version = task.version
            self.db.commit()
            _verify_download_committed_state(
                self.db.get_bind(),
                task_id=task_id,
                expected_state=TaskState.SUCCEEDED,
                expected_stage="durable_verified",
                expected_version=expected_success_version,
                lease_owner=None,
                lease_generation=None,
                media_root=self.media_root,
                relative_path=relative_path,
                item_id=item_id,
                source_id=source_id,
                provider_key=provider_key,
                asset_identity_hash=asset_identity_hash,
                mime_type=declared_mime,
                size_bytes=total,
                sha256=final_sha256,
                chunk_bytes=self.chunk_bytes,
            )
            return DownloadExecutionResult(
                task_id,
                relative_path,
                total,
                final_sha256,
                declared_mime,
            )
        except Exception as caught:
            requires_outcome_proof = not isinstance(caught, DownloadServiceError)
            if isinstance(caught, DownloadServiceError):
                error = caught
            elif isinstance(caught, _IndependentVerificationFailed):
                error = DownloadServiceError(DownloadServiceErrorCode.OUTCOME_UNKNOWN)
            else:
                error = DownloadServiceError(
                    DownloadServiceErrorCode.STORAGE_UNSAFE
                    if isinstance(caught, OSError)
                    else DownloadServiceErrorCode.PROVIDER_ERROR
                )
            if published and error.code not in {
                DownloadServiceErrorCode.LEASE_LOST,
                DownloadServiceErrorCode.LEASE_CONFLICT,
                DownloadServiceErrorCode.CANCELLED,
                DownloadServiceErrorCode.PAUSED,
            }:
                error = DownloadServiceError(DownloadServiceErrorCode.OUTCOME_UNKNOWN)
            lease_failure = error.code in {
                DownloadServiceErrorCode.LEASE_LOST,
                DownloadServiceErrorCode.LEASE_CONFLICT,
            }
            self.db.rollback()
            if published and expected_success_version is not None:
                try:
                    _verify_download_committed_state(
                        self.db.get_bind(),
                        task_id=task_id,
                        expected_state=TaskState.SUCCEEDED,
                        expected_stage="durable_verified",
                        expected_version=expected_success_version,
                        lease_owner=None,
                        lease_generation=None,
                        media_root=self.media_root,
                        relative_path=relative_path,
                        item_id=item_id,
                        source_id=source_id,
                        provider_key=provider_key,
                        asset_identity_hash=asset_identity_hash,
                        mime_type=declared_mime,
                        size_bytes=total,
                        sha256=final_sha256,
                        chunk_bytes=self.chunk_bytes,
                    )
                    return DownloadExecutionResult(
                        task_id,
                        relative_path,
                        total,
                        final_sha256,
                        declared_mime,
                    )
                except _IndependentVerificationFailed:
                    try:
                        task = self.tasks.get(task_id)
                        if (
                            task.state == TaskState.SUCCEEDED.value
                            and task.stage == "durable_verified"
                            and task.version == expected_success_version
                        ):
                            self.tasks.mark_verification_unknown(
                                task_id,
                                expected_version=expected_success_version,
                                expected_stage="durable_verified",
                                event_type="download_verification_unknown",
                            )
                            self.db.commit()
                    except Exception:
                        self.db.rollback()
            if requires_outcome_proof:
                try:
                    _verify_download_pre_state(
                        self.db.get_bind(),
                        task_id=task_id,
                        expected=pre_state,
                        media_root=self.media_root,
                        relative_path=relative_path,
                        chunk_bytes=self.chunk_bytes,
                    )
                    error = DownloadServiceError(DownloadServiceErrorCode.WRITE_FAILED)
                except _IndependentVerificationFailed:
                    error = DownloadServiceError(DownloadServiceErrorCode.OUTCOME_UNKNOWN)
            if not lease_failure:
                try:
                    self.db.expire_all()
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
                not lease_failure
                and error.code is not DownloadServiceErrorCode.PAUSED
                and not published
                and temp_fd is not None
                and temp_name is not None
            ):
                try:
                    os.unlink(temp_name, dir_fd=temp_fd)
                    fact = self.db.get(DownloadTaskFact, task_id)
                    if fact is not None:
                        fact.temp_name = None
                        fact.temp_device = None
                        fact.temp_inode = None
                        fact.resume_offset = 0
                        self.db.commit()
                except Exception:
                    self.db.rollback()
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
