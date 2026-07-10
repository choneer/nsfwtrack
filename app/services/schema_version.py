from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import inspect, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base

CURRENT_SCHEMA_VERSION = 1
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
    from app.models import SchemaMigration

    try:
        with bind.begin() as connection:
            Base.metadata.create_all(bind=connection)
            connection.execute(
                insert(SchemaMigration).values(
                    version=CURRENT_SCHEMA_VERSION,
                    name=BASELINE_MIGRATION_NAME,
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
