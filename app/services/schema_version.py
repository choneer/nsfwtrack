from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import inspect, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base

CURRENT_SCHEMA_VERSION = 6
BASELINE_MIGRATION_NAME = "baseline"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
SCHEMA_STATUS_CURRENT = "current"
SCHEMA_STATUS_UPGRADE_REQUIRED = "upgrade_required"
SCHEMA_STATUS_APPLICATION_OUTDATED = "application_outdated"
SCHEMA_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaStatus:
    application_version: int
    database_version: int | None
    state: str
    last_applied_at: datetime | None


class SchemaVersionError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status: SchemaStatus | None = None,
        problems: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.status = status
        self.problems = problems
        super().__init__(self._message())

    def _message(self) -> str:
        backup_hint = "Back up the database before changing the application version."
        if self.code == "application_outdated" and self.status is not None:
            return (
                "Database schema version "
                f"{self.status.database_version} is newer than application schema "
                f"version {self.status.application_version}; startup was refused. "
                f"{backup_hint}"
            )
        if self.code == "structure_invalid":
            detail = "; ".join(self.problems) or "required structure is unavailable"
            return (
                "Database schema preflight failed; no baseline version was recorded "
                f"({detail}). {backup_hint}"
            )
        if self.code == "version_unknown":
            return (
                "Database schema version could not be confirmed; startup was refused. "
                f"{backup_hint}"
            )
        return (
            "Database schema initialization failed; no baseline version was recorded. "
            f"{backup_hint}"
        )


def _load_models() -> None:
    import app.models  # noqa: F401


def _business_schema() -> dict[str, set[str]]:
    _load_models()
    return {
        table.name: {column.name for column in table.columns}
        for table in Base.metadata.sorted_tables
        if table.name != SCHEMA_MIGRATIONS_TABLE
    }


def _structure_problems(bind: Engine) -> tuple[str, ...]:
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    problems: list[str] = []
    for table_name, expected_columns in sorted(_business_schema().items()):
        if table_name not in table_names:
            problems.append(f"missing table {table_name}")
            continue
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(expected_columns - actual_columns)
        if missing_columns:
            problems.append(
                f"missing columns in {table_name}: {', '.join(missing_columns)}"
            )
    if "item_sources" in table_names:
        source_columns = {
            column["name"]: column
            for column in inspector.get_columns("item_sources")
        }
        tracking_types = {
            "provider_key": "VARCHAR(64)",
            "external_id": "VARCHAR(512)",
            "last_checked_at": "DATETIME",
            "metadata_hash": "VARCHAR(96)",
        }
        for name, expected_type in tracking_types.items():
            column = source_columns.get(name)
            if column is None:
                continue
            if not column.get("nullable") or str(column.get("type")).upper() != expected_type:
                problems.append(f"invalid column {name} in item_sources")
        indexes = inspector.get_indexes("item_sources")
        matching = [
            index
            for index in indexes
            if index.get("name") == "uq_item_sources_provider_identity"
        ]
        if len(matching) != 1 or not matching[0].get("unique") or tuple(
            matching[0].get("column_names") or ()
        ) != ("provider_key", "external_id"):
            problems.append("missing provider identity partial unique index")
        else:
            try:
                with bind.connect() as connection:
                    sql = connection.exec_driver_sql(
                        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                        ("uq_item_sources_provider_identity",),
                    ).scalar_one_or_none()
            except SQLAlchemyError:
                sql = None
            normalized = "" if not isinstance(sql, str) else "".join(sql.casefold().split())
            predicate = normalized.split("where", 1)[1] if "where" in normalized else ""
            predicate = predicate.replace('"', "").replace("`", "")
            if predicate != "provider_keyisnotnullandexternal_idisnotnull":
                problems.append("invalid provider identity partial predicate")
    if "operation_tasks" in table_names:
        task_checks = {
            constraint.get("name")
            for constraint in inspector.get_check_constraints("operation_tasks")
        }
        if not {
            "ck_operation_tasks_type",
            "ck_operation_tasks_state",
            "ck_operation_tasks_version",
            "ck_operation_tasks_attempts",
            "ck_operation_tasks_bytes",
        }.issubset(task_checks):
            problems.append("invalid operation task check constraints")
        task_unique = {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("operation_tasks")
        }
        if ("intent_key",) not in task_unique:
            problems.append("missing operation task intent uniqueness")
        task_foreign_keys = {
            (
                tuple(foreign_key.get("constrained_columns") or ()),
                foreign_key.get("referred_table"),
                str((foreign_key.get("options") or {}).get("ondelete", "")).upper(),
            )
            for foreign_key in inspector.get_foreign_keys("operation_tasks")
        }
        for expected in (
            (("item_id",), "items", "SET NULL"),
            (("source_id",), "item_sources", "SET NULL"),
        ):
            if expected not in task_foreign_keys:
                problems.append(f"invalid operation task foreign key {expected[0][0]}")
    if "task_events" in table_names:
        event_unique = {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("task_events")
        }
        if ("task_id", "version") not in event_unique:
            problems.append("missing task event version uniqueness")
    if "item_local_assets" in table_names:
        asset_unique = {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("item_local_assets")
        }
        for expected in (
            ("relative_path",),
            ("item_id", "provider_key", "asset_identity_hash"),
        ):
            if expected not in asset_unique:
                problems.append("missing local asset uniqueness")
    return tuple(problems)


