from __future__ import annotations

import errno
import fcntl
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


MEDIA_OPERATION_LOCK_DIRECTORY = Path(__file__).resolve().parents[2] / "data"
MEDIA_OPERATION_LOCK_FILENAME = ".nsfwtrack-media-operation.lock"
MEDIA_OPERATION_LOCK_TIMEOUT_SECONDS = 1.0
MEDIA_OPERATION_LOCK_POLL_SECONDS = 0.025


class MediaOperationLockError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _LockIdentity:
    mode: int
    device: int
    inode: int
    owner: int
    links: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _LockIdentity:
        return cls(
            mode=value.st_mode,
            device=value.st_dev,
            inode=value.st_ino,
            owner=value.st_uid,
            links=value.st_nlink,
        )


@dataclass
class MediaOperationLock:
    directory_fd: int
    lock_fd: int
    directory_identity: _LockIdentity
    lock_identity: _LockIdentity

    def verify(self) -> None:
        try:
            current_directory = _LockIdentity.from_stat(os.fstat(self.directory_fd))
            mapped_directory = _LockIdentity.from_stat(
                os.stat(MEDIA_OPERATION_LOCK_DIRECTORY, follow_symlinks=False)
            )
            current_lock = _LockIdentity.from_stat(os.fstat(self.lock_fd))
            mapped_lock = _LockIdentity.from_stat(
                os.stat(
                    MEDIA_OPERATION_LOCK_FILENAME,
                    dir_fd=self.directory_fd,
                    follow_symlinks=False,
                )
            )
        except OSError as exc:
            raise MediaOperationLockError("media_lock_changed") from exc
        if (
            not _same_directory_identity(
                current_directory,
                self.directory_identity,
            )
            or not _same_directory_identity(
                mapped_directory,
                self.directory_identity,
            )
            or current_lock != self.lock_identity
            or mapped_lock != self.lock_identity
        ):
            raise MediaOperationLockError("media_lock_changed")
        _validate_directory_identity(current_directory)
        _validate_lock_identity(current_lock)


def media_operation_lock_path() -> Path:
    return MEDIA_OPERATION_LOCK_DIRECTORY / MEDIA_OPERATION_LOCK_FILENAME


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _lock_file_flags() -> int:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _validate_directory_identity(identity: _LockIdentity) -> None:
    if (
        not stat.S_ISDIR(identity.mode)
        or identity.owner != os.geteuid()
        or stat.S_IMODE(identity.mode) & 0o022
    ):
        raise MediaOperationLockError("media_lock_unsafe")


def _same_directory_identity(
    first: _LockIdentity,
    second: _LockIdentity,
) -> bool:
    return (
        stat.S_IFMT(first.mode) == stat.S_IFMT(second.mode)
        and first.device == second.device
        and first.inode == second.inode
        and first.owner == second.owner
    )


def _validate_lock_identity(identity: _LockIdentity) -> None:
    if (
        not stat.S_ISREG(identity.mode)
        or identity.owner != os.geteuid()
        or identity.links != 1
        or stat.S_IMODE(identity.mode) & 0o077
    ):
        raise MediaOperationLockError("media_lock_unsafe")


def _open_lock_objects() -> tuple[int, int, _LockIdentity, _LockIdentity]:
    directory_fd = -1
    lock_fd = -1
    try:
        directory_fd = os.open(MEDIA_OPERATION_LOCK_DIRECTORY, _directory_flags())
        directory_identity = _LockIdentity.from_stat(os.fstat(directory_fd))
        _validate_directory_identity(directory_identity)
        lock_fd = os.open(
            MEDIA_OPERATION_LOCK_FILENAME,
            _lock_file_flags(),
            0o600,
            dir_fd=directory_fd,
        )
        lock_identity = _LockIdentity.from_stat(os.fstat(lock_fd))
        _validate_lock_identity(lock_identity)
        handle = MediaOperationLock(
            directory_fd,
            lock_fd,
            directory_identity,
            lock_identity,
        )
        handle.verify()
        return directory_fd, lock_fd, directory_identity, lock_identity
    except MediaOperationLockError:
        if lock_fd >= 0:
            os.close(lock_fd)
        if directory_fd >= 0:
            os.close(directory_fd)
        raise
    except OSError as exc:
        if lock_fd >= 0:
            os.close(lock_fd)
        if directory_fd >= 0:
            os.close(directory_fd)
        code = (
            "media_lock_unsafe"
            if exc.errno in {errno.ELOOP, errno.EISDIR, errno.ENXIO}
            else "media_lock_unavailable"
        )
        raise MediaOperationLockError(code) from exc


def _try_flock(file_descriptor: int, deadline: float) -> None:
    while True:
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise MediaOperationLockError("media_busy") from None
            time.sleep(MEDIA_OPERATION_LOCK_POLL_SECONDS)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise MediaOperationLockError("media_lock_unavailable") from exc
            if time.monotonic() >= deadline:
                raise MediaOperationLockError("media_busy") from None
            time.sleep(MEDIA_OPERATION_LOCK_POLL_SECONDS)


def _unlock_quietly(file_descriptor: int) -> None:
    try:
        fcntl.flock(file_descriptor, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def media_operation_lock(
    *,
    timeout_seconds: float | None = None,
) -> Iterator[MediaOperationLock]:
    timeout = (
        MEDIA_OPERATION_LOCK_TIMEOUT_SECONDS
        if timeout_seconds is None
        else max(float(timeout_seconds), 0.0)
    )
    directory_fd = -1
    lock_fd = -1
    directory_locked = False
    file_locked = False
    try:
        (
            directory_fd,
            lock_fd,
            directory_identity,
            lock_identity,
        ) = _open_lock_objects()
        deadline = time.monotonic() + timeout
        _try_flock(directory_fd, deadline)
        directory_locked = True
        _try_flock(lock_fd, deadline)
        file_locked = True
        handle = MediaOperationLock(
            directory_fd,
            lock_fd,
            directory_identity,
            lock_identity,
        )
        handle.verify()
        yield handle
    finally:
        if file_locked:
            _unlock_quietly(lock_fd)
        if directory_locked:
            _unlock_quietly(directory_fd)
        if lock_fd >= 0:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass
