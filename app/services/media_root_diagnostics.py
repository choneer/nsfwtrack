from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_health import audit_local_media


MediaRootStatus = Literal[
    "missing",
    "symlink",
    "not_directory",
    "unreadable",
    "scan_failed",
    "ready",
]


class MediaRootDiagnosticError(ValueError):
    def __init__(self, code: str, *, created: bool = False) -> None:
        self.code = code
        self.created = created
        super().__init__(code)


@dataclass(frozen=True)
class MediaRootIdentity:
    kind: str
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> MediaRootIdentity:
        if stat.S_ISDIR(value.st_mode):
            kind = "directory"
        elif stat.S_ISLNK(value.st_mode):
            kind = "symlink"
        elif stat.S_ISREG(value.st_mode):
            kind = "file"
        else:
            kind = "special"
        return cls(
            kind=kind,
            size=value.st_size,
            device=value.st_dev,
            inode=value.st_ino,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )

    def matches(self, value: os.stat_result) -> bool:
        return self == self.from_stat(value)


@dataclass(frozen=True)
class MediaRootDiagnostic:
    logical_path: str
    status: MediaRootStatus
    parent_identity: MediaRootIdentity | None
    root_identity: MediaRootIdentity | None
    item_reference_count: int
    creator_reference_count: int
    can_initialize: bool

    @property
    def reference_count(self) -> int:
        return self.item_reference_count + self.creator_reference_count


@dataclass(frozen=True)
class MediaRootInitializationResult:
    logical_path: str
    warning_code: str | None = None


@dataclass
class _OpenParentChain:
    parts: tuple[str, ...]
    descriptors: list[int]
    identities: tuple[MediaRootIdentity, ...]

    @property
    def parent_descriptor(self) -> int:
        return self.descriptors[-1]

    @property
    def parent_identity(self) -> MediaRootIdentity:
        return self.identities[-1]

    def close(self) -> None:
        while self.descriptors:
            descriptor = self.descriptors.pop()
            try:
                os.close(descriptor)
            except OSError:
                pass


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _configured_parts() -> tuple[str, ...]:
    configured = local_media.LOCAL_MEDIA_ROOT
    if configured.is_absolute():
        try:
            configured = configured.relative_to(Path.cwd())
        except ValueError as exc:
            raise MediaRootDiagnosticError("unsafe_configuration") from exc
    parts = configured.parts
    if (
        not parts
        or len(parts) > 32
        or any(
            part in {"", ".", ".."}
            or "/" in part
            or "\\" in part
            or len(part.encode("utf-8")) > 255
            for part in parts
        )
    ):
        raise MediaRootDiagnosticError("unsafe_configuration")
    return tuple(parts)


def _open_parent_chain(parts: tuple[str, ...]) -> _OpenParentChain:
    descriptors: list[int] = []
    identities: list[MediaRootIdentity] = []
    flags = _directory_open_flags()
    try:
        descriptor = os.open(".", flags)
        descriptors.append(descriptor)
        identity = MediaRootIdentity.from_stat(os.fstat(descriptor))
        if identity.kind != "directory":
            raise MediaRootDiagnosticError("parent_unavailable")
        identities.append(identity)
        for part in parts[:-1]:
            descriptor = os.open(part, flags, dir_fd=descriptor)
            descriptors.append(descriptor)
            identity = MediaRootIdentity.from_stat(os.fstat(descriptor))
            if identity.kind != "directory":
                raise MediaRootDiagnosticError("parent_unavailable")
            identities.append(identity)
        return _OpenParentChain(
            parts=parts,
            descriptors=descriptors,
            identities=tuple(identities),
        )
    except MediaRootDiagnosticError:
        chain = _OpenParentChain(parts, descriptors, tuple(identities))
        chain.close()
        raise
    except OSError as exc:
        chain = _OpenParentChain(parts, descriptors, tuple(identities))
        chain.close()
        raise MediaRootDiagnosticError("parent_unavailable") from exc


