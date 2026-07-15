from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Collection, Literal

from sqlalchemy.orm import Session

from app.services import local_media
from app.services.media_file_rename import (
    MediaFilePathSource,
    MediaFileRenameError,
    MediaFileRenamePreview,
    build_media_file_path_source,
    build_media_file_rename_preview,
    execute_media_file_rename,
    normalize_media_file_target,
)
from app.services.media_operation_token import (
    MediaOperationTokenError,
    decode_media_operation_token,
    encode_media_operation_token,
)


MAX_MEDIA_BATCH_SIZE = 20
MediaBatchOperation = Literal["move", "rename"]
MediaBatchItemStatus = Literal["success", "failed", "source_retained", "unknown"]


class MediaBatchError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaBatchPreviewItem:
    source_info: MediaFilePathSource
    target_basename: str
    target_path: str | None
    operation_preview: MediaFileRenamePreview | None
    snapshot_token: str | None


@dataclass(frozen=True)
class MediaBatchPreview:
    operation: MediaBatchOperation
    items: tuple[MediaBatchPreviewItem, ...]
    target_directory: str | None
    prepared: bool

    @property
    def total_references(self) -> int:
        return sum(item.source_info.reference_count for item in self.items)


@dataclass(frozen=True)
class MediaBatchItemResult:
    status: MediaBatchItemStatus
    source_path: str
    target_path: str
    migrated_items: int
    migrated_creators: int
    source_removed: bool
    code: str | None = None


@dataclass(frozen=True)
class MediaBatchResult:
    operation: MediaBatchOperation
    items: tuple[MediaBatchItemResult, ...]

    def count(self, status: MediaBatchItemStatus) -> int:
        return sum(item.status == status for item in self.items)


@dataclass(frozen=True)
class _ParsedBatchSnapshot:
    operation: MediaBatchOperation
    source_path: str
    target_directory: str | None
    target_basename: str
    target_path: str
    sha256: str
    mode: int
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int
    source_mapping_token: str
    target_mapping_token: str
    item_ids: tuple[int, ...]
    creator_ids: tuple[int, ...]


def _normalize_selected_paths(
    media_paths: list[str] | tuple[str, ...] | None,
    *,
    allowed_paths: Collection[str] | None,
) -> tuple[str, ...]:
    if not media_paths:
        raise MediaBatchError("no_selection")
    if len(media_paths) > MAX_MEDIA_BATCH_SIZE:
        raise MediaBatchError("batch_too_large")
    normalized_paths: list[str] = []
    for value in media_paths:
        try:
            normalized = local_media.normalize_interactive_local_media_path(value)
        except local_media.LocalMediaPathError as exc:
            raise MediaBatchError("invalid_source") from exc
        if normalized is None or normalized != value:
            raise MediaBatchError("invalid_source")
        normalized_paths.append(normalized)
    if len(set(normalized_paths)) != len(normalized_paths):
        raise MediaBatchError("duplicate_source")
    if allowed_paths is not None and not set(normalized_paths).issubset(allowed_paths):
        raise MediaBatchError("selection_outside_page")
    return tuple(normalized_paths)


def _operation(value: str) -> MediaBatchOperation:
    if value not in {"move", "rename"}:
        raise MediaBatchError("invalid_operation")
    return value


def _payload_for_preview(
    operation: MediaBatchOperation,
    preview: MediaFileRenamePreview,
    *,
    target_directory: str | None,
) -> dict[str, object]:
    source = preview.source
    return {
        "kind": "media_batch_path_change",
        "version": 1,
        "operation": operation,
        "source_path": source.media_path,
        "target_directory": target_directory,
        "target_basename": preview.target_basename,
        "target_path": preview.target_media_path,
        "sha256": source.sha256,
        "mode": source.mode,
        "size": source.size,
        "device": source.device,
        "inode": source.inode,
        "modified_ns": source.modified_ns,
        "changed_ns": source.changed_ns,
        "source_mapping_token": local_media.local_media_directory_mapping_token(
            source
        ),
        "target_mapping_token": local_media.local_media_directory_mapping_token(
            preview.target_directory
        ),
        "item_ids": list(preview.item_reference_ids),
        "creator_ids": list(preview.creator_reference_ids),
    }


