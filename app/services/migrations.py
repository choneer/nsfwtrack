from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import inspect, insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.models import (
    DownloadTaskFact,
    DiscoveredAssetFact,
    ItemLocalAsset,
    ItemSource,
    MediaIndexEntry,
    MediaIndexState,
    OperationTask,
    SchemaMigration,
    SourceCheckFact,
    TaskEvent,
)
from app.services.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_MIGRATIONS_TABLE,
)

ITEM_SOURCES_SCHEMA_2_COLUMNS = {
    "id",
    "item_id",
    "url",
    "normalized_url",
    "title",
    "created_at",
}
ITEM_SOURCES_SCHEMA_4_COLUMNS = ITEM_SOURCES_SCHEMA_2_COLUMNS | {
    "provider_key",
    "external_id",
    "last_checked_at",
    "metadata_hash",
}
SOURCE_IDENTITY_INDEX = "uq_item_sources_provider_identity"
TASK_SCHEMA_TABLES = (
    OperationTask,
    TaskEvent,
    DownloadTaskFact,
    SourceCheckFact,
    DiscoveredAssetFact,
    ItemLocalAsset,
)


@dataclass(frozen=True)
class MigrationCheck:
    passed: bool
    message: str


@dataclass(frozen=True)
class MigrationPreview:
    changes: tuple[str, ...]
    warnings: tuple[str, ...] = ()


MigrationCheckCallable = Callable[[Connection], MigrationCheck]
MigrationPreviewCallable = Callable[[Connection], MigrationPreview]
MigrationApplyCallable = Callable[[Connection], None]


@dataclass(frozen=True)
class MigrationStep:
    from_version: int
    to_version: int
    name: str
    preview: MigrationPreviewCallable
    apply: MigrationApplyCallable
    precheck: MigrationCheckCallable
    postcheck: MigrationCheckCallable


class MigrationError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class MigrationRegistry:
    def __init__(self, steps: tuple[MigrationStep, ...] = ()) -> None:
        ordered = tuple(sorted(steps, key=lambda step: step.from_version))
        self._validate(ordered)
        self._steps = ordered
        self._by_from = {step.from_version: step for step in ordered}

    @staticmethod
    def _validate(steps: tuple[MigrationStep, ...]) -> None:
        seen_from: set[int] = set()
        seen_to: set[int] = set()
        for step in steps:
            if (
                type(step.from_version) is not int
                or type(step.to_version) is not int
                or step.from_version < 0
                or step.to_version < 0
            ):
                raise MigrationError("invalid_version")
            if step.to_version <= step.from_version:
                raise MigrationError("invalid_direction", step.name)
            if step.to_version != step.from_version + 1:
                raise MigrationError("version_jump", step.name)
            if not step.name.strip():
                raise MigrationError("invalid_name")
            if step.from_version in seen_from or step.to_version in seen_to:
                raise MigrationError("duplicate_step", step.name)
            if not all(
                callable(callback)
                for callback in (
                    step.preview,
                    step.apply,
                    step.precheck,
                    step.postcheck,
                )
            ):
                raise MigrationError("invalid_callback", step.name)
            seen_from.add(step.from_version)
            seen_to.add(step.to_version)

        for previous, current in zip(steps, steps[1:], strict=False):
            if current.from_version != previous.to_version:
                raise MigrationError("registry_gap", current.name)

    @property
    def steps(self) -> tuple[MigrationStep, ...]:
        return self._steps

    def resolve(self, from_version: int, to_version: int) -> tuple[MigrationStep, ...]:
        if (
            type(from_version) is not int
            or type(to_version) is not int
            or from_version < 0
            or to_version < 0
        ):
            raise MigrationError("invalid_version")
        if from_version > to_version:
            raise MigrationError("downgrade_not_supported")
        if from_version == to_version:
            return ()

        path: list[MigrationStep] = []
        cursor = from_version
        while cursor < to_version:
            step = self._by_from.get(cursor)
            if step is None or step.to_version > to_version:
                raise MigrationError("missing_path", f"{cursor}->{to_version}")
            path.append(step)
            cursor = step.to_version
        return tuple(path)


