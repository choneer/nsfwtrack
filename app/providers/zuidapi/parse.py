"""Bounded MacCMS-style VOD list parsing (ported from nsfwpro maccms)."""

from __future__ import annotations

from typing import Any


class MacCMSParseError(ValueError):
    """Bounded parse failure for MacCMS JSON envelopes."""


def _split_values(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        values = [
            item.strip()
            for item in value.replace("/", ",").split(",")
            if item.strip()
        ]
        return values or None
    return [str(value)]


def parse_maccms_vod_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize only the stable list envelope and item fields."""

    if not isinstance(payload, dict):
        raise MacCMSParseError("MacCMS response root must be an object")
    required = {"code", "list"}
    missing = required - set(payload)
    if missing:
        raise MacCMSParseError(f"MacCMS response is missing fields: {sorted(missing)}")
    if not isinstance(payload.get("list"), list):
        raise MacCMSParseError("MacCMS response list must be an array")
    items: list[dict[str, Any]] = []
    for raw in payload["list"]:
        if not isinstance(raw, dict):
            raise MacCMSParseError("MacCMS list item must be an object")
        if raw.get("vod_id") is None:
            raise MacCMSParseError("MacCMS list item has no stable vod_id")
        items.append(
            {
                "vod_id": str(raw["vod_id"]),
                "vod_name": raw.get("vod_name"),
                "vod_pic": raw.get("vod_pic"),
                "vod_year": str(raw["vod_year"]) if raw.get("vod_year") is not None else None,
                "vod_actor": _split_values(raw.get("vod_actor")),
                "vod_director": raw.get("vod_director"),
                "vod_class": _split_values(raw.get("vod_class")),
                "vod_time": raw.get("vod_time"),
                "vod_play_from": _split_values(raw.get("vod_play_from")),
                "vod_play_url": raw.get("vod_play_url"),
            }
        )
    return {
        "code": payload["code"],
        "message": payload.get("msg"),
        "page": payload.get("page"),
        "page_count": payload.get("pagecount"),
        "limit": payload.get("limit"),
        "total": payload.get("total"),
        "items": items,
    }