def build_media_batch_preview(
    db: Session,
    *,
    operation: str,
    media_paths: list[str] | tuple[str, ...] | None,
    target_directory: str | None,
    target_basenames: list[str] | tuple[str, ...] | None,
    allowed_paths: Collection[str] | None,
    secret_key: str,
) -> MediaBatchPreview:
    normalized_operation = _operation(operation)
    selected_paths = _normalize_selected_paths(
        media_paths,
        allowed_paths=allowed_paths,
    )
    prepared = target_basenames is not None
    if prepared and len(target_basenames) != len(selected_paths):
        raise MediaBatchError("invalid_snapshot")
    if normalized_operation == "rename" and target_directory is not None:
        raise MediaBatchError("invalid_target_directory")
    if normalized_operation == "move" and prepared and not target_directory:
        raise MediaBatchError("target_directory_required")

    source_infos: list[MediaFilePathSource] = []
    for media_path in selected_paths:
        try:
            source_infos.append(build_media_file_path_source(db, media_path=media_path))
        except MediaFileRenameError as exc:
            raise MediaBatchError(exc.code) from exc

    names = (
        tuple(target_basenames or ())
        if prepared
        else tuple(PurePosixPath(path).name for path in selected_paths)
    )
    if not prepared:
        return MediaBatchPreview(
            operation=normalized_operation,
            items=tuple(
                MediaBatchPreviewItem(
                    source_info=source_info,
                    target_basename=name,
                    target_path=None,
                    operation_preview=None,
                    snapshot_token=None,
                )
                for source_info, name in zip(source_infos, names, strict=True)
            ),
            target_directory=None,
            prepared=False,
        )

    normalized_targets: list[tuple[str, str, str]] = []
    for source_info, name in zip(source_infos, names, strict=True):
        try:
            normalized_targets.append(
                normalize_media_file_target(
                    source_info.source.media_path,
                    name,
                    target_directory if normalized_operation == "move" else None,
                )
            )
        except MediaFileRenameError as exc:
            raise MediaBatchError(exc.code) from exc
    target_paths = tuple(target[0] for target in normalized_targets)
    if len(set(target_paths)) != len(target_paths):
        raise MediaBatchError("duplicate_target")
    if set(target_paths) & set(selected_paths):
        raise MediaBatchError("selected_target_conflict")

    rows: list[MediaBatchPreviewItem] = []
    for source_info, target in zip(source_infos, normalized_targets, strict=True):
        try:
            preview = build_media_file_rename_preview(
                db,
                media_path=source_info.source.media_path,
                target_basename=target[1],
                target_directory=(
                    target_directory if normalized_operation == "move" else None
                ),
            )
        except MediaFileRenameError as exc:
            raise MediaBatchError(exc.code) from exc
        try:
            token = encode_media_operation_token(
                _payload_for_preview(
                    normalized_operation,
                    preview,
                    target_directory=(
                        preview.target_directory.media_path
                        if normalized_operation == "move"
                        else None
                    ),
                ),
                secret_key,
            )
        except MediaOperationTokenError as exc:
            raise MediaBatchError("snapshot_too_large") from exc
        rows.append(
            MediaBatchPreviewItem(
                source_info=source_info,
                target_basename=preview.target_basename,
                target_path=preview.target_media_path,
                operation_preview=preview,
                snapshot_token=token,
            )
        )
    return MediaBatchPreview(
        operation=normalized_operation,
        items=tuple(rows),
        target_directory=target_directory,
        prepared=True,
    )


def _required_string(payload: dict[str, object], key: str, *, maximum: int = 600) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise MediaBatchError("invalid_snapshot")
    return value


