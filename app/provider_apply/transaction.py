"""Transactional application of signed Provider apply plans."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from sqlalchemy import bindparam, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Item,
    ItemActivity,
    ItemCollection,
    ItemCreator,
    ItemSource,
    ItemTag,
    UTCDateTime,
    UserItemState,
)
from app.provider_apply.contracts import (
    CREATE_FIELD_NAMES,
    MAX_ITEM_TITLE_LENGTH,
    MAX_PROVIDER_APPLY_DUPLICATE_HINTS,
    MAX_PROVIDER_APPLY_STRING_LENGTH,
    PROVIDER_APPLY_RESULT_FORMAT,
    PROVIDER_APPLY_RESULT_VERSION,
    UPDATE_FIELD_NAMES,
    ProviderApplyAction,
    ProviderApplyCommitStatus,
    ProviderApplyError,
    ProviderApplyErrorCode,
    ProviderApplyFieldChange,
    ProviderApplyPlan,
    ProviderApplyResult,
)
from app.provider_apply.service import verify_provider_apply_token
from app.services.sources import SourceError, validate_source_tracking_metadata


class _ObservationInvalid(RuntimeError):
    pass


class _PostStateMismatch(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class _AuthorizedProjection:
    action: ProviderApplyAction
    written_fields: tuple[str, ...]
    title: str
    summary: str | None
    release_date: str | None
    source_title: str | None
    provider_key: str
    external_id: str
    normalized_url: str
    last_checked_at: datetime
    metadata_hash: str


@dataclass(frozen=True, slots=True, repr=False)
class _ItemState:
    item_id: int
    title: str
    summary: str | None
    release_date: str | None
    cover_path: str | None
    extra: str | None


@dataclass(frozen=True, slots=True, repr=False)
class _SourceState:
    source_id: int
    item_id: int
    url: str
    normalized_url: str
    title: str | None
    provider_key: str | None
    external_id: str | None
    last_checked_at: datetime | None
    metadata_hash: str | None


@dataclass(frozen=True, slots=True, repr=False)
class _DatabaseObservation:
    identity_sources: tuple[_SourceState, ...]
    url_sources: tuple[_SourceState, ...]
    item: _ItemState | None
    duplicate_title_item_ids: tuple[int, ...]
    related_rows_absent: bool | None


@dataclass(frozen=True, slots=True, repr=False)
class _ExpectedDatabaseState:
    item: _ItemState | None
    source: _SourceState | None
    duplicate_title_item_ids: tuple[int, ...]
    duplicate_excluded_item_id: int | None
    require_related_rows_absent: bool
    absent_item_id: int | None = None
    absent_source_id: int | None = None


@dataclass(slots=True, repr=False)
class _MutationIds:
    item_id: int | None = None
    source_id: int | None = None


def _raise(code: ProviderApplyErrorCode) -> None:
    raise ProviderApplyError(code) from None


def _required_text(value: object, *, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return value


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > maximum:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return value


def _release_date(value: object) -> str | None:
    parsed_value = _optional_text(value, maximum=32)
    if parsed_value is None:
        return None
    try:
        parsed = date.fromisoformat(parsed_value)
    except ValueError:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    if parsed.isoformat() != parsed_value:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return parsed_value


def _datetime(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    normalized = parsed.astimezone(UTC)
    canonical = normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if canonical != value:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return normalized


def _change_map(plan: ProviderApplyPlan) -> dict[str, ProviderApplyFieldChange]:
    if type(plan.field_changes) is not tuple or not all(
        type(change) is ProviderApplyFieldChange for change in plan.field_changes
    ):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    changes = {change.field_name: change for change in plan.field_changes}
    if len(changes) != len(plan.field_changes):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return changes


def _authorized_projection(plan: object) -> _AuthorizedProjection:
    if type(plan) is not ProviderApplyPlan:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    if plan.has_writes is not True:
        _raise(ProviderApplyErrorCode.NOTHING_TO_APPLY)
    if plan.action not in {
        ProviderApplyAction.CREATE_ITEM,
        ProviderApplyAction.UPDATE_ITEM,
    }:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)

    changes = _change_map(plan)
    expected_fields = (
        CREATE_FIELD_NAMES
        if plan.action is ProviderApplyAction.CREATE_ITEM
        else UPDATE_FIELD_NAMES
    )
    if tuple(changes) != expected_fields:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    written_fields = tuple(
        change.field_name for change in plan.field_changes if change.will_write
    )
    if not written_fields:
        _raise(ProviderApplyErrorCode.NOTHING_TO_APPLY)

    if plan.action is ProviderApplyAction.CREATE_ITEM:
        if (
            plan.item_snapshot.item_id is not None
            or plan.source_snapshot.source_id is not None
            or plan.source_snapshot.item_id is not None
        ):
            _raise(ProviderApplyErrorCode.PLAN_INVALID)
        allowed_writes = frozenset(CREATE_FIELD_NAMES)
    else:
        if (
            plan.item_snapshot.item_id is None
            or plan.source_snapshot.source_id is None
            or plan.source_snapshot.item_id != plan.item_snapshot.item_id
        ):
            _raise(ProviderApplyErrorCode.PLAN_INVALID)
        allowed_writes = frozenset(
            {
                "item.summary",
                "item.release_date",
                "item_source.last_checked_at",
                "item_source.metadata_hash",
            }
        )
    if any(field not in allowed_writes for field in written_fields):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)

    title = _required_text(
        changes["item.title"].proposed_value,
        maximum=MAX_ITEM_TITLE_LENGTH,
    )
    summary = _optional_text(
        changes["item.summary"].proposed_value,
        maximum=MAX_PROVIDER_APPLY_STRING_LENGTH,
    )
    release_date = _release_date(changes["item.release_date"].proposed_value)
    checked_at = _datetime(
        changes["item_source.last_checked_at"].proposed_value
    )
    metadata_hash = _required_text(
        changes["item_source.metadata_hash"].proposed_value,
        maximum=96,
    )
    if metadata_hash != plan.apply_projection_hash:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)

    source_title: str | None = None
    if plan.action is ProviderApplyAction.CREATE_ITEM:
        source_url = changes["item_source.url"].proposed_value
        normalized_url = changes["item_source.normalized_url"].proposed_value
        source_title = _required_text(
            changes["item_source.title"].proposed_value,
            maximum=MAX_ITEM_TITLE_LENGTH,
        )
        if (
            source_url != plan.normalized_source_url
            or normalized_url != plan.normalized_source_url
            or source_title != title
            or changes["item_source.provider_key"].proposed_value
            != plan.provider_key
            or changes["item_source.external_id"].proposed_value
            != plan.external_id
        ):
            _raise(ProviderApplyErrorCode.PLAN_INVALID)

    return _AuthorizedProjection(
        action=plan.action,
        written_fields=written_fields,
        title=title,
        summary=summary,
        release_date=release_date,
        source_title=source_title,
        provider_key=plan.provider_key,
        external_id=plan.external_id,
        normalized_url=plan.normalized_source_url,
        last_checked_at=checked_at,
        metadata_hash=metadata_hash,
    )


def _source_state(row: object) -> _SourceState:
    try:
        (
            source_id,
            item_id,
            url,
            normalized_url,
            title,
            provider_key,
            external_id,
            last_checked_at,
            metadata_hash,
        ) = tuple(row)
    except (TypeError, ValueError):
        raise _ObservationInvalid from None
    if (
        type(source_id) is not int
        or source_id < 1
        or type(item_id) is not int
        or item_id < 1
        or type(url) is not str
        or type(normalized_url) is not str
        or (title is not None and type(title) is not str)
        or (provider_key is not None and type(provider_key) is not str)
        or (external_id is not None and type(external_id) is not str)
        or (
            last_checked_at is not None
            and (
                type(last_checked_at) is not datetime
                or last_checked_at.tzinfo is None
                or last_checked_at.utcoffset() is None
            )
        )
        or (metadata_hash is not None and type(metadata_hash) is not str)
    ):
        raise _ObservationInvalid from None
    normalized_checked = (
        None if last_checked_at is None else last_checked_at.astimezone(UTC)
    )
    return _SourceState(
        source_id,
        item_id,
        url,
        normalized_url,
        title,
        provider_key,
        external_id,
        normalized_checked,
        metadata_hash,
    )


def _item_state(row: object) -> _ItemState:
    try:
        item_id, title, summary, release_date, cover_path, extra = tuple(row)
    except (TypeError, ValueError):
        raise _ObservationInvalid from None
    if (
        type(item_id) is not int
        or item_id < 1
        or type(title) is not str
        or not title
        or (summary is not None and type(summary) is not str)
        or (release_date is not None and type(release_date) is not str)
        or (cover_path is not None and type(cover_path) is not str)
        or (extra is not None and type(extra) is not str)
    ):
        raise _ObservationInvalid from None
    return _ItemState(item_id, title, summary, release_date, cover_path, extra)


def _query_sources(
    db: Session,
    *,
    provider_key: str | None = None,
    external_id: str | None = None,
    normalized_url: str | None = None,
) -> tuple[_SourceState, ...]:
    statement = select(
        ItemSource.id,
        ItemSource.item_id,
        ItemSource.url,
        ItemSource.normalized_url,
        ItemSource.title,
        ItemSource.provider_key,
        ItemSource.external_id,
        ItemSource.last_checked_at,
        ItemSource.metadata_hash,
    )
    if normalized_url is not None:
        statement = statement.where(ItemSource.normalized_url == normalized_url)
    else:
        statement = statement.where(
            ItemSource.provider_key == provider_key,
            ItemSource.external_id == external_id,
        )
    rows = db.execute(statement.order_by(ItemSource.id.asc()).limit(2)).all()
    return tuple(_source_state(row) for row in rows)


def _query_item(db: Session, item_id: int | None) -> _ItemState | None:
    if item_id is None:
        return None
    rows = db.execute(
        select(
            Item.id,
            Item.title,
            Item.summary,
            Item.release_date,
            Item.cover_path,
            Item.extra,
        )
        .where(Item.id == item_id)
        .limit(2)
    ).all()
    if len(rows) > 1:
        raise _ObservationInvalid from None
    return None if not rows else _item_state(rows[0])


def _query_duplicate_ids(
    db: Session,
    *,
    title: str,
    excluded_item_id: int | None,
) -> tuple[int, ...]:
    statement = select(Item.id).where(Item.title == title)
    if excluded_item_id is not None:
        statement = statement.where(Item.id != excluded_item_id)
    values = tuple(
        db.scalars(
            statement.order_by(Item.id.asc()).limit(
                MAX_PROVIDER_APPLY_DUPLICATE_HINTS
            )
        ).all()
    )
    if not all(type(value) is int and value > 0 for value in values):
        raise _ObservationInvalid from None
    return values


def _related_rows_absent(db: Session, item_id: int) -> bool:
    columns = (
        ItemTag.item_id,
        ItemCreator.item_id,
        ItemCollection.item_id,
        UserItemState.item_id,
        ItemActivity.item_id,
    )
    for column in columns:
        if db.scalar(select(column).where(column == item_id).limit(1)) is not None:
            return False
    return True


def _observe(
    db: Session,
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    *,
    item_id: int | None,
    duplicate_excluded_item_id: int | None,
    check_related_rows: bool,
) -> _DatabaseObservation:
    identity_sources = _query_sources(
        db,
        provider_key=plan.provider_key,
        external_id=plan.external_id,
    )
    url_sources = _query_sources(db, normalized_url=plan.normalized_source_url)
    item = _query_item(db, item_id)
    duplicates = _query_duplicate_ids(
        db,
        title=projection.title,
        excluded_item_id=duplicate_excluded_item_id,
    )
    related_rows_absent = (
        _related_rows_absent(db, item_id)
        if check_related_rows and item_id is not None
        else None
    )
    return _DatabaseObservation(
        identity_sources,
        url_sources,
        item,
        duplicates,
        related_rows_absent,
    )


def _validated_pre_state(
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    observation: _DatabaseObservation,
) -> _ExpectedDatabaseState:
    if len(observation.identity_sources) > 1 or len(observation.url_sources) > 1:
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)

    if plan.action is ProviderApplyAction.CREATE_ITEM:
        if observation.identity_sources or observation.url_sources:
            _raise(ProviderApplyErrorCode.STALE_PLAN)
        if observation.duplicate_title_item_ids != plan.duplicate_title_item_ids:
            _raise(ProviderApplyErrorCode.STALE_PLAN)
        return _ExpectedDatabaseState(
            item=None,
            source=None,
            duplicate_title_item_ids=plan.duplicate_title_item_ids,
            duplicate_excluded_item_id=None,
            require_related_rows_absent=False,
        )

    if not observation.identity_sources or not observation.url_sources:
        _raise(ProviderApplyErrorCode.STALE_PLAN)
    identity_source = observation.identity_sources[0]
    url_source = observation.url_sources[0]
    source_snapshot = plan.source_snapshot
    item_snapshot = plan.item_snapshot
    if identity_source != url_source:
        _raise(ProviderApplyErrorCode.STALE_PLAN)
    try:
        validate_source_tracking_metadata(
            provider_key=identity_source.provider_key,
            external_id=identity_source.external_id,
            last_checked_at=identity_source.last_checked_at,
            metadata_hash=identity_source.metadata_hash,
        )
    except SourceError:
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)
    if (
        identity_source.source_id != source_snapshot.source_id
        or identity_source.item_id != source_snapshot.item_id
        or identity_source.provider_key != source_snapshot.provider_key
        or identity_source.external_id != source_snapshot.external_id
        or identity_source.url != source_snapshot.normalized_url
        or identity_source.normalized_url != source_snapshot.normalized_url
        or identity_source.last_checked_at != source_snapshot.last_checked_at
        or identity_source.metadata_hash != source_snapshot.metadata_hash
    ):
        _raise(ProviderApplyErrorCode.STALE_PLAN)
    if observation.item is None:
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)
    if (
        observation.item.item_id != item_snapshot.item_id
        or observation.item.title != item_snapshot.title
        or observation.item.summary != item_snapshot.summary
        or observation.item.release_date != item_snapshot.release_date
    ):
        _raise(ProviderApplyErrorCode.STALE_PLAN)
    if observation.duplicate_title_item_ids != plan.duplicate_title_item_ids:
        _raise(ProviderApplyErrorCode.STALE_PLAN)
    return _ExpectedDatabaseState(
        item=observation.item,
        source=identity_source,
        duplicate_title_item_ids=plan.duplicate_title_item_ids,
        duplicate_excluded_item_id=item_snapshot.item_id,
        require_related_rows_absent=False,
    )


def _id_exists(db: Session, model: type[Item] | type[ItemSource], value: int) -> bool:
    return db.scalar(select(model.id).where(model.id == value).limit(1)) is not None


def _matches_expected_state(
    db: Session,
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    expected: _ExpectedDatabaseState,
) -> bool:
    observation = _observe(
        db,
        plan,
        projection,
        item_id=None if expected.item is None else expected.item.item_id,
        duplicate_excluded_item_id=expected.duplicate_excluded_item_id,
        check_related_rows=expected.require_related_rows_absent,
    )
    expected_sources = () if expected.source is None else (expected.source,)
    if (
        observation.identity_sources != expected_sources
        or observation.url_sources != expected_sources
        or observation.item != expected.item
        or observation.duplicate_title_item_ids
        != expected.duplicate_title_item_ids
    ):
        return False
    if (
        expected.require_related_rows_absent
        and observation.related_rows_absent is not True
    ):
        return False
    if expected.absent_item_id is not None and _id_exists(
        db, Item, expected.absent_item_id
    ):
        return False
    if expected.absent_source_id is not None and _id_exists(
        db, ItemSource, expected.absent_source_id
    ):
        return False
    return True


def _expected_post_state(
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    pre_state: _ExpectedDatabaseState,
    ids: _MutationIds,
) -> _ExpectedDatabaseState:
    if plan.action is ProviderApplyAction.CREATE_ITEM:
        if ids.item_id is None or ids.source_id is None:
            raise _PostStateMismatch from None
        item = _ItemState(
            ids.item_id,
            projection.title,
            projection.summary,
            projection.release_date,
            None,
            None,
        )
        source = _SourceState(
            ids.source_id,
            ids.item_id,
            projection.normalized_url,
            projection.normalized_url,
            projection.source_title,
            projection.provider_key,
            projection.external_id,
            projection.last_checked_at,
            projection.metadata_hash,
        )
        return _ExpectedDatabaseState(
            item=item,
            source=source,
            duplicate_title_item_ids=plan.duplicate_title_item_ids,
            duplicate_excluded_item_id=ids.item_id,
            require_related_rows_absent=True,
        )

    if pre_state.item is None or pre_state.source is None:
        raise _PostStateMismatch from None
    item = pre_state.item
    source = pre_state.source
    written = frozenset(projection.written_fields)
    if "item.summary" in written:
        item = replace(item, summary=projection.summary)
    if "item.release_date" in written:
        item = replace(item, release_date=projection.release_date)
    if "item_source.last_checked_at" in written:
        source = replace(source, last_checked_at=projection.last_checked_at)
    if "item_source.metadata_hash" in written:
        source = replace(source, metadata_hash=projection.metadata_hash)
    return replace(pre_state, item=item, source=source)


def _capture_positive_id(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _apply_create(
    db: Session,
    projection: _AuthorizedProjection,
    ids: _MutationIds,
) -> None:
    written = frozenset(projection.written_fields)
    item_values: dict[str, object] = {"title": projection.title}
    if "item.summary" in written:
        item_values["summary"] = projection.summary
    if "item.release_date" in written:
        item_values["release_date"] = projection.release_date
    item_result = db.execute(insert(Item).values(**item_values))
    db.flush()
    ids.item_id = _capture_positive_id(item_result.inserted_primary_key[0])
    if ids.item_id is None:
        raise _PostStateMismatch from None

    source_result = db.execute(
        insert(ItemSource).values(
            item_id=ids.item_id,
            url=projection.normalized_url,
            normalized_url=projection.normalized_url,
            title=projection.source_title,
            provider_key=projection.provider_key,
            external_id=projection.external_id,
            last_checked_at=projection.last_checked_at,
            metadata_hash=projection.metadata_hash,
        )
    )
    db.flush()
    ids.source_id = _capture_positive_id(source_result.inserted_primary_key[0])
    if ids.source_id is None:
        raise _PostStateMismatch from None


def _execute_exact_update(
    db: Session,
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
) -> None:
    item_id = plan.item_snapshot.item_id
    source_id = plan.source_snapshot.source_id
    if item_id is None or source_id is None:
        raise _PostStateMismatch from None
    written = frozenset(projection.written_fields)

    item_assignments: list[str] = []
    item_parameters: dict[str, object] = {"item_id": item_id}
    if "item.summary" in written:
        item_assignments.append("summary = :item_summary")
        item_parameters["item_summary"] = projection.summary
    if "item.release_date" in written:
        item_assignments.append("release_date = :item_release_date")
        item_parameters["item_release_date"] = projection.release_date
    if item_assignments:
        result = db.execute(
            text(
                "UPDATE items SET "
                + ", ".join(item_assignments)
                + " WHERE id = :item_id"
            ),
            item_parameters,
        )
        if result.rowcount != 1:
            raise _PostStateMismatch from None

    source_assignments: list[str] = []
    source_parameters: dict[str, object] = {"source_id": source_id}
    typed_parameters = []
    if "item_source.last_checked_at" in written:
        source_assignments.append("last_checked_at = :source_last_checked_at")
        source_parameters["source_last_checked_at"] = projection.last_checked_at
        typed_parameters.append(
            bindparam("source_last_checked_at", type_=UTCDateTime())
        )
    if "item_source.metadata_hash" in written:
        source_assignments.append("metadata_hash = :source_metadata_hash")
        source_parameters["source_metadata_hash"] = projection.metadata_hash
    if source_assignments:
        statement = text(
            "UPDATE item_sources SET "
            + ", ".join(source_assignments)
            + " WHERE id = :source_id"
        )
        if typed_parameters:
            statement = statement.bindparams(*typed_parameters)
        result = db.execute(statement, source_parameters)
        if result.rowcount != 1:
            raise _PostStateMismatch from None

    db.flush()


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _integrity_failure(error: Exception) -> bool:
    if isinstance(error, (IntegrityError, sqlite3.IntegrityError)):
        return True
    original = getattr(error, "orig", None)
    return isinstance(original, sqlite3.IntegrityError)


def _independent_outcome(
    factory: Callable[[], Session],
    *,
    write_db: Session,
    write_bind: object,
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    post_state: _ExpectedDatabaseState | None,
    pre_state: _ExpectedDatabaseState | None,
    verify_plan_pre_state: bool = False,
) -> str:
    verification_db: Session | None = None
    original_autoflush: bool | None = None
    outcome = "unknown"
    lifecycle_ok = True
    try:
        candidate = factory()
        if not isinstance(candidate, Session) or candidate is write_db:
            return "unknown"
        verification_db = candidate
        if verification_db.get_bind() is not write_bind:
            return "unknown"
        if (
            not verification_db.is_active
            or verification_db.new
            or verification_db.dirty
            or verification_db.deleted
            or verification_db.in_transaction()
        ):
            return "unknown"
        original_autoflush = verification_db.autoflush
        verification_db.autoflush = False
        if post_state is not None and _matches_expected_state(
            verification_db,
            plan,
            projection,
            post_state,
        ):
            outcome = "post"
        elif pre_state is not None and _matches_expected_state(
            verification_db,
            plan,
            projection,
            pre_state,
        ):
            outcome = "pre"
        elif verify_plan_pre_state:
            observation = _observe(
                verification_db,
                plan,
                projection,
                item_id=plan.item_snapshot.item_id,
                duplicate_excluded_item_id=plan.item_snapshot.item_id,
                check_related_rows=False,
            )
            _validated_pre_state(plan, projection, observation)
            outcome = "pre"
    except Exception:
        outcome = "unknown"
    finally:
        if verification_db is not None:
            if original_autoflush is not None:
                try:
                    verification_db.autoflush = original_autoflush
                except Exception:
                    lifecycle_ok = False
            try:
                verification_db.close()
            except Exception:
                lifecycle_ok = False
    return outcome if lifecycle_ok else "unknown"


def _result(
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    ids: _MutationIds,
    status: ProviderApplyCommitStatus,
) -> ProviderApplyResult:
    item_id = ids.item_id
    source_id = ids.source_id
    if item_id is None or source_id is None:
        _raise(ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN)
    try:
        return ProviderApplyResult(
            format=PROVIDER_APPLY_RESULT_FORMAT,
            version=PROVIDER_APPLY_RESULT_VERSION,
            action=plan.action,
            item_id=item_id,
            source_id=source_id,
            written_fields=projection.written_fields,
            commit_status=status,
        )
    except (TypeError, ValueError):
        _raise(ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN)


def _classify_exception(
    error: Exception,
    *,
    db: Session,
    factory: Callable[[], Session],
    write_bind: object,
    plan: ProviderApplyPlan,
    projection: _AuthorizedProjection,
    pre_state: _ExpectedDatabaseState | None,
    post_state: _ExpectedDatabaseState | None,
    ids: _MutationIds,
    verify_plan_pre_state: bool = False,
) -> ProviderApplyResult:
    _rollback_quietly(db)
    outcome = _independent_outcome(
        factory,
        write_db=db,
        write_bind=write_bind,
        plan=plan,
        projection=projection,
        post_state=post_state,
        pre_state=pre_state,
        verify_plan_pre_state=verify_plan_pre_state,
    )
    if outcome == "post":
        return _result(
            plan,
            projection,
            ids,
            ProviderApplyCommitStatus.COMMITTED_VERIFIED_AFTER_EXCEPTION,
        )
    if outcome == "pre":
        _raise(
            ProviderApplyErrorCode.WRITE_CONFLICT
            if _integrity_failure(error)
            else ProviderApplyErrorCode.WRITE_FAILED
        )
    _raise(ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN)


def apply_provider_apply_token(
    db: Session,
    token: str,
    *,
    secret: bytes,
    context: str,
    now: datetime,
    verification_session_factory: Callable[[], Session],
) -> ProviderApplyResult:
    """Verify and transactionally apply one signed Provider apply token."""

    plan = verify_provider_apply_token(
        token,
        secret=secret,
        context=context,
        now=now,
    )
    projection = _authorized_projection(plan)

    if not isinstance(db, Session) or not callable(verification_session_factory):
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    try:
        if (
            not db.is_active
            or db.new
            or db.dirty
            or db.deleted
            or db.in_transaction()
        ):
            _raise(ProviderApplyErrorCode.INVALID_REQUEST)
        write_bind = db.get_bind()
        if write_bind.dialect.name != "sqlite":
            _raise(ProviderApplyErrorCode.INVALID_REQUEST)
        original_autoflush = db.autoflush
    except ProviderApplyError:
        raise
    except Exception:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)

    ids = _MutationIds(
        item_id=plan.item_snapshot.item_id,
        source_id=plan.source_snapshot.source_id,
    )
    try:
        db.autoflush = False
        try:
            db.execute(text("BEGIN IMMEDIATE"))
        except Exception as error:
            return _classify_exception(
                error,
                db=db,
                factory=verification_session_factory,
                write_bind=write_bind,
                plan=plan,
                projection=projection,
                pre_state=None,
                post_state=None,
                ids=ids,
                verify_plan_pre_state=True,
            )

        try:
            observation = _observe(
                db,
                plan,
                projection,
                item_id=plan.item_snapshot.item_id,
                duplicate_excluded_item_id=plan.item_snapshot.item_id,
                check_related_rows=False,
            )
            pre_state = _validated_pre_state(plan, projection, observation)
        except ProviderApplyError as error:
            _rollback_quietly(db)
            _raise(error.code)
        except Exception:
            _rollback_quietly(db)
            _raise(ProviderApplyErrorCode.UNKNOWN)

        post_state: _ExpectedDatabaseState | None = None
        try:
            if plan.action is ProviderApplyAction.CREATE_ITEM:
                ids.item_id = None
                ids.source_id = None
                _apply_create(db, projection, ids)
            else:
                _execute_exact_update(db, plan, projection)
            post_state = _expected_post_state(plan, projection, pre_state, ids)
            if not _matches_expected_state(
                db,
                plan,
                projection,
                post_state,
            ):
                raise _PostStateMismatch from None
            db.commit()
        except Exception as error:
            classified_pre = pre_state
            if plan.action is ProviderApplyAction.CREATE_ITEM:
                classified_pre = replace(
                    pre_state,
                    absent_item_id=ids.item_id,
                    absent_source_id=ids.source_id,
                )
                if post_state is None and ids.item_id is not None and ids.source_id is not None:
                    try:
                        post_state = _expected_post_state(
                            plan,
                            projection,
                            pre_state,
                            ids,
                        )
                    except Exception:
                        post_state = None
            return _classify_exception(
                error,
                db=db,
                factory=verification_session_factory,
                write_bind=write_bind,
                plan=plan,
                projection=projection,
                pre_state=classified_pre,
                post_state=post_state,
                ids=ids,
            )

        outcome = _independent_outcome(
            verification_session_factory,
            write_db=db,
            write_bind=write_bind,
            plan=plan,
            projection=projection,
            post_state=post_state,
            pre_state=None,
        )
        if outcome != "post":
            _raise(ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN)
        return _result(
            plan,
            projection,
            ids,
            ProviderApplyCommitStatus.COMMITTED,
        )
    finally:
        try:
            db.autoflush = original_autoflush
        except Exception:
            pass


__all__ = ["apply_provider_apply_token"]
