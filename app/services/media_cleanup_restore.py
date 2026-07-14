from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media


class MediaCleanupRestoreError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaCleanupRestoreItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaCleanupRestoreCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaCleanupRestorePreview:
    anchor: local_media.ValidatedLocalMediaFile
    mime_type: str
    item_references: tuple[MediaCleanupRestoreItemReference, ...]
    creator_references: tuple[MediaCleanupRestoreCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)


@dataclass(frozen=True)
class MediaCleanupRestoreResult:
    anchor_path: str
    recovered_path: str
    sha256: str
    migrated_items: int
    migrated_creators: int
    anchor_removed: bool
    anchor_retained_path: str | None = None
    anchor_removal_code: str | None = None


def _normalize_anchor_path(value: str | None) -> str:
    if value is None or not value.strip():
        raise MediaCleanupRestoreError("invalid_request")
    try:
        normalized = local_media.normalize_local_media_path(value)
    except local_media.LocalMediaPathError as exc:
        raise MediaCleanupRestoreError("invalid_request") from exc
    if (
        normalized is None
        or normalized != value
        or not local_media.is_cleanup_anchor_filename(normalized)
        or local_media.is_recovered_media_filename(normalized)
    ):
        raise MediaCleanupRestoreError("not_anchor")
    return normalized


def _normalize_digest(value: str | None) -> str:
    digest = (value or "").strip()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise MediaCleanupRestoreError("invalid_request")
    return digest


def _load_references(
    db: Session,
    media_path: str,
) -> tuple[
    tuple[MediaCleanupRestoreItemReference, ...],
    tuple[MediaCleanupRestoreCreatorReference, ...],
]:
    items = tuple(
        MediaCleanupRestoreItemReference(id=row.id, title=row.title)
        for row in db.execute(
            select(Item.id, Item.title)
            .where(Item.cover_path == media_path)
            .order_by(Item.title, Item.id)
        ).all()
    )
    creators = tuple(
        MediaCleanupRestoreCreatorReference(id=row.id, name=row.name)
        for row in db.execute(
            select(Creator.id, Creator.name)
            .where(Creator.avatar_path == media_path)
            .order_by(Creator.name, Creator.id)
        ).all()
    )
    return items, creators


