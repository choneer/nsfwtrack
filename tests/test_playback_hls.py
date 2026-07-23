"""HLS manifest + MacCMS playback-line parse tests (no segment fetch)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.playback.hls import (
    PlaybackError,
    parse_hls_manifest,
    parse_playback_lines,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "hls"


def test_parse_media_playlist_fixture() -> None:
    text = (FIXTURE / "media.m3u8").read_text(encoding="utf-8")
    manifest = parse_hls_manifest(
        text,
        base_url="https://cdn.example.invalid/path/media.m3u8",
        approved_hosts={"cdn.example.invalid"},
    )
    assert manifest.is_master is False
    assert manifest.encrypted is False
    assert len(manifest.segments) == 2
    assert manifest.segments[0].url.endswith("/seg0.ts")
    assert manifest.segments[0].duration_seconds == 4.0
    d = manifest.to_dict()
    assert d["segment_count"] == 2


def test_parse_master_playlist_fixture() -> None:
    text = (FIXTURE / "master.m3u8").read_text(encoding="utf-8")
    manifest = parse_hls_manifest(
        text,
        base_url="https://cdn.example.invalid/master.m3u8",
        approved_hosts={"cdn.example.invalid"},
    )
    assert manifest.is_master is True
    assert len(manifest.variants) == 2
    assert manifest.variants[0].bandwidth == 800000
    assert manifest.variants[1].resolution == "1280x720"


def test_hls_rejects_unapproved_host() -> None:
    text = (FIXTURE / "media.m3u8").read_text(encoding="utf-8")
    with pytest.raises(PlaybackError, match="not approved"):
        parse_hls_manifest(
            text,
            base_url="https://cdn.example.invalid/media.m3u8",
            approved_hosts={"other.invalid"},
        )


def test_hls_encrypted_key_uri() -> None:
    text = (
        "#EXTM3U\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.example.invalid/key.bin"\n'
        "#EXTINF:1.0,\n"
        "https://cdn.example.invalid/s0.ts\n"
    )
    manifest = parse_hls_manifest(
        text,
        base_url="https://cdn.example.invalid/m.m3u8",
        approved_hosts={"cdn.example.invalid"},
    )
    assert manifest.encrypted is True
    assert manifest.key_uri == "https://cdn.example.invalid/key.bin"


def test_hls_master_reports_audio_and_subtitle_renditions_without_fetching() -> None:
    text = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Main",LANGUAGE="en",DEFAULT=YES,AUTOSELECT=YES,URI="audio/en.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",LANGUAGE="en",DEFAULT=NO,AUTOSELECT=YES,URI="subs/en.m3u8"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO=\"audio\",SUBTITLES=\"subs\"\n"
        "video/low.m3u8\n"
    )
    manifest = parse_hls_manifest(
        text,
        base_url="https://cdn.example.invalid/master.m3u8",
        approved_hosts={"cdn.example.invalid"},
    )
    assert manifest.audio_renditions[0].name == "Main"
    assert manifest.audio_renditions[0].default is True
    assert manifest.subtitle_renditions[0].url.endswith("/subs/en.m3u8")
    assert manifest.to_dict()["subtitle_rendition_count"] == 1


def test_parse_playback_lines_maccms_style() -> None:
    raw = (
        "HD$https://play.example.invalid/a.m3u8#"
        "SD$https://play.example.invalid/b.m3u8"
    )
    lines = parse_playback_lines(
        raw,
        source="zuidapi",
        approved_hosts={"play.example.invalid"},
    )
    assert len(lines) == 2
    assert lines[0].label == "HD"
    assert lines[0].host == "play.example.invalid"
    assert lines[1].label == "SD"


def test_playback_lines_reject_unapproved() -> None:
    with pytest.raises(PlaybackError, match="not approved"):
        parse_playback_lines(
            "X$https://evil.example/a.m3u8",
            approved_hosts={"good.example"},
        )


def test_playback_api_hls_inspect(auth_client) -> None:
    text = (FIXTURE / "media.m3u8").read_text(encoding="utf-8")
    r = auth_client.post(
        "/api/playback/hls/inspect",
        json={
            "text": text,
            "base_url": "https://cdn.example.invalid/media.m3u8",
            "approved_hosts": ["cdn.example.invalid"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["manifest"]["segment_count"] == 2


def test_playback_api_lines_parse(auth_client) -> None:
    r = auth_client.post(
        "/api/playback/lines/parse",
        json={
            "raw": "A$https://cdn.example.invalid/x.m3u8",
            "approved_hosts": ["cdn.example.invalid"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["lines"][0]["label"] == "A"