@dataclass(frozen=True)
class UpgradePlan:
    current_version: int | None
    target_version: int
    state: str
    steps: tuple[MigrationStep, ...] = ()
    error_code: str | None = None

    @property
    def can_preview(self) -> bool:
        return self.state == "ready"


@dataclass(frozen=True)
class StepDryRun:
    from_version: int
    to_version: int
    name: str
    changes: tuple[str, ...]
    warnings: tuple[str, ...]
    precheck_state: str
    precheck_message: str


@dataclass(frozen=True)
class UpgradeDryRun:
    current_version: int | None
    target_version: int
    state: str
    steps: tuple[StepDryRun, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    can_upgrade: bool


@dataclass(frozen=True)
class MigrationApplyResult:
    from_version: int
    to_version: int
    applied_steps: tuple[str, ...]


def _read_database_version(connection: Connection) -> int:
    try:
        inspector = inspect(connection)
        if SCHEMA_MIGRATIONS_TABLE not in inspector.get_table_names():
            raise MigrationError("version_unknown")
        columns = {
            column["name"]
            for column in inspector.get_columns(SCHEMA_MIGRATIONS_TABLE)
        }
        if not {"version", "name", "applied_at"}.issubset(columns):
            raise MigrationError("version_unknown")
        value = connection.scalar(
            select(SchemaMigration.version)
            .order_by(SchemaMigration.version.desc())
            .limit(1)
        )
    except MigrationError:
        raise
    except (SQLAlchemyError, TypeError, ValueError):
        raise MigrationError("version_unknown") from None
    if value is None:
        raise MigrationError("version_unknown")
    try:
        version = int(value)
    except (TypeError, ValueError):
        raise MigrationError("version_unknown") from None
    if version < 0:
        raise MigrationError("version_unknown")
    return version


def build_upgrade_plan(
    bind: Engine,
    registry: MigrationRegistry,
    *,
    target_version: int = CURRENT_SCHEMA_VERSION,
) -> UpgradePlan:
    try:
        with bind.connect() as connection:
            current_version = _read_database_version(connection)
    except MigrationError as exc:
        return UpgradePlan(
            current_version=None,
            target_version=target_version,
            state="unknown",
            error_code=exc.code,
        )

    if current_version == target_version:
        return UpgradePlan(
            current_version=current_version,
            target_version=target_version,
            state="current",
        )
    if current_version > target_version:
        return UpgradePlan(
            current_version=current_version,
            target_version=target_version,
            state="application_outdated",
            error_code="downgrade_not_supported",
        )
    try:
        steps = registry.resolve(current_version, target_version)
    except MigrationError as exc:
        return UpgradePlan(
            current_version=current_version,
            target_version=target_version,
            state="missing_path",
            error_code=exc.code,
        )
    return UpgradePlan(
        current_version=current_version,
        target_version=target_version,
        state="ready",
        steps=steps,
    )


_SQLITE_READ_ACTIONS = {
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_RECURSIVE,
    sqlite3.SQLITE_SAVEPOINT,
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_TRANSACTION,
}
_SQLITE_SCHEMA_READ_PRAGMAS = {
    "foreign_key_list",
    "index_info",
    "index_list",
    "index_xinfo",
    "table_info",
    "table_xinfo",
}


@contextmanager
def _read_only_connection(bind: Engine) -> Iterator[Connection]:
    if bind.dialect.name != "sqlite":
        raise MigrationError("unsupported_database")
    with bind.connect() as connection:
        driver_connection = connection.connection.driver_connection
        if not isinstance(driver_connection, sqlite3.Connection):
            raise MigrationError("unsupported_database")
        original_query_only = int(
            connection.exec_driver_sql("PRAGMA query_only").scalar_one()
        )
        connection.rollback()
        connection.exec_driver_sql("PRAGMA query_only = ON")
        connection.commit()

        def authorize(
            action: int,
            first: str | None,
            second: str | None,
            database: str | None,
            source: str | None,
        ) -> int:
            del database, source
            if action in _SQLITE_READ_ACTIONS:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_PRAGMA and (
                second is None
                or (first or "").casefold() in _SQLITE_SCHEMA_READ_PRAGMAS
            ):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        driver_connection.set_authorizer(authorize)
        try:
            yield connection
        finally:
            connection.rollback()
            driver_connection.set_authorizer(None)
            connection.exec_driver_sql(
                f"PRAGMA query_only = {1 if original_query_only else 0}"
            )
            connection.commit()


def preview_upgrade(
    bind: Engine,
    registry: MigrationRegistry,
    *,
    target_version: int = CURRENT_SCHEMA_VERSION,
) -> UpgradeDryRun:
    plan = build_upgrade_plan(bind, registry, target_version=target_version)
    if plan.state != "ready":
        errors = (plan.error_code,) if plan.error_code else ()
        return UpgradeDryRun(
            current_version=plan.current_version,
            target_version=plan.target_version,
            state=plan.state,
            steps=(),
            warnings=(),
            errors=errors,
            can_upgrade=False,
        )

    reports: list[StepDryRun] = []
    warnings: list[str] = []
    errors: list[str] = []
    try:
        with _read_only_connection(bind) as connection:
            for index, step in enumerate(plan.steps):
                try:
                    preview = step.preview(connection)
                    if not isinstance(preview, MigrationPreview):
                        raise MigrationError("invalid_preview", step.name)
                    if index == 0:
                        check = step.precheck(connection)
                        if not isinstance(check, MigrationCheck):
                            raise MigrationError("invalid_precheck", step.name)
                        precheck_state = "passed" if check.passed else "failed"
                        precheck_message = check.message
                        if not check.passed:
                            errors.append("precheck_failed")
                    else:
                        precheck_state = "deferred"
                        precheck_message = "precheck_deferred"
                    warnings.extend(preview.warnings)
                    reports.append(
                        StepDryRun(
                            from_version=step.from_version,
                            to_version=step.to_version,
                            name=step.name,
                            changes=preview.changes,
                            warnings=preview.warnings,
                            precheck_state=precheck_state,
                            precheck_message=precheck_message,
                        )
                    )
                except MigrationError as exc:
                    errors.append(exc.code)
                    break
                except Exception:
                    errors.append("preview_failed")
                    break
    except MigrationError as exc:
        errors.append(exc.code)
    except Exception:
        errors.append("preview_failed")

    return UpgradeDryRun(
        current_version=plan.current_version,
        target_version=plan.target_version,
        state="ready" if not errors else "blocked",
        steps=tuple(reports),
        warnings=tuple(warnings),
        errors=tuple(errors),
        can_upgrade=not errors and len(reports) == len(plan.steps),
    )


def apply_upgrade(
    bind: Engine,
    registry: MigrationRegistry,
    *,
    backup_confirmed: bool,
    target_version: int = CURRENT_SCHEMA_VERSION,
) -> MigrationApplyResult:
    if not backup_confirmed:
        raise MigrationError("backup_confirmation_required")

    try:
        with bind.begin() as connection:
            if connection.dialect.name == "sqlite":
                # pysqlite defers the physical BEGIN until the first write. An
                # explicit transaction is required before DDL so a later step
                # failure rolls back newly created tables as well as data and
                # version records.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            from_version = _read_database_version(connection)
            if from_version == target_version:
                raise MigrationError("no_upgrade_needed")
            steps = registry.resolve(from_version, target_version)
            for step in steps:
                precheck = step.precheck(connection)
                if not isinstance(precheck, MigrationCheck):
                    raise MigrationError("invalid_precheck", step.name)
                if not precheck.passed:
                    raise MigrationError("precheck_failed", step.name)

                step.apply(connection)
                connection.execute(
                    insert(SchemaMigration).values(
                        version=step.to_version,
                        name=step.name,
                    )
                )

                postcheck = step.postcheck(connection)
                if not isinstance(postcheck, MigrationCheck):
                    raise MigrationError("invalid_postcheck", step.name)
                if not postcheck.passed:
                    raise MigrationError("postcheck_failed", step.name)

            final_version = _read_database_version(connection)
            if final_version != target_version:
                raise MigrationError("version_record_failed")
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("apply_failed") from None

    return MigrationApplyResult(
        from_version=from_version,
        to_version=target_version,
        applied_steps=tuple(step.name for step in steps),
    )


def _item_sources_preview(connection: Connection) -> MigrationPreview:
    del connection
    return MigrationPreview(
        changes=(
            "create item_sources table",
            "add globally unique normalized source URLs linked to items",
        ),
        warnings=("back up the Schema 1 database before applying",),
    )


def _item_sources_precheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "items" not in table_names:
        return MigrationCheck(False, "items table is missing")
    if "item_sources" in table_names:
        return MigrationCheck(False, "item_sources already exists")
    return MigrationCheck(True, "Schema 1 item table is ready")


def _item_sources_apply(connection: Connection) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE item_sources (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            url VARCHAR(2048) NOT NULL,
            normalized_url VARCHAR(2048) NOT NULL,
            title VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            CONSTRAINT ck_item_sources_url_not_blank CHECK (trim(url) != ''),
            CONSTRAINT ck_item_sources_normalized_url_not_blank
                CHECK (trim(normalized_url) != ''),
            CONSTRAINT uq_item_sources_normalized_url UNIQUE (normalized_url),
            FOREIGN KEY(item_id) REFERENCES items (id) ON DELETE CASCADE
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_item_sources_item_id ON item_sources (item_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_item_sources_normalized_url "
        "ON item_sources (normalized_url)"
    )


def _item_sources_postcheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    if "item_sources" not in inspector.get_table_names():
        return MigrationCheck(False, "item_sources was not created")
    columns = {column["name"] for column in inspector.get_columns("item_sources")}
    if not ITEM_SOURCES_SCHEMA_2_COLUMNS.issubset(columns):
        return MigrationCheck(False, "item_sources columns are incomplete")
    unique_columns = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("item_sources")
    }
    if ("normalized_url",) not in unique_columns:
        return MigrationCheck(False, "normalized_url uniqueness is missing")
    foreign_keys = inspector.get_foreign_keys("item_sources")
    if not any(
        foreign_key.get("referred_table") == "items"
        and tuple(foreign_key.get("constrained_columns") or ()) == ("item_id",)
        for foreign_key in foreign_keys
    ):
        return MigrationCheck(False, "item source item foreign key is missing")
    return MigrationCheck(True, "item_sources structure is valid")


def _media_index_preview(connection: Connection) -> MigrationPreview:
    del connection
    return MigrationPreview(
        changes=(
            "create media_index_entries derived-cache table",
            "add unique media_path and parent, digest, and path lookup indexes",
            "create singleton media_index_state status table",
            "initialize an empty invalid index without scanning media files",
        ),
        warnings=(
            "back up the Schema 2 database before applying",
            "the media index is rebuildable and is excluded from JSON backups",
        ),
    )


def _media_index_precheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    source_tables = tuple(
        table
        for table in MediaIndexEntry.metadata.sorted_tables
        if table.name
        not in {
            MediaIndexEntry.__tablename__,
            MediaIndexState.__tablename__,
            *(model.__tablename__ for model in TASK_SCHEMA_TABLES),
        }
    )
    missing = sorted(table.name for table in source_tables if table.name not in table_names)
    if missing:
        return MigrationCheck(False, f"required tables are missing: {', '.join(missing)}")
    for table in source_tables:
        actual_columns = {
            column["name"] for column in inspector.get_columns(table.name)
        }
        expected_columns = (
            ITEM_SOURCES_SCHEMA_2_COLUMNS
            if table.name == ItemSource.__tablename__
            else {column.name for column in table.columns}
        )
        missing_columns = sorted(expected_columns - actual_columns)
        if missing_columns:
            return MigrationCheck(
                False,
                f"required columns are missing from {table.name}: "
                f"{', '.join(missing_columns)}",
            )
    existing = sorted(
        {MediaIndexEntry.__tablename__, MediaIndexState.__tablename__} & table_names
    )
    if existing:
        return MigrationCheck(
            False,
            f"media index tables already exist: {', '.join(existing)}",
        )
    return MigrationCheck(True, "Schema 2 is ready for empty media index tables")


def _media_index_apply(connection: Connection) -> None:
    MediaIndexEntry.__table__.create(bind=connection)
    MediaIndexState.__table__.create(bind=connection)
    connection.execute(
        insert(MediaIndexState).values(
            id=1,
            index_format_version=1,
            valid=False,
            stale_reason="never_scanned",
            current_media_root_identity="",
            last_scan_result="never",
            last_scan_error="",
            duration_ms=0,
            entry_count=0,
            valid_count=0,
            damaged_count=0,
            recovered_count=0,
            skipped_count=0,
            reused_count=0,
            new_count=0,
            changed_count=0,
            removed_count=0,
            rehashed_count=0,
            change_details_json="[]",
            skipped_details_json="[]",
            snapshot_signature="",
        )
    )


def _media_index_postcheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if not {MediaIndexEntry.__tablename__, MediaIndexState.__tablename__}.issubset(
        table_names
    ):
        return MigrationCheck(False, "media index tables were not created")

    entry_columns = {
        column["name"]
        for column in inspector.get_columns(MediaIndexEntry.__tablename__)
    }
    required_entry_columns = {
        "id",
        "record_type",
        "media_path",
        "basename",
        "parent_directory",
        "extension",
        "mime_type",
        "size",
        "sha256",
        "valid",
        "detail",
        "recovered",
        "mode",
        "device",
        "inode",
        "modified_ns",
        "changed_ns",
        "directory_mapping_token",
        "directory_identity_json",
        "cache_signature",
        "first_seen_at",
        "last_seen_at",
        "indexed_at",
    }
    if not required_entry_columns.issubset(entry_columns):
        return MigrationCheck(False, "media index entry columns are incomplete")

    unique_columns = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(
            MediaIndexEntry.__tablename__
        )
    }
    if ("media_path",) not in unique_columns:
        return MigrationCheck(False, "media index media_path uniqueness is missing")
    indexed_columns = {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(MediaIndexEntry.__tablename__)
    }
    for required_index in (
        ("media_path",),
        ("parent_directory",),
        ("sha256",),
    ):
        if required_index not in indexed_columns:
            return MigrationCheck(
                False,
                f"media index lookup index is missing: {required_index[0]}",
            )

    state_columns = {
        column["name"]
        for column in inspector.get_columns(MediaIndexState.__tablename__)
    }
    required_state_columns = {
        "id",
        "index_format_version",
        "valid",
        "stale_reason",
        "current_media_root_identity",
        "last_incremental_scan_at",
        "last_full_verification_at",
        "last_attempt_at",
        "last_success_at",
        "last_scan_kind",
        "last_scan_result",
        "last_scan_error",
        "duration_ms",
        "entry_count",
        "valid_count",
        "damaged_count",
        "recovered_count",
        "skipped_count",
        "reused_count",
        "new_count",
        "changed_count",
        "removed_count",
        "rehashed_count",
        "change_details_json",
        "skipped_details_json",
        "snapshot_signature",
    }
    if not required_state_columns.issubset(state_columns):
        return MigrationCheck(False, "media index state columns are incomplete")
    state_row = connection.execute(
        select(
            MediaIndexState.id,
            MediaIndexState.index_format_version,
            MediaIndexState.valid,
            MediaIndexState.last_scan_result,
        )
    ).one_or_none()
    if state_row != (1, 1, False, "never"):
        return MigrationCheck(False, "media index state singleton is missing")
    return MigrationCheck(True, "empty media index structure is valid")


