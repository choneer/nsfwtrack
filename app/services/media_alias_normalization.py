from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.media_hardlink_aliases import (
    MediaAliasCreatorReference,
    MediaAliasItemReference,
    MediaHardlinkAliasGroup,
    build_media_hardlink_alias_groups,
)
from app.services.media_operation_token import (
    MediaOperationTokenError,
    decode_media_operation_token,
    encode_media_operation_token,
)


MAX_MEDIA_ALIAS_NORMALIZATION_PATHS = 20
MediaAliasPathStatus = Literal["keeper", "deleted", "retained"]


class MediaAliasNormalizationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaAliasNormalizationPath:
    record: local_media.ValidatedLocalMediaFile
    item_references: tuple[MediaAliasItemReference, ...]
    creator_references: tuple[MediaAliasCreatorReference, ...]
    is_keeper: bool

    @property
    def item_ids(self) -> tuple[int, ...]:
        return tuple(sorted(reference.id for reference in self.item_references))

    @property
    def creator_ids(self) -> tuple[int, ...]:
        return tuple(sorted(reference.id for reference in self.creator_references))


@dataclass(frozen=True)
class MediaAliasNormalizationPreview:
    device: int
    inode: int
    sha256: str
    keeper_path: str
    paths: tuple[MediaAliasNormalizationPath, ...]
    independent_paths: tuple[str, ...]
    snapshot_token: str

    @property
    def migrated_items(self) -> int:
        return sum(len(path.item_references) for path in self.paths if not path.is_keeper)

    @property
    def migrated_creators(self) -> int:
        return sum(
            len(path.creator_references) for path in self.paths if not path.is_keeper
        )


@dataclass(frozen=True)
class MediaAliasNormalizationPathResult:
    media_path: str
    status: MediaAliasPathStatus
    code: str | None = None


@dataclass(frozen=True)
class MediaAliasNormalizationResult:
    keeper_path: str
    migrated_items: int
    migrated_creators: int
    database_outcome: Literal["committed", "unknown"]
    paths: tuple[MediaAliasNormalizationPathResult, ...]
    warning_code: str | None = None


@dataclass(frozen=True)
class _AliasSnapshotPath:
    media_path: str
    sha256: str
    mode: int
    size: int
    device: int
    inode: int
    modified_ns: int
    changed_ns: int
    mapping_token: str
    item_ids: tuple[int, ...]
    creator_ids: tuple[int, ...]


@dataclass(frozen=True)
class _AliasSnapshot:
    keeper_path: str
    device: int
    inode: int
    sha256: str
    paths: tuple[_AliasSnapshotPath, ...]


