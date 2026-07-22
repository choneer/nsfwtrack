"""Read-only Jiuse playback-page parsing (ported from nsfwpro).

Never executes provider JavaScript and never downloads a manifest or segment.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse


class JiuseParseError(ValueError):
    """Bounded parse failure for Jiuse HTML."""


class _PageDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attributes: list[dict[str, str]] = []
        self.json_scripts: list[str] = []
        self._script_type = ""
        self._script_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = {key.lower(): value or "" for key, value in attrs}
        self.attributes.append(normalized)
        if tag.lower() == "script":
            self._script_type = normalized.get("type", "").lower()
            self._script_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            if self._script_type == "application/json":
                self.json_scripts.append("".join(self._script_buffer))
            self._script_type = ""
            self._script_buffer = []

    def handle_data(self, data: str) -> None:
        if self._script_type:
            self._script_buffer.append(data)


def _walk_values(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower(), child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _host(value: str) -> str | None:
    parsed = urlparse(value if "://" in value else "//" + value)
    return parsed.hostname.lower() if parsed.hostname else None


def _candidate_value(attributes: list[dict[str, str]], names: set[str]) -> str | None:
    for attrs in attributes:
        for name in names:
            value = _string(attrs.get(name, ""))
            if value:
                return value
    return None


def _candidate_list(attributes: list[dict[str, str]], names: set[str]) -> list[str]:
    values: list[str] = []
    for attrs in attributes:
        for name in names:
            raw = _string(attrs.get(name, ""))
            if raw:
                values.extend(
                    item.strip()
                    for item in re.split(r"[,\s]+", raw)
                    if item.strip()
                )
    return list(dict.fromkeys(values))


def _from_json(scripts: list[str]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for raw in scripts:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for key, child in _walk_values(value):
            if key in {"vid", "video_id", "videoid"} and "video_id" not in found:
                found["video_id"] = _string(child)
            elif key in {"title", "name"} and "title" not in found:
                found["title"] = _string(child)
            elif key in {"hls", "m3u8", "manifest", "manifest_url"} and "manifest_path" not in found:
                found["manifest_path"] = _string(child)
            elif key in {"cdns", "cdn", "cdn_hosts"} and "cdn_values" not in found:
                if isinstance(child, list):
                    found["cdn_values"] = [
                        item for item in (_string(item) for item in child) if item
                    ]
                elif isinstance(child, str):
                    found["cdn_values"] = [child]
            elif key in {"duration", "length"} and "duration" not in found:
                found["duration"] = _string(child)
            elif key in {"author", "uploader", "creator"} and "author" not in found:
                found["author"] = _string(child)
            elif key in {"thumbnail", "thumb", "poster"} and "thumbnail" not in found:
                found["thumbnail"] = _string(child)
    return found


def _absolute_manifest(path: str, page_url: str, cdns: list[str]) -> str:
    if "://" in path:
        return path
    if path.startswith("/") or path.startswith("."):
        return urljoin(page_url, path)
    if cdns:
        return urljoin("https://" + cdns[0].rstrip("/") + "/", path)
    return urljoin(page_url, path)


def _assert_exact_hosts(
    payload: dict[str, Any], page_url: str, approved_hosts: set[str]
) -> None:
    if not approved_hosts:
        raise JiuseParseError("no approved Jiuse hosts are available")
    page_host = urlparse(page_url).hostname
    if not page_host or page_host.lower() not in approved_hosts:
        raise JiuseParseError("Jiuse page host is not approved")
    manifest_url = payload.get("manifest_url")
    if manifest_url:
        host = urlparse(str(manifest_url)).hostname
        if not host or host.lower() not in approved_hosts:
            raise JiuseParseError("Jiuse manifest host is not approved")
    for host_value in payload.get("cdn_hosts", []):
        host = _host(str(host_value))
        if host and host not in approved_hosts:
            raise JiuseParseError(f"Jiuse CDN host is not approved: {host}")


def parse_jiuse_video_html(
    html: str,
    *,
    page_url: str,
    approved_hosts: set[str] | None = None,
) -> dict[str, Any]:
    """Extract a playback candidate without executing scripts or fetching media."""

    parser = _PageDataParser()
    parser.feed(html)
    parser.close()
    payload = _from_json(parser.json_scripts)

    video_id = payload.get("video_id") or _candidate_value(
        parser.attributes,
        {"data-vid", "data-video-id", "data-videoid"},
    )
    title = payload.get("title") or _candidate_value(parser.attributes, {"data-title"})
    manifest_path = payload.get("manifest_path") or _candidate_value(
        parser.attributes,
        {"data-hls", "data-m3u8", "data-manifest", "data-manifest-url"},
    )
    cdn_values = payload.get("cdn_values") or _candidate_list(
        parser.attributes,
        {"data-cdn", "data-cdns", "data-cdn-host"},
    )
    if not video_id:
        raise JiuseParseError("Jiuse page has no explicit video identifier")
    if not manifest_path:
        raise JiuseParseError("Jiuse page has no explicit HLS manifest")

    manifest_url = _absolute_manifest(str(manifest_path), page_url, list(cdn_values or []))
    result: dict[str, Any] = {
        "video_id": video_id,
        "title": title,
        "duration": payload.get("duration"),
        "author": payload.get("author"),
        "thumbnail": payload.get("thumbnail"),
        "page_url": page_url,
        "manifest_url": manifest_url,
        "manifest_format": "hls",
        "cdn_hosts": list(
            dict.fromkeys(
                host
                for host in (_host(item) for item in (cdn_values or []))
                if host
            )
        ),
    }
    if approved_hosts is not None:
        _assert_exact_hosts(result, page_url, {host.lower() for host in approved_hosts})
    return result
