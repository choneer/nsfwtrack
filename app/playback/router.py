"""Authenticated HLS / playback-line inspect APIs (no segment fetch)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import require_api_auth
from app.playback.hls import PlaybackError, parse_hls_manifest, parse_playback_lines


router = APIRouter(prefix="/api/playback", tags=["playback"])


class HlsInspectBody(BaseModel):
    text: str = Field(..., min_length=7, max_length=2_000_000)
    base_url: str = Field(..., min_length=8, max_length=2048)
    approved_hosts: list[str] = Field(..., min_length=1, max_length=32)
    max_segments: int = Field(default=10000, ge=1, le=20000)


class PlaybackLinesBody(BaseModel):
    raw: str = Field(..., min_length=1, max_length=100_000)
    source: str = Field(default="default", max_length=64)
    approved_hosts: list[str] | None = None
    max_lines: int = Field(default=20, ge=1, le=50)


@router.post("/hls/inspect", dependencies=[Depends(require_api_auth)])
def hls_inspect(body: HlsInspectBody) -> JSONResponse:
    try:
        manifest = parse_hls_manifest(
            body.text,
            base_url=body.base_url,
            approved_hosts=set(body.approved_hosts),
            max_segments=body.max_segments,
        )
        return JSONResponse(
            {"ok": True, "manifest": manifest.to_dict()},
            headers={"Cache-Control": "no-store"},
        )
    except PlaybackError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )


@router.post("/lines/parse", dependencies=[Depends(require_api_auth)])
def playback_lines_parse(body: PlaybackLinesBody) -> JSONResponse:
    try:
        hosts = set(body.approved_hosts) if body.approved_hosts is not None else None
        lines = parse_playback_lines(
            body.raw,
            source=body.source,
            approved_hosts=hosts,
            max_lines=body.max_lines,
        )
        return JSONResponse(
            {
                "ok": True,
                "lines": [line.to_dict() for line in lines],
                "count": len(lines),
            },
            headers={"Cache-Control": "no-store"},
        )
    except PlaybackError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
