"""Build a bounded diagnostic report without external activity or secrets."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ItemLocalAsset, OperationTask
from app.local_workflow.service import effective_task_state
from app.provider_runtime.service import ProviderRuntimeRegistry, egress_profile_statuses
from app.services.media_index import get_media_index_status
from app.services.schema_version import CURRENT_SCHEMA_VERSION, get_schema_status


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    application_version: str
    schema: dict[str, object]
    backup_format: str
    providers: tuple[dict[str, object], ...]
    cookiecloud: dict[str, int]
    egress: dict[str, object]
    tasks: dict[str, int]
    media_index: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_diagnostics_snapshot(db: Session, *, application_version: str = "1.7.0") -> DiagnosticsSnapshot:
    """Return local facts only; never fetches Provider/CookieCloud/egress URLs."""

    schema_status = get_schema_status(db.get_bind())
    runtime = ProviderRuntimeRegistry(db).list()
    providers = tuple(
        {
            "provider_key": view.provider_key,
            "scope": view.scope,
            "enabled": view.enabled,
            "runtime_status": view.runtime_status,
            "configuration_status": view.configuration_status,
            "session_status": view.session_status,
            "egress_profile": view.egress_profile,
            "last_error_code": view.last_error_code,
            "last_health_check_at": view.last_health_check_at.isoformat()
            if view.last_health_check_at
            else None,
            "last_success_at": view.last_success_at.isoformat()
            if view.last_success_at
            else None,
        }
        for view in runtime
    )
    session_counts = Counter(view.session_status for view in runtime)
    task_counts = Counter(
        str(value)
        for value in db.scalars(
            select(OperationTask.state).order_by(OperationTask.state)
        ).all()
    )
    effective_counts = Counter(
        effective_task_state(task)
        for task in db.scalars(select(OperationTask)).all()
    )
    try:
        media = get_media_index_status(db)
        media_report: dict[str, object] = {
            "valid": media.usable,
            "entry_count": media.entry_count,
            "stale_reason": media.stale_reason,
            "last_success_at": media.last_success_at.isoformat()
            if media.last_success_at
            else None,
        }
    except Exception:
        media_report = {
            "valid": False,
            "entry_count": 0,
            "stale_reason": "unavailable",
            "last_success_at": None,
        }
    return DiagnosticsSnapshot(
        application_version=application_version,
        schema={
            "application_version": CURRENT_SCHEMA_VERSION,
            "database_version": schema_status.database_version,
            "state": schema_status.state,
        },
        backup_format="nsfwtrack.backup.v2",
        providers=providers,
        cookiecloud={
            "available": int(session_counts.get("available", 0)),
            "missing": int(session_counts.get("missing", 0)),
            "expired": int(session_counts.get("expired", 0)),
        },
        egress={
            "profiles": list(egress_profile_statuses()),
            "provider_profile_consistent": all(
                view.configuration_status != "valid"
                or any(
                    profile["name"] == view.egress_profile and profile["supported"]
                    for profile in egress_profile_statuses()
                )
                for view in runtime
            ),
            "network_probe_on_get": False,
        },
        tasks={
            **{key: int(value) for key, value in sorted(task_counts.items())},
            "interrupted": int(effective_counts.get("interrupted", 0)),
            "retryable": int(effective_counts.get("retryable", 0)),
        },
        media_index={
            **media_report,
            "linked_local_assets": int(
                db.scalar(select(func.count()).select_from(ItemLocalAsset)) or 0
            ),
            "pending_recovery_tasks": int(
                db.scalar(
                    select(func.count()).select_from(OperationTask).where(
                        OperationTask.stage == "recovery_required"
                    )
                )
                or 0
            ),
        },
    )