def _normalized_url_is_unique(connection: Connection) -> bool:
    inspector = inspect(connection)
    if ("normalized_url",) in {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(ItemSource.__tablename__)
    }:
        return True
    return any(
        bool(index.get("unique"))
        and tuple(index.get("column_names") or ()) == ("normalized_url",)
        for index in inspector.get_indexes(ItemSource.__tablename__)
    )


def _schema_2_item_source_shape_is_valid(connection: Connection) -> bool:
    columns = {
        column["name"]: column
        for column in inspect(connection).get_columns(ItemSource.__tablename__)
    }
    if set(columns) < ITEM_SOURCES_SCHEMA_2_COLUMNS:
        return False
    expected = {
        "id": ("INTEGER", False, 1),
        "item_id": ("INTEGER", False, 0),
        "url": ("VARCHAR(2048)", False, 0),
        "normalized_url": ("VARCHAR(2048)", False, 0),
        "title": ("VARCHAR(255)", True, 0),
        "created_at": ("DATETIME", False, 0),
    }
    return all(
        str(columns[name].get("type")).upper() == expected_type
        and bool(columns[name].get("nullable")) is nullable
        and int(columns[name].get("primary_key") or 0) == primary_key
        for name, (expected_type, nullable, primary_key) in expected.items()
    )