def get_schema_status(bind: Engine) -> SchemaStatus:
    _load_models()
    try:
        inspector = inspect(bind)
        if SCHEMA_MIGRATIONS_TABLE not in inspector.get_table_names():
            return SchemaStatus(
                application_version=CURRENT_SCHEMA_VERSION,
                database_version=None,
                state=SCHEMA_STATUS_UNKNOWN,
                last_applied_at=None,
            )
        migration_columns = {
            column["name"]
            for column in inspector.get_columns(SCHEMA_MIGRATIONS_TABLE)
        }
        if not {"version", "name", "applied_at"}.issubset(migration_columns):
            return SchemaStatus(
                application_version=CURRENT_SCHEMA_VERSION,
                database_version=None,
                state=SCHEMA_STATUS_UNKNOWN,
                last_applied_at=None,
            )

        from app.models import SchemaMigration

        with bind.connect() as connection:
            row = connection.execute(
                select(SchemaMigration.version, SchemaMigration.applied_at)
                .order_by(SchemaMigration.version.desc())
                .limit(1)
            ).one_or_none()
    except (SQLAlchemyError, TypeError, ValueError):
        return SchemaStatus(
            application_version=CURRENT_SCHEMA_VERSION,
            database_version=None,
            state=SCHEMA_STATUS_UNKNOWN,
            last_applied_at=None,
        )

    if row is None:
        return SchemaStatus(
            application_version=CURRENT_SCHEMA_VERSION,
            database_version=None,
            state=SCHEMA_STATUS_UNKNOWN,
            last_applied_at=None,
        )

    try:
        database_version = int(row.version)
        last_applied_at = row.applied_at
        if last_applied_at is not None and not isinstance(last_applied_at, datetime):
            raise ValueError
    except (TypeError, ValueError):
        return SchemaStatus(
            application_version=CURRENT_SCHEMA_VERSION,
            database_version=None,
            state=SCHEMA_STATUS_UNKNOWN,
            last_applied_at=None,
        )
    if database_version == CURRENT_SCHEMA_VERSION:
        state = SCHEMA_STATUS_CURRENT
    elif database_version < CURRENT_SCHEMA_VERSION:
        state = SCHEMA_STATUS_UPGRADE_REQUIRED
    else:
        state = SCHEMA_STATUS_APPLICATION_OUTDATED
    return SchemaStatus(
        application_version=CURRENT_SCHEMA_VERSION,
        database_version=database_version,
        state=state,
        last_applied_at=last_applied_at,
    )


def _create_schema_and_register_baseline(bind: Engine) -> None:
    _load_models()
    from app.models import MediaIndexState, SchemaMigration

    try:
        with bind.begin() as connection:
            Base.metadata.create_all(bind=connection)
            connection.execute(
                insert(SchemaMigration).values(
                    version=CURRENT_SCHEMA_VERSION,
                    name=BASELINE_MIGRATION_NAME,
                )
            )
            if connection.scalar(select(MediaIndexState.id).limit(1)) is None:
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
    except Exception:
        raise SchemaVersionError("initialization_failed") from None


def initialize_database(bind: Engine) -> SchemaStatus:
    _load_models()
    try:
        table_names = set(inspect(bind).get_table_names())
    except SQLAlchemyError:
        raise SchemaVersionError("version_unknown") from None

    if not table_names:
        _create_schema_and_register_baseline(bind)
        status = get_schema_status(bind)
        if status.state != SCHEMA_STATUS_CURRENT:
            raise SchemaVersionError("initialization_failed", status=status)
        return status

    if SCHEMA_MIGRATIONS_TABLE not in table_names:
        try:
            problems = _structure_problems(bind)
        except SQLAlchemyError:
            raise SchemaVersionError("version_unknown") from None
        if problems:
            raise SchemaVersionError("structure_invalid", problems=problems)
        _create_schema_and_register_baseline(bind)
        status = get_schema_status(bind)
        if status.state != SCHEMA_STATUS_CURRENT:
            raise SchemaVersionError("initialization_failed", status=status)
        return status

    status = get_schema_status(bind)
    if status.state == SCHEMA_STATUS_UNKNOWN:
        raise SchemaVersionError("version_unknown", status=status)
    if status.state == SCHEMA_STATUS_APPLICATION_OUTDATED:
        raise SchemaVersionError("application_outdated", status=status)
    if status.state == SCHEMA_STATUS_UPGRADE_REQUIRED:
        return status

    try:
        problems = _structure_problems(bind)
    except SQLAlchemyError:
        raise SchemaVersionError("version_unknown", status=status) from None
    if problems:
        raise SchemaVersionError(
            "structure_invalid",
            status=status,
            problems=problems,
        )
    return status