def _normalize_paths(
    alias_paths: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if alias_paths is None or len(alias_paths) < 2:
        raise MediaAliasNormalizationError("invalid_group")
    if len(alias_paths) > MAX_MEDIA_ALIAS_NORMALIZATION_PATHS:
        raise MediaAliasNormalizationError("group_too_large")
    normalized: list[str] = []
    for value in alias_paths:
        try:
            path = local_media.normalize_interactive_local_media_path(value)
        except local_media.LocalMediaPathError as exc:
            raise MediaAliasNormalizationError("invalid_group") from exc
        if path is None or path != value:
            raise MediaAliasNormalizationError("invalid_group")
        normalized.append(path)
    if len(set(normalized)) != len(normalized):
        raise MediaAliasNormalizationError("duplicate_path")
    return tuple(normalized)


def _normalize_keeper(keeper_path: str | None, paths: tuple[str, ...]) -> str:
    if keeper_path is None or keeper_path not in paths:
        raise MediaAliasNormalizationError("keeper_not_member")
    return keeper_path


def _find_exact_group(
    groups: tuple[MediaHardlinkAliasGroup, ...],
    paths: tuple[str, ...],
) -> MediaHardlinkAliasGroup:
    selected = set(paths)
    group = next(
        (
            candidate
            for candidate in groups
            if {path.entry.media_path for path in candidate.paths} == selected
        ),
        None,
    )
    if group is None:
        raise MediaAliasNormalizationError("stale_group")
    return group


def _entry_matches_record(
    entry: local_media.LocalMediaEntry,
    record: local_media.ValidatedLocalMediaFile,
) -> bool:
    return (
        entry.available
        and entry.sha256 == record.sha256
        and entry.size == record.size
        and entry.device == record.device
        and entry.inode == record.inode
        and entry.modified_ns == record.modified_ns
        and entry.changed_ns == record.changed_ns
    )


def _snapshot_payload(
    *,
    keeper_path: str,
    group: MediaHardlinkAliasGroup,
    paths: tuple[MediaAliasNormalizationPath, ...],
) -> dict[str, object]:
    return {
        "kind": "media_alias_normalization",
        "version": 1,
        "keeper_path": keeper_path,
        "device": group.device,
        "inode": group.inode,
        "sha256": group.sha256,
        "paths": [
            {
                "media_path": path.record.media_path,
                "sha256": path.record.sha256,
                "mode": path.record.mode,
                "size": path.record.size,
                "device": path.record.device,
                "inode": path.record.inode,
                "modified_ns": path.record.modified_ns,
                "changed_ns": path.record.changed_ns,
                "mapping_token": local_media.local_media_directory_mapping_token(
                    path.record
                ),
                "item_ids": list(path.item_ids),
                "creator_ids": list(path.creator_ids),
            }
            for path in paths
        ],
    }


def build_media_alias_normalization_preview(
    db: Session,
    *,
    alias_paths: list[str] | tuple[str, ...] | None,
    keeper_path: str | None,
    secret_key: str,
) -> MediaAliasNormalizationPreview:
    normalized_paths = _normalize_paths(alias_paths)
    keeper = _normalize_keeper(keeper_path, normalized_paths)
    try:
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError) as exc:
        raise MediaAliasNormalizationError("storage_unavailable") from exc
    groups = build_media_hardlink_alias_groups(db, scan)
    group = _find_exact_group(groups, normalized_paths)
    rows_by_path = {path.entry.media_path: path for path in group.paths}
    validated: list[MediaAliasNormalizationPath] = []
    for media_path in normalized_paths:
        row = rows_by_path[media_path]
        try:
            record = local_media.validate_local_media_file(
                media_path,
                expected_sha256=group.sha256,
            )
        except local_media.LocalMediaPathError as exc:
            raise MediaAliasNormalizationError("stale_group") from exc
        if (
            not _entry_matches_record(row.entry, record)
            or record.device != group.device
            or record.inode != group.inode
        ):
            raise MediaAliasNormalizationError("stale_group")
        validated.append(
            MediaAliasNormalizationPath(
                record=record,
                item_references=row.item_references,
                creator_references=row.creator_references,
                is_keeper=media_path == keeper,
            )
        )
    paths = tuple(validated)
    try:
        token = encode_media_operation_token(
            _snapshot_payload(keeper_path=keeper, group=group, paths=paths),
            secret_key,
        )
    except MediaOperationTokenError as exc:
        raise MediaAliasNormalizationError("snapshot_too_large") from exc
    return MediaAliasNormalizationPreview(
        device=group.device,
        inode=group.inode,
        sha256=group.sha256,
        keeper_path=keeper,
        paths=paths,
        independent_paths=tuple(
            entry.media_path for entry in group.same_sha_independent_paths
        ),
        snapshot_token=token,
    )


def _required_string(payload: dict[str, object], key: str, maximum: int = 600) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise MediaAliasNormalizationError("invalid_snapshot")
    return value


def _number(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MediaAliasNormalizationError("invalid_snapshot")
    return value


def _digest(payload: dict[str, object], key: str) -> str:
    value = _required_string(payload, key, 64).casefold()
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise MediaAliasNormalizationError("invalid_snapshot")
    return value


def _ids(payload: dict[str, object], key: str) -> tuple[int, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) > 10_000:
        raise MediaAliasNormalizationError("invalid_snapshot")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0
        for item in value
    ):
        raise MediaAliasNormalizationError("invalid_snapshot")
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise MediaAliasNormalizationError("invalid_snapshot")
    return result


