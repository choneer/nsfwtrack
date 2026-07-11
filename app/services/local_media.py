from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


LOCAL_MEDIA_PREFIX = "/media/"
LOCAL_MEDIA_ROOT = Path("data/media")
ALLOWED_MEDIA_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


class LocalMediaPathError(ValueError):
    pass


def normalize_local_media_path(value: str | None) -> str | None:
    if value is None:
        return None
    path = value.strip()
    if not path:
        return None
    if (
        len(path) > 500
        or not path.startswith(LOCAL_MEDIA_PREFIX)
        or path.startswith("//")
        or "\\" in path
        or "%" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise LocalMediaPathError("invalid local media path")

    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or parsed.path != path:
        raise LocalMediaPathError("invalid local media path")

    relative_path = path.removeprefix(LOCAL_MEDIA_PREFIX)
    segments = relative_path.split("/")
    if not relative_path or any(segment in {"", ".", ".."} for segment in segments):
        raise LocalMediaPathError("invalid local media path")
    if PurePosixPath(relative_path).suffix.casefold() not in ALLOWED_MEDIA_EXTENSIONS:
        raise LocalMediaPathError("unsupported local media type")
    return path


def local_media_url(value: str | None) -> str | None:
    try:
        return normalize_local_media_path(value)
    except LocalMediaPathError:
        return None


def resolve_local_media_file(media_path: str) -> Path:
    normalized = normalize_local_media_path(f"{LOCAL_MEDIA_PREFIX}{media_path}")
    if normalized is None:
        raise LocalMediaPathError("invalid local media path")
    root = LOCAL_MEDIA_ROOT.resolve()
    candidate = (root / normalized.removeprefix(LOCAL_MEDIA_PREFIX)).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise LocalMediaPathError("local media file not found")
    return candidate