def _identity_number(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MediaBatchError("invalid_snapshot")
    return value


def _digest(payload: dict[str, object], key: str) -> str:
    value = _required_string(payload, key, maximum=64).casefold()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise MediaBatchError("invalid_snapshot")
    return value


def _id_tuple(payload: dict[str, object], key: str) -> tuple[int, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) > 10_000:
        raise MediaBatchError("invalid_snapshot")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise MediaBatchError("invalid_snapshot")
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise MediaBatchError("invalid_snapshot")
    return result


def _parse_snapshot(
    token: str,
    *,
    expected_operation: MediaBatchOperation,
    secret_key: str,
) -> _ParsedBatchSnapshot:
    try:
        payload = decode_media_operation_token(token, secret_key)
    except MediaOperationTokenError as exc:
        raise MediaBatchError("invalid_snapshot") from exc
    if (
        payload.get("kind") != "media_batch_path_change"
        or payload.get("version") != 1
        or payload.get("operation") != expected_operation
    ):
        raise MediaBatchError("invalid_snapshot")
    source_path = _required_string(payload, "source_path")
    target_basename = _required_string(payload, "target_basename", maximum=255)
    target_path = _required_string(payload, "target_path")
    raw_target_directory = payload.get("target_directory")
    if raw_target_directory is not None and not isinstance(raw_target_directory, str):
        raise MediaBatchError("invalid_snapshot")
    target_directory = raw_target_directory
    if expected_operation == "move" and not target_directory:
        raise MediaBatchError("invalid_snapshot")
    if expected_operation == "rename" and target_directory is not None:
        raise MediaBatchError("invalid_snapshot")
    try:
        normalized_source = local_media.normalize_interactive_local_media_path(
            source_path
        )
        normalized_target = normalize_media_file_target(
            source_path,
            target_basename,
            target_directory,
        )[0]
    except (local_media.LocalMediaPathError, MediaFileRenameError) as exc:
        raise MediaBatchError("invalid_snapshot") from exc
    if normalized_source != source_path or normalized_target != target_path:
        raise MediaBatchError("invalid_snapshot")
    return _ParsedBatchSnapshot(
        operation=expected_operation,
        source_path=source_path,
        target_directory=target_directory,
        target_basename=target_basename,
        target_path=target_path,
        sha256=_digest(payload, "sha256"),
        mode=_identity_number(payload, "mode"),
        size=_identity_number(payload, "size"),
        device=_identity_number(payload, "device"),
        inode=_identity_number(payload, "inode"),
        modified_ns=_identity_number(payload, "modified_ns"),
        changed_ns=_identity_number(payload, "changed_ns"),
        source_mapping_token=_digest(payload, "source_mapping_token"),
        target_mapping_token=_digest(payload, "target_mapping_token"),
        item_ids=_id_tuple(payload, "item_ids"),
        creator_ids=_id_tuple(payload, "creator_ids"),
    )


def _matches_original_snapshot(
    current: MediaFileRenamePreview,
    snapshot: _ParsedBatchSnapshot,
) -> bool:
    source = current.source
    return (
        current.target_media_path == snapshot.target_path
        and source.sha256 == snapshot.sha256
        and source.mode == snapshot.mode
        and source.size == snapshot.size
        and source.device == snapshot.device
        and source.inode == snapshot.inode
        and source.modified_ns == snapshot.modified_ns
        and source.changed_ns == snapshot.changed_ns
        and current.item_reference_ids == snapshot.item_ids
        and current.creator_reference_ids == snapshot.creator_ids
        and local_media.local_media_directory_mapping_token(source)
        == snapshot.source_mapping_token
        and local_media.local_media_directory_mapping_token(current.target_directory)
        == snapshot.target_mapping_token
    )


def execute_media_batch(
    db: Session,
    *,
    operation: str,
    snapshot_tokens: list[str] | tuple[str, ...] | None,
    secret_key: str,
) -> MediaBatchResult:
    normalized_operation = _operation(operation)
    if not snapshot_tokens:
        raise MediaBatchError("no_selection")
    if len(snapshot_tokens) > MAX_MEDIA_BATCH_SIZE:
        raise MediaBatchError("batch_too_large")
    snapshots = tuple(
        _parse_snapshot(
            token,
            expected_operation=normalized_operation,
            secret_key=secret_key,
        )
        for token in snapshot_tokens
    )
    source_paths = tuple(snapshot.source_path for snapshot in snapshots)
    target_paths = tuple(snapshot.target_path for snapshot in snapshots)
    if len(set(source_paths)) != len(source_paths):
        raise MediaBatchError("duplicate_source")
    if len(set(target_paths)) != len(target_paths):
        raise MediaBatchError("duplicate_target")
    if set(source_paths) & set(target_paths):
        raise MediaBatchError("selected_target_conflict")

    results: list[MediaBatchItemResult] = []
    for snapshot in snapshots:
        try:
            current = build_media_file_rename_preview(
                db,
                media_path=snapshot.source_path,
                target_basename=snapshot.target_basename,
                target_directory=snapshot.target_directory,
            )
            if not _matches_original_snapshot(current, snapshot):
                raise MediaFileRenameError("stale_preview")
            result = execute_media_file_rename(
                db,
                media_path=current.source.media_path,
                target_basename=current.target_basename,
                target_directory=snapshot.target_directory,
                expected_sha256=current.source.sha256,
                expected_mode=current.source.mode,
                expected_size=current.source.size,
                expected_device=current.source.device,
                expected_inode=current.source.inode,
                expected_modified_ns=current.source.modified_ns,
                expected_changed_ns=current.source.changed_ns,
                expected_item_reference_ids=[
                    str(value) for value in current.item_reference_ids
                ],
                expected_creator_reference_ids=[
                    str(value) for value in current.creator_reference_ids
                ],
                expected_source_directory_token=(
                    local_media.local_media_directory_identity_token(current.source)
                    if snapshot.target_directory is not None
                    else None
                ),
                expected_target_directory_token=(
                    local_media.local_media_directory_identity_token(
                        current.target_directory
                    )
                    if snapshot.target_directory is not None
                    else None
                ),
            )
        except MediaFileRenameError as exc:
            results.append(
                MediaBatchItemResult(
                    status="failed",
                    source_path=snapshot.source_path,
                    target_path=snapshot.target_path,
                    migrated_items=0,
                    migrated_creators=0,
                    source_removed=False,
                    code=exc.code,
                )
            )
            continue
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            results.append(
                MediaBatchItemResult(
                    status="failed",
                    source_path=snapshot.source_path,
                    target_path=snapshot.target_path,
                    migrated_items=0,
                    migrated_creators=0,
                    source_removed=False,
                    code="unexpected_failure",
                )
            )
            continue

        if result.warning_code == "commit_outcome_unknown":
            item_status: MediaBatchItemStatus = "unknown"
        elif not result.source_removed:
            item_status = "source_retained"
        else:
            item_status = "success"
        results.append(
            MediaBatchItemResult(
                status=item_status,
                source_path=result.source_path,
                target_path=result.target_path,
                migrated_items=result.migrated_items,
                migrated_creators=result.migrated_creators,
                source_removed=result.source_removed,
                code=result.warning_code,
            )
        )
    return MediaBatchResult(operation=normalized_operation, items=tuple(results))