def _parse_snapshot(token: str, secret_key: str) -> _AliasSnapshot:
    try:
        payload = decode_media_operation_token(token, secret_key)
    except MediaOperationTokenError as exc:
        raise MediaAliasNormalizationError("invalid_snapshot") from exc
    if payload.get("kind") != "media_alias_normalization" or payload.get("version") != 1:
        raise MediaAliasNormalizationError("invalid_snapshot")
    raw_paths = payload.get("paths")
    if not isinstance(raw_paths, list):
        raise MediaAliasNormalizationError("invalid_snapshot")
    if not 2 <= len(raw_paths) <= MAX_MEDIA_ALIAS_NORMALIZATION_PATHS:
        raise MediaAliasNormalizationError("invalid_snapshot")
    paths: list[_AliasSnapshotPath] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, dict):
            raise MediaAliasNormalizationError("invalid_snapshot")
        media_path = _required_string(raw_path, "media_path")
        try:
            normalized = local_media.normalize_interactive_local_media_path(media_path)
        except local_media.LocalMediaPathError as exc:
            raise MediaAliasNormalizationError("invalid_snapshot") from exc
        if normalized != media_path:
            raise MediaAliasNormalizationError("invalid_snapshot")
        paths.append(
            _AliasSnapshotPath(
                media_path=media_path,
                sha256=_digest(raw_path, "sha256"),
                mode=_number(raw_path, "mode"),
                size=_number(raw_path, "size"),
                device=_number(raw_path, "device"),
                inode=_number(raw_path, "inode"),
                modified_ns=_number(raw_path, "modified_ns"),
                changed_ns=_number(raw_path, "changed_ns"),
                mapping_token=_digest(raw_path, "mapping_token"),
                item_ids=_ids(raw_path, "item_ids"),
                creator_ids=_ids(raw_path, "creator_ids"),
            )
        )
    path_names = tuple(path.media_path for path in paths)
    if len(set(path_names)) != len(path_names):
        raise MediaAliasNormalizationError("invalid_snapshot")
    keeper = _required_string(payload, "keeper_path")
    if keeper not in path_names:
        raise MediaAliasNormalizationError("invalid_snapshot")
    snapshot = _AliasSnapshot(
        keeper_path=keeper,
        device=_number(payload, "device"),
        inode=_number(payload, "inode"),
        sha256=_digest(payload, "sha256"),
        paths=tuple(paths),
    )
    if any(
        path.device != snapshot.device
        or path.inode != snapshot.inode
        or path.sha256 != snapshot.sha256
        for path in snapshot.paths
    ):
        raise MediaAliasNormalizationError("invalid_snapshot")
    return snapshot


def _preview_matches_snapshot(
    preview: MediaAliasNormalizationPreview,
    snapshot: _AliasSnapshot,
) -> bool:
    if (
        preview.keeper_path != snapshot.keeper_path
        or preview.device != snapshot.device
        or preview.inode != snapshot.inode
        or preview.sha256 != snapshot.sha256
    ):
        return False
    current = {path.record.media_path: path for path in preview.paths}
    if set(current) != {path.media_path for path in snapshot.paths}:
        return False
    for expected in snapshot.paths:
        path = current[expected.media_path]
        record = path.record
        if (
            record.sha256 != expected.sha256
            or record.mode != expected.mode
            or record.size != expected.size
            or record.device != expected.device
            or record.inode != expected.inode
            or record.modified_ns != expected.modified_ns
            or record.changed_ns != expected.changed_ns
            or local_media.local_media_directory_mapping_token(record)
            != expected.mapping_token
            or path.item_ids != expected.item_ids
            or path.creator_ids != expected.creator_ids
        ):
            return False
    return True


def _reference_state(
    db: Session,
    paths: tuple[str, ...],
) -> tuple[dict[str, tuple[int, ...]], dict[str, tuple[int, ...]]]:
    item_map = {path: [] for path in paths}
    creator_map = {path: [] for path in paths}
    for row in db.execute(
        select(Item.id, Item.cover_path)
        .where(Item.cover_path.in_(paths))
        .order_by(Item.id)
    ):
        item_map[row.cover_path].append(row.id)
    for row in db.execute(
        select(Creator.id, Creator.avatar_path)
        .where(Creator.avatar_path.in_(paths))
        .order_by(Creator.id)
    ):
        creator_map[row.avatar_path].append(row.id)
    return (
        {path: tuple(values) for path, values in item_map.items()},
        {path: tuple(values) for path, values in creator_map.items()},
    )