def _item_source_foreign_key_exists(connection: Connection) -> bool:
    return any(
        foreign_key.get("referred_table") == "items"
        and tuple(foreign_key.get("constrained_columns") or ()) == ("item_id",)
        for foreign_key in inspect(connection).get_foreign_keys(
            ItemSource.__tablename__
        )
    )


def _source_tracking_preview(connection: Connection) -> MigrationPreview:
    del connection
    return MigrationPreview(
        changes=(
            "add nullable provider_key, external_id, last_checked_at, and metadata_hash columns",
            "create a unique provider/external-ID index only when both values are non-null",
            "preserve every existing item_sources row with all four new values null",
        ),
        warnings=(
            "back up the Schema 3 database before applying",
            "Schema 4 databases are not compatible with the stable v1.1.0 application",
            "the migration performs no network or media access",
        ),
    )


def _source_tracking_precheck(connection: Connection) -> MigrationCheck:
    try:
        if _read_database_version(connection) != 3:
            return MigrationCheck(False, "database is not at Schema 3")
    except MigrationError:
        return MigrationCheck(False, "Schema 3 version record is unavailable")
    inspector = inspect(connection)
    if ItemSource.__tablename__ not in inspector.get_table_names():
        return MigrationCheck(False, "item_sources table is missing")
    columns = {
        column["name"]: column
        for column in inspector.get_columns(ItemSource.__tablename__)
    }
    if set(columns) != ITEM_SOURCES_SCHEMA_2_COLUMNS:
        return MigrationCheck(False, "item_sources is not the expected Schema 3 shape")
    if not _schema_2_item_source_shape_is_valid(connection):
        return MigrationCheck(False, "item_sources column definitions are invalid")
    indexes = inspector.get_indexes(ItemSource.__tablename__)
    if any(index.get("name") == SOURCE_IDENTITY_INDEX for index in indexes):
        return MigrationCheck(False, "provider identity index already exists")
    if not _normalized_url_is_unique(connection):
        return MigrationCheck(False, "normalized_url uniqueness is missing")
    if not _item_source_foreign_key_exists(connection):
        return MigrationCheck(False, "item source item foreign key is missing")
    return MigrationCheck(True, "Schema 3 item_sources is ready for nullable metadata")


