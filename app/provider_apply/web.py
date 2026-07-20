"""Session-bound key material for Provider apply Web requests."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from enum import Enum

from fastapi import Request

from app.auth import SESSION_GENERATION_KEY, is_authenticated
from app.config import get_settings


PROVIDER_APPLY_SESSION_NONCE_KEY = "_provider_apply_nonce"

_SECRET_DOMAIN = b"nsfwtrack.provider-apply.web-secret.v1"
_CONTEXT_DOMAIN = b"nsfwtrack.provider-apply.web-context.v1"
_CONTEXT_PREFIX = "provider-apply:web:v1:"
_NONCE = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ROOT_SECRET_BYTES = 4_096
_MAX_SESSION_GENERATION_BYTES = 512


class ProviderApplyWebErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    SESSION_INVALID = "session_invalid"
    CONFIGURATION_INVALID = "configuration_invalid"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyWebError(RuntimeError):
    code: ProviderApplyWebErrorCode

    def __post_init__(self) -> None:
        if type(self.code) is not ProviderApplyWebErrorCode:
            raise TypeError("code must be ProviderApplyWebErrorCode")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ProviderApplyWebError(code={self.code.value!r})"


class _RedactedValue:
    __slots__ = ()

    def __str__(self) -> str:
        return type(self).__name__

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyWebMaterial(_RedactedValue):
    secret: bytes
    context: str

    def __post_init__(self) -> None:
        if type(self.secret) is not bytes or len(self.secret) != 32:
            raise ValueError("secret must be exactly 32 bytes")
        if (
            type(self.context) is not str
            or not self.context.startswith(_CONTEXT_PREFIX)
            or len(self.context) != len(_CONTEXT_PREFIX) + 64
            or _NONCE.fullmatch(self.context.removeprefix(_CONTEXT_PREFIX)) is None
        ):
            raise ValueError("context is invalid")


def _raise(code: ProviderApplyWebErrorCode) -> None:
    raise ProviderApplyWebError(code) from None


def _strict_bounded_utf8(
    value: object,
    *,
    maximum: int,
    code: ProviderApplyWebErrorCode,
) -> bytes:
    if type(value) is not str or not value:
        _raise(code)
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _raise(code)
    if len(encoded) > maximum:
        _raise(code)
    return encoded


def _session_generation(request: Request) -> bytes:
    try:
        session_generation = request.session.get(SESSION_GENERATION_KEY)
        current_generation = getattr(request.app.state, "session_generation", None)
    except Exception:
        _raise(ProviderApplyWebErrorCode.INVALID_REQUEST)
    session_bytes = _strict_bounded_utf8(
        session_generation,
        maximum=_MAX_SESSION_GENERATION_BYTES,
        code=ProviderApplyWebErrorCode.SESSION_INVALID,
    )
    current_bytes = _strict_bounded_utf8(
        current_generation,
        maximum=_MAX_SESSION_GENERATION_BYTES,
        code=ProviderApplyWebErrorCode.SESSION_INVALID,
    )
    try:
        authenticated = is_authenticated(request)
        generations_match = secrets.compare_digest(session_bytes, current_bytes)
    except Exception:
        _raise(ProviderApplyWebErrorCode.SESSION_INVALID)
    if not authenticated or not generations_match:
        _raise(ProviderApplyWebErrorCode.SESSION_INVALID)
    return session_bytes


def _nonce(request: Request, *, create: bool) -> bytes:
    try:
        value = request.session.get(PROVIDER_APPLY_SESSION_NONCE_KEY)
    except Exception:
        _raise(ProviderApplyWebErrorCode.INVALID_REQUEST)
    if type(value) is str and _NONCE.fullmatch(value) is not None:
        return value.encode("ascii")
    if not create:
        _raise(ProviderApplyWebErrorCode.SESSION_INVALID)
    value = secrets.token_hex(32)
    try:
        request.session[PROVIDER_APPLY_SESSION_NONCE_KEY] = value
    except Exception:
        _raise(ProviderApplyWebErrorCode.SESSION_INVALID)
    return value.encode("ascii")


def _material(request: Request, *, create_nonce: bool) -> ProviderApplyWebMaterial:
    if not isinstance(request, Request):
        _raise(ProviderApplyWebErrorCode.INVALID_REQUEST)
    generation = _session_generation(request)
    nonce = _nonce(request, create=create_nonce)
    try:
        root_value = get_settings().secret_key
    except Exception:
        _raise(ProviderApplyWebErrorCode.CONFIGURATION_INVALID)
    root = _strict_bounded_utf8(
        root_value,
        maximum=_MAX_ROOT_SECRET_BYTES,
        code=ProviderApplyWebErrorCode.CONFIGURATION_INVALID,
    )
    input_material = generation + b"\0" + nonce
    secret = hmac.new(
        root,
        _SECRET_DOMAIN + b"\0" + input_material,
        hashlib.sha256,
    ).digest()
    context_digest = hmac.new(
        root,
        _CONTEXT_DOMAIN + b"\0" + input_material,
        hashlib.sha256,
    ).hexdigest()
    try:
        return ProviderApplyWebMaterial(
            secret=secret,
            context=_CONTEXT_PREFIX + context_digest,
        )
    except (TypeError, ValueError):
        _raise(ProviderApplyWebErrorCode.CONFIGURATION_INVALID)


def ensure_provider_apply_web_material(request: Request) -> ProviderApplyWebMaterial:
    """Derive material for Preview, creating or replacing its session nonce."""

    return _material(request, create_nonce=True)


def get_provider_apply_web_material(request: Request) -> ProviderApplyWebMaterial:
    """Derive material for Confirm without ever creating session state."""

    return _material(request, create_nonce=False)


__all__ = [
    "PROVIDER_APPLY_SESSION_NONCE_KEY",
    "ProviderApplyWebError",
    "ProviderApplyWebErrorCode",
    "ProviderApplyWebMaterial",
    "ensure_provider_apply_web_material",
    "get_provider_apply_web_material",
]