def _expected_states(
    snapshot: _AliasSnapshot,
) -> tuple[
    dict[str, tuple[int, ...]],
    dict[str, tuple[int, ...]],
    dict[str, tuple[int, ...]],
    dict[str, tuple[int, ...]],
]:
    original_items = {path.media_path: path.item_ids for path in snapshot.paths}
    original_creators = {path.media_path: path.creator_ids for path in snapshot.paths}
    all_item_ids = tuple(sorted(value for path in snapshot.paths for value in path.item_ids))
    all_creator_ids = tuple(
        sorted(value for path in snapshot.paths for value in path.creator_ids)
    )
    committed_items = {
        path.media_path: all_item_ids if path.media_path == snapshot.keeper_path else ()
        for path in snapshot.paths
    }
    committed_creators = {
        path.media_path: (
            all_creator_ids if path.media_path == snapshot.keeper_path else ()
        )
        for path in snapshot.paths
    }
    return original_items, original_creators, committed_items, committed_creators


def _inspect_commit_outcome(snapshot: _AliasSnapshot) -> str:
    paths = tuple(path.media_path for path in snapshot.paths)
    original_items, original_creators, committed_items, committed_creators = (
        _expected_states(snapshot)
    )
    try:
        with SessionLocal() as verification_db:
            current_items, current_creators = _reference_state(verification_db, paths)
    except Exception:
        return "unknown"
    if current_items == original_items and current_creators == original_creators:
        return "not_committed"
    if current_items == committed_items and current_creators == committed_creators:
        return "committed"
    return "unknown"


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _unknown_result(snapshot: _AliasSnapshot) -> MediaAliasNormalizationResult:
    original_items, original_creators, _, _ = _expected_states(snapshot)
    return MediaAliasNormalizationResult(
        keeper_path=snapshot.keeper_path,
        migrated_items=sum(
            len(values)
            for path, values in original_items.items()
            if path != snapshot.keeper_path
        ),
        migrated_creators=sum(
            len(values)
            for path, values in original_creators.items()
            if path != snapshot.keeper_path
        ),
        database_outcome="unknown",
        paths=tuple(
            MediaAliasNormalizationPathResult(
                media_path=path.media_path,
                status=(
                    "keeper"
                    if path.media_path == snapshot.keeper_path
                    else "retained"
                ),
                code=(
                    None
                    if path.media_path == snapshot.keeper_path
                    else "commit_outcome_unknown"
                ),
            )
            for path in snapshot.paths
        ),
        warning_code="commit_outcome_unknown",
    )


def _delete_committed_aliases(
    db: Session,
    snapshot: _AliasSnapshot,
) -> tuple[MediaAliasNormalizationPathResult, ...]:
    paths = tuple(path.media_path for path in snapshot.paths)
    _, _, committed_items, committed_creators = _expected_states(snapshot)
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        current_items, current_creators = _reference_state(db, paths)
    except Exception:
        _rollback_quietly(db)
        return tuple(
            MediaAliasNormalizationPathResult(
                media_path=path.media_path,
                status=(
                    "keeper"
                    if path.media_path == snapshot.keeper_path
                    else "retained"
                ),
                code=(
                    None
                    if path.media_path == snapshot.keeper_path
                    else "reference_check_failed"
                ),
            )
            for path in snapshot.paths
        )
    if current_items != committed_items or current_creators != committed_creators:
        _rollback_quietly(db)
        return tuple(
            MediaAliasNormalizationPathResult(
                media_path=path.media_path,
                status=(
                    "keeper"
                    if path.media_path == snapshot.keeper_path
                    else "retained"
                ),
                code=(
                    None
                    if path.media_path == snapshot.keeper_path
                    else "references_changed"
                ),
            )
            for path in snapshot.paths
        )

    results: list[MediaAliasNormalizationPathResult] = []
    for expected in snapshot.paths:
        if expected.media_path == snapshot.keeper_path:
            results.append(MediaAliasNormalizationPathResult(expected.media_path, "keeper"))
            continue
        try:
            keeper = local_media.validate_local_media_file(
                snapshot.keeper_path,
                expected_sha256=snapshot.sha256,
            )
            alias = local_media.validate_local_media_file(
                expected.media_path,
                expected_sha256=snapshot.sha256,
            )
            if (
                keeper.device != snapshot.device
                or keeper.inode != snapshot.inode
                or alias.device != snapshot.device
                or alias.inode != snapshot.inode
                or local_media.local_media_directory_mapping_token(alias)
                != expected.mapping_token
            ):
                raise local_media.LocalMediaDeleteError("changed")
            local_media.delete_validated_local_media_file(alias)
        except local_media.LocalMediaDeleteError as exc:
            results.append(
                MediaAliasNormalizationPathResult(
                    expected.media_path,
                    "deleted" if exc.removed else "retained",
                    exc.code,
                )
            )
        except (local_media.LocalMediaPathError, OSError):
            results.append(
                MediaAliasNormalizationPathResult(
                    expected.media_path,
                    "retained",
                    "changed",
                )
            )
        else:
            results.append(
                MediaAliasNormalizationPathResult(expected.media_path, "deleted")
            )
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        results = [
            MediaAliasNormalizationPathResult(
                result.media_path,
                result.status,
                result.code or "lock_release_failed",
            )
            if result.status == "deleted"
            else result
            for result in results
        ]
    return tuple(results)