def _source_tracking_apply(connection: Connection) -> None:
    connection.exec_driver_sql(
        "ALTER TABLE item_sources ADD COLUMN provider_key VARCHAR(64) NULL"
    )
    connection.exec_driver_sql(
        "ALTER TABLE item_sources ADD COLUMN external_id VARCHAR(512) NULL"
    )
    connection.exec_driver_sql(
        "ALTER TABLE item_sources ADD COLUMN last_checked_at DATETIME NULL"
    )
    connection.exec_driver_sql(
        "ALTER TABLE item_sources ADD COLUMN metadata_hash VARCHAR(96) NULL"
    )
    connection.exec_driver_sql(
        f"CREATE UNIQUE INDEX {SOURCE_IDENTITY_INDEX} "
        "ON item_sources (provider_key, external_id) "
        "WHERE provider_key IS NOT NULL AND external_id IS NOT NULL"
    )


def _source_identity_index_is_valid(connection: Connection) -> bool:
    indexes = inspect(connection).get_indexes(ItemSource.__tablename__)
    matching = [index for index in indexes if index.get("name") == SOURCE_IDENTITY_INDEX]
    if len(matching) != 1:
        return False
    index = matching[0]
    if not index.get("unique") or tuple(index.get("column_names") or ()) != (
        "provider_key",
        "external_id",
    ):
        return False
    sql = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (SOURCE_IDENTITY_INDEX,),
    ).scalar_one_or_none()
    if not isinstance(sql, str) or "where" not in sql.casefold():
        return False
    predicate = "".join(sql.casefold().split()).split("where", 1)[1]
    predicate = predicate.replace('"', "").replace("`", "")
    return predicate == "provider_keyisnotnullandexternal_idisnotnull"


