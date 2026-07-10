from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import inspect, insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.models import SchemaMigration
from app.services.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_MIGRATIONS_TABLE,
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
            del first, database, source
            if action in _SQLITE_READ_ACTIONS:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_PRAGMA and second is None:
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

                postcheck = step.postcheck(connection)
                if not isinstance(postcheck, MigrationCheck):
                    raise MigrationError("invalid_postcheck", step.name)
                if not postcheck.passed:
                    raise MigrationError("postcheck_failed", step.name)
                connection.execute(
                    insert(SchemaMigration).values(
                        version=step.to_version,
                        name=step.name,
                    )
                )

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


MIGRATION_REGISTRY = MigrationRegistry()