def _verify_parent_chain_mapping(chain: _OpenParentChain) -> None:
    try:
        verification = _open_parent_chain(chain.parts)
    except MediaRootDiagnosticError as exc:
        raise MediaRootDiagnosticError("parent_changed") from exc
    try:
        if verification.identities != chain.identities:
            raise MediaRootDiagnosticError("parent_changed")
    finally:
        verification.close()


def _verify_created_root_mapping(
    chain: _OpenParentChain,
    root_identity: MediaRootIdentity,
) -> None:
    try:
        verification = _open_parent_chain(chain.parts)
    except MediaRootDiagnosticError as exc:
        raise MediaRootDiagnosticError("parent_changed") from exc
    try:
        if len(verification.identities) != len(chain.identities):
            raise MediaRootDiagnosticError("parent_changed")
        for index, (current, original) in enumerate(
            zip(verification.identities, chain.identities, strict=True)
        ):
            if index == len(chain.identities) - 1:
                if (
                    current.kind != "directory"
                    or current.device != original.device
                    or current.inode != original.inode
                ):
                    raise MediaRootDiagnosticError("parent_changed")
            elif current != original:
                raise MediaRootDiagnosticError("parent_changed")
        try:
            mapped_identity = MediaRootIdentity.from_stat(
                os.stat(
                    chain.parts[-1],
                    dir_fd=verification.parent_descriptor,
                    follow_symlinks=False,
                )
            )
        except OSError as exc:
            raise MediaRootDiagnosticError("created_unverified") from exc
        if mapped_identity != root_identity:
            raise MediaRootDiagnosticError("created_unverified")
    finally:
        verification.close()