def _source_tracking_postcheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    columns = {
        column["name"]: column
        for column in inspector.get_columns(ItemSource.__tablename__)
    }
    if set(columns) != ITEM_SOURCES_SCHEMA_4_COLUMNS:
        return MigrationCheck(False, "Schema 4 item_sources columns are incomplete")
    if not _schema_2_item_source_shape_is_valid(connection):
        return MigrationCheck(False, "legacy item_sources columns changed")
    for name, expected_type in {
        "provider_key": "VARCHAR(64)",
        "external_id": "VARCHAR(512)",
        "last_checked_at": "DATETIME",
        "metadata_hash": "VARCHAR(96)",
    }.items():
        column = columns[name]
        if not column.get("nullable") or str(column.get("type")).upper() != expected_type:
            return MigrationCheck(False, f"{name} type or nullable state is invalid")
    if not _normalized_url_is_unique(connection):
        return MigrationCheck(False, "normalized_url uniqueness is missing")
    if not _item_source_foreign_key_exists(connection):
        return MigrationCheck(False, "item source item foreign key is missing")
    if not _source_identity_index_is_valid(connection):
        return MigrationCheck(False, "provider identity partial unique index is invalid")
    non_null_history = connection.exec_driver_sql(
        "SELECT count(*) FROM item_sources WHERE provider_key IS NOT NULL "
        "OR external_id IS NOT NULL OR last_checked_at IS NOT NULL "
        "OR metadata_hash IS NOT NULL"
    ).scalar_one()
    if int(non_null_history) != 0:
        return MigrationCheck(False, "legacy source metadata was modified")
    if _read_database_version(connection) != 4:
        return MigrationCheck(False, "Schema 4 version record is missing")
    return MigrationCheck(True, "Schema 4 source tracking structure is valid")