def build_media_cleanup_restore_preview(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
) -> MediaCleanupRestorePreview:
    normalized = _normalize_anchor_path(media_path)
    digest = _normalize_digest(sha256)
    try:
        scan = local_media.scan_local_media(include_cleanup_anchors=True)
    except local_media.LocalMediaPathError as exc:
        raise MediaCleanupRestoreError("storage_unavailable") from exc
    entry = next(
        (candidate for candidate in scan.entries if candidate.media_path == normalized),
        None,
    )
    if entry is None:
        raise MediaCleanupRestoreError("anchor_not_found")
    if not entry.is_cleanup_anchor:
        raise MediaCleanupRestoreError("not_anchor")
    if not entry.available or not entry.sha256:
        raise MediaCleanupRestoreError("anchor_damaged")
    if entry.sha256 != digest:
        raise MediaCleanupRestoreError("stale_anchor")
    try:
        anchor = local_media.validate_local_media_file(
            normalized,
            expected_sha256=digest,
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaCleanupRestoreError("stale_anchor") from exc
    if anchor.size != entry.size:
        raise MediaCleanupRestoreError("stale_anchor")
    item_references, creator_references = _load_references(db, normalized)
    return MediaCleanupRestorePreview(
        anchor=anchor,
        mime_type=entry.mime_type,
        item_references=item_references,
        creator_references=creator_references,
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaCleanupRestoreError("invalid_request")
    raw = str(value)
    if not raw.isascii() or not raw.isdecimal():
        raise MediaCleanupRestoreError("invalid_request")
    parsed = int(raw)
    if parsed < 0:
        raise MediaCleanupRestoreError("invalid_request")
    return parsed


def _snapshot_matches(
    record: local_media.ValidatedLocalMediaFile,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        record.size == _parse_identity_number(expected_size)
        and record.device == _parse_identity_number(expected_device)
        and record.inode == _parse_identity_number(expected_inode)
        and record.modified_ns == _parse_identity_number(expected_modified_ns)
        and record.changed_ns == _parse_identity_number(expected_changed_ns)
    )


def _same_published_inode(
    anchor: local_media.ValidatedLocalMediaFile,
    recovered: local_media.ValidatedLocalMediaFile,
) -> bool:
    return (
        anchor.sha256 == recovered.sha256
        and anchor.size == recovered.size
        and anchor.device == recovered.device
        and anchor.inode == recovered.inode
        and anchor.modified_ns == recovered.modified_ns
        and anchor.changed_ns == recovered.changed_ns
    )


def _remove_failed_publication(
    recovered: local_media.ValidatedLocalMediaFile,
) -> bool:
    try:
        local_media.delete_validated_local_media_file(recovered)
    except local_media.LocalMediaDeleteError as exc:
        return exc.removed
    except Exception:
        return False
    return True


def _reference_counts(db: Session, media_path: str) -> tuple[int, int]:
    return (
        int(
            db.scalar(
                select(func.count(Item.id)).where(Item.cover_path == media_path)
            )
            or 0
        ),
        int(
            db.scalar(
                select(func.count(Creator.id)).where(
                    Creator.avatar_path == media_path
                )
            )
            or 0
        ),
    )


def execute_media_cleanup_restore(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaCleanupRestoreResult:
    preview = build_media_cleanup_restore_preview(
        db,
        media_path=media_path,
        sha256=sha256,
    )
    if not _snapshot_matches(
        preview.anchor,
        expected_size=expected_size,
        expected_device=expected_device,
        expected_inode=expected_inode,
        expected_modified_ns=expected_modified_ns,
        expected_changed_ns=expected_changed_ns,
    ):
        raise MediaCleanupRestoreError("stale_anchor")

    recovered: local_media.ValidatedLocalMediaFile | None = None
    try:
        recovered = local_media.publish_local_media_recovery(preview.anchor)
        current_anchor = local_media.validate_local_media_file(
            preview.anchor.media_path,
            expected_sha256=preview.anchor.sha256,
        )
    except (
        local_media.LocalMediaPathError,
        local_media.LocalMediaSafetyAnchorError,
    ) as exc:
        if recovered is not None and not _remove_failed_publication(recovered):
            raise MediaCleanupRestoreError("recovery_cleanup_failed") from exc
        raise MediaCleanupRestoreError("publish_failed") from exc
    if (
        current_anchor.device != preview.anchor.device
        or current_anchor.inode != preview.anchor.inode
        or current_anchor.size != preview.anchor.size
        or current_anchor.modified_ns != preview.anchor.modified_ns
        or not _same_published_inode(current_anchor, recovered)
    ):
        if not _remove_failed_publication(recovered):
            raise MediaCleanupRestoreError("recovery_cleanup_failed")
        raise MediaCleanupRestoreError("stale_anchor")

    try:
        item_result = db.execute(
            update(Item)
            .where(Item.cover_path == preview.anchor.media_path)
            .values(cover_path=recovered.media_path)
        )
        creator_result = db.execute(
            update(Creator)
            .where(Creator.avatar_path == preview.anchor.media_path)
            .values(avatar_path=recovered.media_path)
        )
        if any(_reference_counts(db, preview.anchor.media_path)):
            raise MediaCleanupRestoreError("references_remaining")
        verified_anchor = local_media.validate_local_media_file(
            current_anchor.media_path,
            expected_sha256=current_anchor.sha256,
        )
        verified_recovered = local_media.validate_local_media_file(
            recovered.media_path,
            expected_sha256=recovered.sha256,
        )
        if (
            not local_media.same_local_media_file_identity(
                current_anchor,
                verified_anchor,
            )
            or not local_media.same_local_media_file_identity(
                recovered,
                verified_recovered,
            )
            or not _same_published_inode(verified_anchor, verified_recovered)
        ):
            raise MediaCleanupRestoreError("stale_anchor")
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        if not _remove_failed_publication(recovered):
            raise MediaCleanupRestoreError("recovery_cleanup_failed") from exc
        if isinstance(exc, MediaCleanupRestoreError):
            raise
        raise MediaCleanupRestoreError("database_failed") from exc

    migrated_items = max(int(item_result.rowcount or 0), 0)
    migrated_creators = max(int(creator_result.rowcount or 0), 0)
    retained_code: str | None = None
    anchor_removed = False
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        if any(_reference_counts(db, preview.anchor.media_path)):
            retained_code = "references_remaining"
        else:
            try:
                verified_anchor = local_media.validate_local_media_file(
                    current_anchor.media_path,
                    expected_sha256=current_anchor.sha256,
                )
                verified_recovered = local_media.validate_local_media_file(
                    recovered.media_path,
                    expected_sha256=recovered.sha256,
                )
            except local_media.LocalMediaPathError:
                retained_code = "anchor_changed"
            else:
                if (
                    not local_media.same_local_media_file_identity(
                        current_anchor,
                        verified_anchor,
                    )
                    or not local_media.same_local_media_file_identity(
                        recovered,
                        verified_recovered,
                    )
                    or not _same_published_inode(
                        verified_anchor,
                        verified_recovered,
                    )
                ):
                    retained_code = "anchor_changed"
                else:
                    try:
                        local_media.delete_validated_local_media_file(
                            verified_anchor
                        )
                    except local_media.LocalMediaDeleteError as exc:
                        retained_code = exc.code
                        anchor_removed = exc.removed
                    except Exception:
                        retained_code = "delete_failed"
                    else:
                        anchor_removed = True
        db.commit()
    except Exception:
        db.rollback()
        retained_code = retained_code or "reference_check_failed"

    return MediaCleanupRestoreResult(
        anchor_path=preview.anchor.media_path,
        recovered_path=recovered.media_path,
        sha256=recovered.sha256,
        migrated_items=migrated_items,
        migrated_creators=migrated_creators,
        anchor_removed=anchor_removed,
        anchor_retained_path=(None if anchor_removed else preview.anchor.media_path),
        anchor_removal_code=retained_code,
    )
