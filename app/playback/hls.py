"""Offline HLS manifest inspection + MacCMS playback-line parse.

Upstream references (protocol observation only):
- HLS (#EXTM3U) media playlist / master playlist
- MacCMS vod_play_url ``label$url#label$url`` convention

Does not fetch segments, keys, or variants. Encrypted streams are reported
and remain unresolved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin, urlparse


class PlaybackError(ValueError):
    """Safe, non-secret playback parse error."""


@dataclass(frozen=True, slots=True)
class HlsSegment:
    sequence: int
    url: str
    duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class HlsVariant:
    url: str
    bandwidth: int | None
    resolution: str | None


@dataclass(frozen=True, slots=True)
class HlsManifest:
    is_master: bool
    encrypted: bool
    key_uri: str | None
    segments: tuple[HlsSegment, ...]
    variants: tuple[HlsVariant, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_master": self.is_master,
            "encrypted": self.encrypted,
            "key_uri": self.key_uri,
            "segments": [asdict(s) for s in self.segments],
            "variants": [asdict(v) for v in self.variants],
            "segment_count": len(self.segments),
            "variant_count": len(self.variants),
        }


@dataclass(frozen=True, slots=True)
class PlaybackLine:
    source: str
    label: str
    url: str
    host: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "label": self.label,
            "url": self.url,
            "host": self.host,
        }


def parse_playback_lines(
    raw: str,
    *,
    source: str = "default",
    approved_hosts: set[str] | None = None,
    max_lines: int = 20,
) -> tuple[PlaybackLine, ...]:
    """Parse ``label$url#label$url`` without resolving or fetching URLs."""

    if not isinstance(raw, str) or not raw.strip():
        return ()
    pieces = [piece.strip() for piece in raw.split("#") if piece.strip()]
    if len(pieces) > max_lines:
        raise PlaybackError("playback line count exceeds the approved limit")
    allowed = {host.lower() for host in approved_hosts} if approved_hosts is not None else None
    result: list[PlaybackLine] = []
    for piece in pieces:
        if "$" in piece:
            label, url = piece.split("$", 1)
        else:
            label, url = "default", piece
        label = label.strip() or "default"
        url = url.strip()
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise PlaybackError("playback line is not a safe absolute HTTP(S) URL")
        host = parsed.hostname.lower()
        if allowed is not None and host not in allowed:
            raise PlaybackError(f"playback host is not approved: {host}")
        result.append(PlaybackLine(source, label, url, host))
    return tuple(result)


def parse_hls_manifest(
    text: str,
    *,
    base_url: str,
    approved_hosts: set[str],
    max_segments: int = 10000,
) -> HlsManifest:
    """Parse HLS metadata and validate every discovered URL host."""

    if not isinstance(text, str) or not text.lstrip().startswith("#EXTM3U"):
        raise PlaybackError("HLS manifest must start with #EXTM3U")
    parsed_base = urlparse(base_url)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.hostname:
        raise PlaybackError("HLS base URL is not a safe HTTP(S) URL")
    allowed = {host.lower() for host in approved_hosts}
    if parsed_base.hostname.lower() not in allowed:
        raise PlaybackError("HLS base URL host is not approved")

    lines = [line.strip() for line in text.splitlines()]
    segments: list[HlsSegment] = []
    variants: list[HlsVariant] = []
    encrypted = False
    key_uri: str | None = None
    duration: float | None = None
    sequence = 0
    expect_variant = False
    variant_bandwidth: int | None = None
    variant_resolution: str | None = None

    for line in lines:
        if not line:
            continue
        if line.startswith("#EXT-X-KEY"):
            encrypted = True
            key_uri = _attribute(line, "URI")
            if key_uri:
                key_uri = _approved_url(key_uri, base_url, allowed)
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                sequence = int(line.split(":", 1)[1])
            except ValueError as exc:
                raise PlaybackError("HLS media sequence is invalid") from exc
            continue
        if line.startswith("#EXTINF:"):
            raw_duration = line.split(":", 1)[1].split(",", 1)[0]
            try:
                duration = float(raw_duration)
            except ValueError as exc:
                raise PlaybackError("HLS segment duration is invalid") from exc
            continue
        if line.startswith("#EXT-X-STREAM-INF:"):
            expect_variant = True
            variant_bandwidth = _int_attribute(line, "BANDWIDTH")
            variant_resolution = _attribute(line, "RESOLUTION")
            continue
        if line.startswith("#"):
            continue

        url = _approved_url(line, base_url, allowed)
        if expect_variant:
            variants.append(HlsVariant(url, variant_bandwidth, variant_resolution))
            expect_variant = False
            variant_bandwidth = None
            variant_resolution = None
        else:
            if len(segments) >= max_segments:
                raise PlaybackError("HLS segment count exceeds the approved limit")
            segments.append(HlsSegment(sequence, url, duration))
            sequence += 1
            duration = None

    return HlsManifest(
        bool(variants), encrypted, key_uri, tuple(segments), tuple(variants)
    )


def _approved_url(value: str, base_url: str, approved_hosts: set[str]) -> str:
    url = urljoin(base_url, value.strip())
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise PlaybackError("HLS URL is not a safe absolute HTTP(S) URL")
    if parsed.hostname.lower() not in approved_hosts:
        raise PlaybackError(f"HLS URL host is not approved: {parsed.hostname.lower()}")
    return url


def _attribute(line: str, name: str) -> str | None:
    # Quoted form: RESOLUTION="1280x720"
    marker = name + '="'
    start = line.find(marker)
    if start >= 0:
        start += len(marker)
        end = line.find('"', start)
        return line[start:end] if end >= 0 else None
    # Unquoted form: RESOLUTION=1280x720 or BANDWIDTH=800000
    marker = name + "="
    start = line.find(marker)
    if start < 0:
        return None
    start += len(marker)
    if start < len(line) and line[start] == '"':
        start += 1
        end = line.find('"', start)
        return line[start:end] if end >= 0 else None
    end = line.find(",", start)
    value = line[start:] if end < 0 else line[start:end]
    return value.strip() or None


def _int_attribute(line: str, name: str) -> int | None:
    value = _attribute(line, name)
    if value is None:
        marker = name + "="
        start = line.find(marker)
        if start < 0:
            return None
        start += len(marker)
        end = line.find(",", start)
        value = line[start:] if end < 0 else line[start:end]
    try:
        return int(value)
    except ValueError as exc:
        raise PlaybackError(f"HLS {name} is invalid") from exc
