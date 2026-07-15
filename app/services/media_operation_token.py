from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


MAX_MEDIA_OPERATION_TOKEN_LENGTH = 50_000


class MediaOperationTokenError(ValueError):
    pass


def encode_media_operation_token(payload: dict[str, Any], secret_key: str) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(serialized).rstrip(b"=").decode("ascii")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{encoded}.{signature}"
    if len(token) > MAX_MEDIA_OPERATION_TOKEN_LENGTH:
        raise MediaOperationTokenError("token_too_large")
    return token


def decode_media_operation_token(token: str, secret_key: str) -> dict[str, Any]:
    if not token or len(token) > MAX_MEDIA_OPERATION_TOKEN_LENGTH:
        raise MediaOperationTokenError("invalid_token")
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise MediaOperationTokenError("invalid_token") from exc
    expected = hmac.new(
        secret_key.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if len(signature) != 64 or not hmac.compare_digest(signature, expected):
        raise MediaOperationTokenError("invalid_token")
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaOperationTokenError("invalid_token") from exc
    if not isinstance(payload, dict):
        raise MediaOperationTokenError("invalid_token")
    return payload