def execute_media_alias_normalization(
    db: Session,
    *,
    snapshot_token: str,
    secret_key: str,
) -> MediaAliasNormalizationResult:
    snapshot = _parse_snapshot(snapshot_token, secret_key)
    alias_paths = tuple(path.media_path for path in snapshot.paths)
    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaAliasNormalizationError("transaction_unavailable") from exc
    try:
        preview = build_media_alias_normalization_preview(
            db,
            alias_paths=alias_paths,
            keeper_path=snapshot.keeper_path,
            secret_key=secret_key,
        )
        if not _preview_matches_snapshot(preview, snapshot):
            raise MediaAliasNormalizationError("stale_preview")
        removal_paths = tuple(
            path for path in alias_paths if path != snapshot.keeper_path
        )
        item_result = db.execute(
            update(Item)
            .where(Item.cover_path.in_(removal_paths))
            .values(cover_path=snapshot.keeper_path)
        )
        creator_result = db.execute(
            update(Creator)
            .where(Creator.avatar_path.in_(removal_paths))
            .values(avatar_path=snapshot.keeper_path)
        )
        _, _, committed_items, committed_creators = _expected_states(snapshot)
        current_items, current_creators = _reference_state(db, alias_paths)
        expected_item_count = sum(
            len(path.item_ids)
            for path in snapshot.paths
            if path.media_path != snapshot.keeper_path
        )
        expected_creator_count = sum(
            len(path.creator_ids)
            for path in snapshot.paths
            if path.media_path != snapshot.keeper_path
        )
        if (
            int(item_result.rowcount or 0) != expected_item_count
            or int(creator_result.rowcount or 0) != expected_creator_count
            or current_items != committed_items
            or current_creators != committed_creators
        ):
            raise MediaAliasNormalizationError("reference_migration_failed")
    except MediaAliasNormalizationError:
        _rollback_quietly(db)
        raise
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaAliasNormalizationError("database_failed") from exc

    try:
        db.commit()
    except Exception as exc:
        _rollback_quietly(db)
        outcome = _inspect_commit_outcome(snapshot)
        if outcome == "not_committed":
            raise MediaAliasNormalizationError("database_failed") from exc
        if outcome != "committed":
            return _unknown_result(snapshot)

    path_results = _delete_committed_aliases(db, snapshot)
    original_items, original_creators, _, _ = _expected_states(snapshot)
    warning_code = (
        "aliases_retained"
        if any(path.status == "retained" for path in path_results)
        else None
    )
    return MediaAliasNormalizationResult(
        keeper_path=snapshot.keeper_path,
        migrated_items=sum(
            len(values)
            for path, values in original_items.items()
            if path != snapshot.keeper_path
        ),
        migrated_creators=sum(
            len(values)
            for path, values in original_creators.items()
            if path != snapshot.keeper_path
        ),
        database_outcome="committed",
        paths=path_results,
        warning_code=warning_code,
    )