def _persistent_tasks_preview(connection: Connection) -> MigrationPreview:
    del connection
    return MigrationPreview(
        changes=(
            "create the provider-neutral operation_tasks state and lease table",
            "create bounded task event and download execution fact tables",
            "create transactional item_local_assets publication links",
            "initialize all task/runtime tables empty without network or media access",
        ),
        warnings=(
            "back up the Schema 4 database before applying",
            "Schema 5 databases are intentionally rejected by stable v1.2.0",
            "task, runtime, progress, lease, and history facts are excluded from JSON backups",
        ),
    )


def _persistent_tasks_precheck(connection: Connection) -> MigrationCheck:
    try:
        if _read_database_version(connection) != 4:
            return MigrationCheck(False, "database is not at Schema 4")
    except MigrationError:
        return MigrationCheck(False, "Schema 4 version record is unavailable")
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    new_names = {model.__tablename__ for model in TASK_SCHEMA_TABLES}
    existing = sorted(new_names & table_names)
    if existing:
        return MigrationCheck(
            False,
            f"Schema 5 task tables already exist: {', '.join(existing)}",
        )
    if ItemSource.__tablename__ not in table_names:
        return MigrationCheck(False, "item_sources table is missing")
    columns = {
        column["name"] for column in inspector.get_columns(ItemSource.__tablename__)
    }
    if columns != ITEM_SOURCES_SCHEMA_4_COLUMNS:
        return MigrationCheck(False, "item_sources is not the expected Schema 4 shape")
    if not _source_identity_index_is_valid(connection):
        return MigrationCheck(False, "provider identity index is invalid")
    return MigrationCheck(True, "Schema 4 is ready for empty persistent task tables")