def _inspect_root_from_parent(
    chain: _OpenParentChain,
) -> tuple[MediaRootStatus, MediaRootIdentity | None]:
    target_name = chain.parts[-1]
    try:
        root_stat = os.stat(
            target_name,
            dir_fd=chain.parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None
    identity = MediaRootIdentity.from_stat(root_stat)
    if identity.kind == "symlink":
        return "symlink", identity
    if identity.kind != "directory":
        return "not_directory", identity

    descriptor: int | None = None
    try:
        descriptor = os.open(
            target_name,
            _directory_open_flags(),
            dir_fd=chain.parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if not identity.matches(opened):
            return "unreadable", identity
        with os.scandir(descriptor):
            pass
    except OSError:
        return "unreadable", identity
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return "ready", identity


def _count_local_references(db: Session) -> tuple[int, int]:
    def is_local(value: str | None) -> bool:
        try:
            return local_media.normalize_local_media_path(value) is not None
        except local_media.LocalMediaPathError:
            return False

    item_count = sum(
        is_local(value)
        for value in db.scalars(
            select(Item.cover_path).where(Item.cover_path.is_not(None))
        )
    )
    creator_count = sum(
        is_local(value)
        for value in db.scalars(
            select(Creator.avatar_path).where(Creator.avatar_path.is_not(None))
        )
    )
    return item_count, creator_count


def _reported_root_status(db: Session) -> MediaRootStatus | None:
    for finding in audit_local_media(db):
        if (
            finding.code == "media_root_unavailable"
            and finding.object_type == "media_root"
            and finding.detail
            in {"missing", "symlink", "not_directory", "unreadable", "scan_failed"}
        ):
            return finding.detail  # type: ignore[return-value]
    return None


def build_media_root_diagnostic(db: Session) -> MediaRootDiagnostic:
    parts = _configured_parts()
    item_count, creator_count = _count_local_references(db)
    parent_identity = None
    root_identity = None
    path_status: MediaRootStatus = "unreadable"
    parent_safe = False
    try:
        chain = _open_parent_chain(parts)
    except MediaRootDiagnosticError:
        chain = None
    if chain is not None:
        try:
            _verify_parent_chain_mapping(chain)
            parent_identity = chain.parent_identity
            path_status, root_identity = _inspect_root_from_parent(chain)
            _verify_parent_chain_mapping(chain)
            parent_safe = True
        except MediaRootDiagnosticError:
            path_status = "unreadable"
            parent_safe = False
        finally:
            chain.close()

    reported_status = _reported_root_status(db)
    status = (
        "scan_failed"
        if path_status == "ready" and reported_status == "scan_failed"
        else path_status
    )
    return MediaRootDiagnostic(
        logical_path=local_media.LOCAL_MEDIA_PREFIX,
        status=status,
        parent_identity=parent_identity,
        root_identity=root_identity,
        item_reference_count=item_count,
        creator_reference_count=creator_count,
        can_initialize=(
            status == "missing"
            and parent_safe
            and parent_identity is not None
        ),
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaRootDiagnosticError("invalid_request")
    raw = str(value)
    if len(raw) > 30 or not raw.isascii() or not raw.isdecimal():
        raise MediaRootDiagnosticError("invalid_request")
    return int(raw)


def _submitted_parent_matches(
    identity: MediaRootIdentity,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        identity.kind == "directory"
        and identity.size == _parse_identity_number(expected_size)
        and identity.device == _parse_identity_number(expected_device)
        and identity.inode == _parse_identity_number(expected_inode)
        and identity.modified_ns == _parse_identity_number(expected_modified_ns)
        and identity.changed_ns == _parse_identity_number(expected_changed_ns)
    )


def execute_media_root_initialization(
    db: Session,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaRootInitializationResult:
    diagnostic = build_media_root_diagnostic(db)
    if diagnostic.status != "missing":
        if diagnostic.parent_identity is None:
            raise MediaRootDiagnosticError("parent_changed")
        raise MediaRootDiagnosticError("root_not_missing")
    if not diagnostic.can_initialize or diagnostic.parent_identity is None:
        raise MediaRootDiagnosticError("parent_unavailable")
    if not _submitted_parent_matches(
        diagnostic.parent_identity,
        expected_size=expected_size,
        expected_device=expected_device,
        expected_inode=expected_inode,
        expected_modified_ns=expected_modified_ns,
        expected_changed_ns=expected_changed_ns,
    ):
        raise MediaRootDiagnosticError("parent_changed")

    parts = _configured_parts()
    chain = _open_parent_chain(parts)
    created = False
    root_descriptor: int | None = None
    try:
        _verify_parent_chain_mapping(chain)
        if chain.parent_identity != diagnostic.parent_identity:
            raise MediaRootDiagnosticError("parent_changed")
        target_name = parts[-1]
        try:
            os.stat(
                target_name,
                dir_fd=chain.parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MediaRootDiagnosticError("root_check_failed") from exc
        else:
            raise MediaRootDiagnosticError("root_not_missing")
        _verify_parent_chain_mapping(chain)
        try:
            os.mkdir(target_name, mode=0o700, dir_fd=chain.parent_descriptor)
            created = True
        except FileExistsError as exc:
            raise MediaRootDiagnosticError("root_not_missing") from exc
        except OSError as exc:
            raise MediaRootDiagnosticError("create_failed") from exc

        try:
            root_descriptor = os.open(
                target_name,
                _directory_open_flags(),
                dir_fd=chain.parent_descriptor,
            )
            opened_identity = MediaRootIdentity.from_stat(
                os.fstat(root_descriptor)
            )
            mapped_identity = MediaRootIdentity.from_stat(
                os.stat(
                    target_name,
                    dir_fd=chain.parent_descriptor,
                    follow_symlinks=False,
                )
            )
            if (
                opened_identity.kind != "directory"
                or mapped_identity != opened_identity
            ):
                raise OSError("created media root identity changed")
        except OSError as exc:
            raise MediaRootDiagnosticError(
                "created_unverified",
                created=True,
            ) from exc

        warning = None
        try:
            os.fsync(root_descriptor)
        except OSError:
            warning = "sync_failed"
        try:
            os.fsync(chain.parent_descriptor)
        except OSError:
            warning = "sync_failed"
        _verify_created_root_mapping(chain, opened_identity)
        return MediaRootInitializationResult(
            logical_path=local_media.LOCAL_MEDIA_PREFIX,
            warning_code=warning,
        )
    except MediaRootDiagnosticError as exc:
        if created and not exc.created:
            raise MediaRootDiagnosticError(exc.code, created=True) from exc
        raise
    finally:
        if root_descriptor is not None:
            try:
                os.close(root_descriptor)
            except OSError:
                pass
        chain.close()
