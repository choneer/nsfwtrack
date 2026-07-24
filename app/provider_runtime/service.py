"""Provider Runtime Registry without secret or ambient-network storage.

The registry persists operator choices and diagnostic facts only.  It never
stores a Cookie header, password, token, URL, raw response, or Provider
identity beyond the reviewed code-owned provider key.  An explicit POST health
check prepares and records state here; its controlled outbound probe lives in
``app.provider_runtime.catalog`` so GETs and startup remain network-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ProviderRuntimeState
from app.providers.javdb.session import SessionCookieError, load_javdb_session_cookie


class ProviderRuntimeErrorCode(str, Enum):
    UNKNOWN_PROVIDER = "unknown_provider"
    INVALID_REQUEST = "invalid_request"
    INVALID_EGRESS_PROFILE = "invalid_egress_profile"
    FIXTURE_PROVIDER = "fixture_provider"
    CONCURRENT_UPDATE = "concurrent_update"


class ProviderRuntimeError(ValueError):
    def __init__(self, code: ProviderRuntimeErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ProviderRuntimeDefinition:
    provider_key: str
    display_name: str
    scope: str
    cookie_required: bool
    manageable: bool
    egress_policy: str


@dataclass(frozen=True, slots=True)
class ProviderRuntimeView:
    provider_key: str
    display_name: str
    scope: str
    cookie_required: bool
    manageable: bool
    egress_policy: str
    enabled: bool
    runtime_status: str
    configuration_status: str
    egress_profile: str
    session_status: str
    session_updated_at: datetime | None
    session_expires_at: datetime | None
    last_health_check_at: datetime | None
    last_success_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    configuration_version: int
    optimistic_version: int

    @property
    def local_runtime_ready(self) -> bool:
        return (
            self.manageable
            and self.scope == "PRODUCTION"
            and self.enabled
            and self.configuration_status == "valid"
            and (not self.cookie_required or self.session_status == "available")
        )

    @property
    def in_production_catalog(self) -> bool:
        return self.local_runtime_ready and self.runtime_status == "ready"

    @property
    def can_search(self) -> bool:
        return self.in_production_catalog

    @property
    def can_detail(self) -> bool:
        return self.in_production_catalog


@dataclass(frozen=True, slots=True)
class ProviderRuntimeHealthPlan:
    """A non-secret snapshot that authorizes exactly one explicit probe."""

    provider: ProviderRuntimeView
    expected_version: int
    blocker_code: str | None


_DEFINITIONS: tuple[ProviderRuntimeDefinition, ...] = (
    ProviderRuntimeDefinition(
        "javdb_metadata",
        "JavDB Metadata",
        "PRODUCTION",
        True,
        True,
        "avoid_jp_kr",
    ),
    ProviderRuntimeDefinition(
        "zuidapi_vod",
        "ZuidAPI MacCMS VOD",
        "PRODUCTION",
        False,
        True,
        "default",
    ),
    ProviderRuntimeDefinition(
        "copymanga",
        "CopyManga Comic",
        "PRODUCTION",
        False,
        True,
        "default",
    ),
    ProviderRuntimeDefinition(
        "jiuse_vod",
        "Jiuse VOD Fixture",
        "TEST_FIXTURE",
        False,
        False,
        "fixture_only",
    ),
    ProviderRuntimeDefinition(
        "comic_local_fixture",
        "Local Comic Fixture",
        "TEST_FIXTURE",
        False,
        False,
        "fixture_only",
    ),
)
_BY_KEY = {definition.provider_key: definition for definition in _DEFINITIONS}
_EGRESS_PROFILES = ("default", "direct", "proxy_pool")
_SUPPORTED_EGRESS_PROFILES = frozenset({"default", "direct"})


def egress_profile_statuses() -> tuple[dict[str, object], ...]:
    """Code-owned transport capability facts; does not read config or use network."""

    return tuple(
        {
            "name": profile,
            "supported": profile in _SUPPORTED_EGRESS_PROFILES,
            "error_code": (
                None
                if profile in _SUPPORTED_EGRESS_PROFILES
                else "egress_profile_unavailable"
            ),
        }
        for profile in _EGRESS_PROFILES
    )


def egress_profile_supported(profile: str) -> bool:
    return profile in _SUPPORTED_EGRESS_PROFILES


def provider_definitions() -> tuple[ProviderRuntimeDefinition, ...]:
    """Return the stable, code-owned Provider Runtime catalog."""

    return _DEFINITIONS


def _now() -> datetime:
    return datetime.now(UTC)


def _definition(provider_key: str) -> ProviderRuntimeDefinition:
    definition = _BY_KEY.get(provider_key)
    if definition is None:
        raise ProviderRuntimeError(ProviderRuntimeErrorCode.UNKNOWN_PROVIDER)
    return definition


def _local_session_status(definition: ProviderRuntimeDefinition) -> str:
    if not definition.cookie_required:
        return "not_required"
    try:
        cookie = load_javdb_session_cookie()
    except SessionCookieError:
        return "missing"
    return "available" if cookie.strip() else "missing"


def _default_state(definition: ProviderRuntimeDefinition) -> ProviderRuntimeView:
    session_status = _local_session_status(definition)
    return ProviderRuntimeView(
        provider_key=definition.provider_key,
        display_name=definition.display_name,
        scope=definition.scope,
        cookie_required=definition.cookie_required,
        manageable=definition.manageable,
        egress_policy=definition.egress_policy,
        enabled=False,
        runtime_status="disabled",
        configuration_status="not_configured",
        egress_profile="default",
        session_status=session_status,
        session_updated_at=None,
        session_expires_at=None,
        last_health_check_at=None,
        last_success_at=None,
        last_error_code=None,
        last_error_at=None,
        configuration_version=1,
        optimistic_version=1,
    )


def _effective_session_status(
    definition: ProviderRuntimeDefinition,
    state: ProviderRuntimeState | None,
) -> str:
    if state is None:
        return _local_session_status(definition)
    if state.session_expires_at is not None and state.session_expires_at <= _now():
        return "expired"
    local_status = _local_session_status(definition)
    # A process restart or local Cookie removal must never leave a stale positive
    # status in the UI. This projection is deliberately read-only.
    if definition.cookie_required and local_status != "available":
        return local_status
    return state.session_status


def _view(definition: ProviderRuntimeDefinition, state: ProviderRuntimeState | None) -> ProviderRuntimeView:
    if state is None:
        return _default_state(definition)
    effective_session = _effective_session_status(definition, state)
    return ProviderRuntimeView(
        provider_key=definition.provider_key,
        display_name=definition.display_name,
        scope=definition.scope,
        cookie_required=definition.cookie_required,
        manageable=definition.manageable,
        egress_policy=definition.egress_policy,
        enabled=state.enabled,
        runtime_status=state.runtime_status,
        configuration_status=(
            state.configuration_status
            if egress_profile_supported(state.egress_profile)
            else "invalid"
        ),
        egress_profile=state.egress_profile,
        session_status=effective_session,
        session_updated_at=state.session_updated_at,
        session_expires_at=state.session_expires_at,
        last_health_check_at=state.last_health_check_at,
        last_success_at=state.last_success_at,
        last_error_code=state.last_error_code,
        last_error_at=state.last_error_at,
        configuration_version=state.configuration_version,
        optimistic_version=state.optimistic_version,
    )


class ProviderRuntimeRegistry:
    """Database-backed runtime state with explicit optimistic writes."""

    def __init__(self, db: Session) -> None:
        if not isinstance(db, Session):
            raise TypeError("db must be a Session")
        self._db = db

    def sync_known_states(self) -> None:
        """Create missing code-owned rows; call only at startup or a POST flow."""

        existing = set(
            self._db.scalars(select(ProviderRuntimeState.provider_key)).all()
        )
        for definition in _DEFINITIONS:
            if definition.provider_key in existing:
                continue
            self._db.add(
                ProviderRuntimeState(
                    provider_key=definition.provider_key,
                    session_status=(
                        _local_session_status(definition)
                        if definition.cookie_required
                        else "not_required"
                    ),
                )
            )
        self._db.flush()

    def list(self) -> tuple[ProviderRuntimeView, ...]:
        states = {
            state.provider_key: state
            for state in self._db.scalars(
                select(ProviderRuntimeState).order_by(ProviderRuntimeState.provider_key)
            ).all()
        }
        return tuple(_view(definition, states.get(definition.provider_key)) for definition in _DEFINITIONS)

    def get(self, provider_key: str) -> ProviderRuntimeView:
        definition = _definition(provider_key)
        return _view(definition, self._db.get(ProviderRuntimeState, provider_key))

    def _state_for_write(self, provider_key: str) -> tuple[ProviderRuntimeDefinition, ProviderRuntimeState]:
        definition = _definition(provider_key)
        state = self._db.get(ProviderRuntimeState, provider_key)
        if state is None:
            self.sync_known_states()
            state = self._db.get(ProviderRuntimeState, provider_key)
        if state is None:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_REQUEST)
        return definition, state

    def _mutate(
        self,
        state: ProviderRuntimeState,
        *,
        expected_version: int,
        values: dict[str, object],
        configuration_changed: bool = False,
    ) -> ProviderRuntimeState:
        if type(expected_version) is not int or expected_version < 1:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_REQUEST)
        values = {
            **values,
            "optimistic_version": expected_version + 1,
            "updated_at": _now(),
        }
        if configuration_changed:
            values["configuration_version"] = state.configuration_version + 1
        result = self._db.execute(
            update(ProviderRuntimeState)
            .where(
                ProviderRuntimeState.provider_key == state.provider_key,
                ProviderRuntimeState.optimistic_version == expected_version,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.CONCURRENT_UPDATE)
        self._db.flush()
        updated = self._db.get(ProviderRuntimeState, state.provider_key, populate_existing=True)
        if updated is None:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.CONCURRENT_UPDATE)
        return updated

    def save_configuration(
        self,
        provider_key: str,
        *,
        egress_profile: str,
        expected_version: int,
    ) -> ProviderRuntimeView:
        definition, state = self._state_for_write(provider_key)
        if not definition.manageable:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.FIXTURE_PROVIDER)
        if not egress_profile_supported(egress_profile):
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_EGRESS_PROFILE)
        updated = self._mutate(
            state,
            expected_version=expected_version,
            configuration_changed=True,
            values={
                "egress_profile": egress_profile,
                "configuration_status": "valid",
                "runtime_status": "disabled" if not state.enabled else "blocked",
                "last_error_code": None,
                "last_error_at": None,
            },
        )
        return _view(definition, updated)

    def set_enabled(
        self,
        provider_key: str,
        *,
        enabled: bool,
        expected_version: int,
    ) -> ProviderRuntimeView:
        definition, state = self._state_for_write(provider_key)
        if not definition.manageable:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.FIXTURE_PROVIDER)
        if type(enabled) is not bool:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_REQUEST)
        runtime_status = "disabled" if not enabled else "blocked"
        updated = self._mutate(
            state,
            expected_version=expected_version,
            values={"enabled": enabled, "runtime_status": runtime_status},
        )
        return _view(definition, updated)

    def prepare_health_check(
        self,
        provider_key: str,
        *,
        expected_version: int,
    ) -> ProviderRuntimeHealthPlan:
        """Validate local prerequisites without mutating state or using network."""

        definition, state = self._state_for_write(provider_key)
        if type(expected_version) is not int or expected_version < 1:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_REQUEST)
        if state.optimistic_version != expected_version:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.CONCURRENT_UPDATE)
        session_status = _effective_session_status(definition, state)
        blocker: str | None = None
        if not definition.manageable:
            blocker = "fixture_provider"
        elif not state.enabled:
            blocker = "provider_disabled"
        elif state.configuration_status != "valid":
            blocker = "configuration_required"
        elif not egress_profile_supported(state.egress_profile):
            blocker = "egress_profile_unavailable"
        elif definition.cookie_required and session_status != "available":
            blocker = "session_expired" if session_status == "expired" else "session_missing"
        return ProviderRuntimeHealthPlan(
            provider=_view(definition, state),
            expected_version=expected_version,
            blocker_code=blocker,
        )

    def complete_health_check(
        self,
        provider_key: str,
        *,
        expected_version: int,
        success: bool,
        error_code: str | None = None,
    ) -> ProviderRuntimeView:
        """Persist a probe result with the original optimistic-version fence."""

        definition, state = self._state_for_write(provider_key)
        if type(success) is not bool or (
            error_code is not None
            and (
                not isinstance(error_code, str)
                or not error_code
                or len(error_code) > 64
            )
        ):
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.INVALID_REQUEST)
        now = _now()
        session_status = _effective_session_status(definition, state)
        local_blocker: str | None = None
        if not definition.manageable:
            local_blocker = "fixture_provider"
        elif not state.enabled:
            local_blocker = "provider_disabled"
        elif state.configuration_status != "valid":
            local_blocker = "configuration_required"
        elif not egress_profile_supported(state.egress_profile):
            local_blocker = "egress_profile_unavailable"
        elif definition.cookie_required and session_status != "available":
            local_blocker = (
                "session_expired" if session_status == "expired" else "session_missing"
            )

        final_success = success and local_blocker is None
        final_error = None if final_success else (local_blocker or error_code or "runtime_probe_failed")
        if final_success:
            runtime_status = "ready"
        elif final_error == "provider_disabled":
            runtime_status = "disabled"
        elif final_error in {
            "configuration_required",
            "session_missing",
            "session_expired",
            "fixture_provider",
            "egress_profile_unavailable",
        }:
            runtime_status = "blocked"
        else:
            runtime_status = "error"
        updated = self._mutate(
            state,
            expected_version=expected_version,
            values={
                "runtime_status": runtime_status,
                "session_status": session_status,
                "session_updated_at": (
                    now if session_status == "available" else state.session_updated_at
                ),
                "last_health_check_at": now,
                "last_success_at": now if final_success else state.last_success_at,
                "last_error_code": final_error,
                "last_error_at": now if final_error else None,
            },
        )
        return _view(definition, updated)

    def clear_error(self, provider_key: str, *, expected_version: int) -> ProviderRuntimeView:
        definition, state = self._state_for_write(provider_key)
        updated = self._mutate(
            state,
            expected_version=expected_version,
            values={
                "last_error_code": None,
                "last_error_at": None,
                "runtime_status": "disabled" if not state.enabled else "blocked",
            },
        )
        return _view(definition, updated)

    def record_session_import(
        self,
        provider_key: str,
        *,
        available: bool,
        updated_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> ProviderRuntimeView:
        definition, state = self._state_for_write(provider_key)
        if not definition.manageable:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.FIXTURE_PROVIDER)
        timestamp = (updated_at or _now()).astimezone(UTC)
        session_status = "available" if available else "missing"
        result = self._db.execute(
            update(ProviderRuntimeState)
            .where(ProviderRuntimeState.provider_key == state.provider_key)
            .values(
                session_status=session_status,
                session_updated_at=timestamp if available else None,
                session_expires_at=expires_at.astimezone(UTC) if expires_at else None,
                runtime_status=("blocked" if state.enabled and not available else state.runtime_status),
                last_error_code=("session_missing" if state.enabled and not available else None),
                last_error_at=(timestamp if state.enabled and not available else None),
                optimistic_version=ProviderRuntimeState.optimistic_version + 1,
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.CONCURRENT_UPDATE)
        self._db.flush()
        updated = self._db.get(ProviderRuntimeState, state.provider_key, populate_existing=True)
        if updated is None:
            raise ProviderRuntimeError(ProviderRuntimeErrorCode.CONCURRENT_UPDATE)
        return _view(definition, updated)

    def enabled_ready_keys(self) -> frozenset[str]:
        return frozenset(
            view.provider_key for view in self.list() if view.can_search
        )