def _persistent_tasks_apply(connection: Connection) -> None:
    for model in TASK_SCHEMA_TABLES:
        model.__table__.create(bind=connection)


def _persistent_tasks_postcheck(connection: Connection) -> MigrationCheck:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    required = {model.__tablename__ for model in TASK_SCHEMA_TABLES}
    if not required.issubset(table_names):
        return MigrationCheck(False, "Schema 5 task tables were not created")
    for model in TASK_SCHEMA_TABLES:
        expected_columns = {column.name for column in model.__table__.columns}
        actual_columns = {
            column["name"] for column in inspector.get_columns(model.__tablename__)
        }
        if actual_columns != expected_columns:
            return MigrationCheck(False, f"{model.__tablename__} columns are invalid")
        count = connection.exec_driver_sql(
            f'SELECT count(*) FROM "{model.__tablename__}"'
        ).scalar_one()
        if int(count) != 0:
            return MigrationCheck(False, f"{model.__tablename__} was not initialized empty")
    operation_checks = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints(OperationTask.__tablename__)
    }
    if not {
        "ck_operation_tasks_type",
        "ck_operation_tasks_state",
        "ck_operation_tasks_version",
    }.issubset(operation_checks):
        return MigrationCheck(False, "operation task database constraints are incomplete")
    if _read_database_version(connection) != 5:
        return MigrationCheck(False, "Schema 5 version record is missing")
    return MigrationCheck(True, "Schema 5 persistent task structure is valid and empty")


MIGRATION_REGISTRY = MigrationRegistry(
    (
        MigrationStep(
            from_version=1,
            to_version=2,
            name="create_item_sources",
            preview=_item_sources_preview,
            apply=_item_sources_apply,
            precheck=_item_sources_precheck,
            postcheck=_item_sources_postcheck,
        ),
        MigrationStep(
            from_version=2,
            to_version=3,
            name="create_media_index",
            preview=_media_index_preview,
            apply=_media_index_apply,
            precheck=_media_index_precheck,
            postcheck=_media_index_postcheck,
        ),
        MigrationStep(
            from_version=3,
            to_version=4,
            name="extend_item_sources_provider_metadata",
            preview=_source_tracking_preview,
            apply=_source_tracking_apply,
            precheck=_source_tracking_precheck,
            postcheck=_source_tracking_postcheck,
        ),
        MigrationStep(
            from_version=4,
            to_version=5,
            name="create_persistent_operation_tasks",
            preview=_persistent_tasks_preview,
            apply=_persistent_tasks_apply,
            precheck=_persistent_tasks_precheck,
            postcheck=_persistent_tasks_postcheck,
        ),
    )
)
