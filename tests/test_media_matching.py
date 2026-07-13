from __future__ import annotations

import struct
import zlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services import media_matching
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_matching import (
    MEDIA_MATCH_PAGE_SIZE,
    build_local_media_matches,
    match_local_media,
    normalize_match_name,
    paginate_media_matches,
)
from app.services.settings import save_app_settings


def _png_bytes(red: int = 0) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, 0, 0)))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def _entry(filename: str, *, available: bool = True) -> LocalMediaEntry:
    return LocalMediaEntry(
        media_path=f"/media/{filename}",
        filename=filename,
        size=64,
        sha256="a" * 64,
        mime_type="image/png",
        available=available,
    )


def _scan(*filenames: str) -> LocalMediaScan:
    return LocalMediaScan(tuple(_entry(filename) for filename in filenames), 0, 0, 0)


def _write_media(media_root: Path, filename: str, *, red: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(red))
    return path


def test_normalized_exact_and_suffix_matching_is_stable_and_explainable() -> None:
    items = [
        Item(id=1, title="Exact Item"),
        Item(id=2, title="Ｎｏｒｍ Item"),
        Item(id=3, title="Suffix Item"),
    ]
    creators = [Creator(id=4, name="Creator Name", type="person")]
    scan = _scan(
        "Exact Item.png",
        "norm-item.png",
        "Suffix Item.cover.png",
        "Creator_Name.avatar.png",
    )

    first = match_local_media(scan, items, creators)
    second = match_local_media(scan, items, creators)

    assert normalize_match_name(" Ａ-b_C ") == "abc"
    assert [(row.target_type, row.target_id, row.reason, row.confidence) for row in first.candidates] == [
        ("creator", 4, "suffix_normalized", "medium"),
        ("item", 1, "exact", "high"),
        ("item", 2, "normalized", "medium"),
        ("item", 3, "suffix_exact", "high"),
    ]
    assert [row.candidate_id for row in first.candidates] == [
        row.candidate_id for row in second.candidates
    ]
    assert first.ready == 4
    assert first.conflicts == 0
    assert first.unmatched_media == 0


def test_suffix_limits_target_type_and_both_ambiguity_directions_are_conflicts() -> None:
    items = [Item(id=1, title="Shared"), Item(id=2, title="Only Item")]
    creators = [Creator(id=3, name="Shared", type="person")]
    result = match_local_media(
        _scan("Shared.png", "Only Item.png", "Only Item.cover.png", "Only Item.avatar.png"),
        items,
        creators,
    )

    shared = [row for row in result.candidates if row.filename == "Shared.png"]
    only_item = [row for row in result.candidates if row.target_id == 2]
    assert {row.target_type for row in shared} == {"item", "creator"}
    assert all("media_multiple_targets" in row.conflicts for row in shared)
    assert {row.filename for row in only_item} == {"Only Item.png", "Only Item.cover.png"}
    assert all("target_multiple_media" in row.conflicts for row in only_item)
    assert not any(row.filename == "Only Item.avatar.png" for row in result.candidates)
    assert result.unmatched_media == 1
    assert result.ready == 0


def test_used_unavailable_media_and_occupied_targets_are_excluded() -> None:
    used_path = "/media/used.png"
    items = [
        Item(id=1, title="Used", cover_path=used_path),
        Item(id=2, title="Open"),
        Item(id=3, title="Occupied", cover_path="/media/other.png"),
    ]
    creators = [
        Creator(id=4, name="Creator", type="person", avatar_path="/media/avatar.png")
    ]
    scan = LocalMediaScan(
        (
            _entry("used.png"),
            _entry("Open.png", available=False),
            _entry("Occupied.png"),
            _entry("Creator.png"),
        ),
        0,
        0,
        1,
    )

    result = match_local_media(scan, items, creators)

    assert result.candidates == ()
    assert result.unused_media == 2
    assert result.unmatched_media == 2
    assert result.empty_items == 1
    assert result.empty_creators == 0


def test_candidate_page_is_read_only_bilingual_and_marks_conflicts(
    auth_client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Shared.png")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Shared"),
                Creator(name="Shared", type="person"),
            ]
        )
        db.commit()

    chinese = auth_client.get("/media-library")
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )
    english = auth_client.get("/media-library")

    assert chinese.status_code == 200
    assert "本地媒体候选配对" in chinese.text
    assert "歧义冲突" in chinese.text
    assert "冲突，禁止应用" in chinese.text
    assert "Local Media Candidate Matching" in english.text
    assert "Candidate generation is read-only" in english.text
    assert "Ambiguous Conflict" in english.text
    assert 'name="candidate_ids"' not in english.text
    with SessionLocal() as db:
        assert all(item.cover_path is None for item in db.query(Item).all())
        assert all(creator.avatar_path is None for creator in db.query(Creator).all())


def test_forged_conflict_candidate_is_rejected_server_side(
    auth_client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Shared.png")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Shared"),
                Creator(name="Shared", type="person"),
            ]
        )
        db.commit()
        candidate_id = build_local_media_matches(db).candidates[0].candidate_id

    response = auth_client.post(
        "/media-library/matches/apply",
        data={"candidate_id": candidate_id, "match_page": "1", "confirm": "1"},
        follow_redirects=True,
    )

    assert "冲突候选不能应用" in response.text
    with SessionLocal() as db:
        assert all(item.cover_path is None for item in db.query(Item).all())
        assert all(creator.avatar_path is None for creator in db.query(Creator).all())


def test_single_match_requires_confirmation_and_strict_text_without_overwrite(
    auth_client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_file = _write_media(media_root, "Single.cover.png")
    original = media_file.read_bytes()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="Single")
        db.add(item)
        db.commit()
        item_id = item.id
        candidate_id = build_local_media_matches(db).candidates[0].candidate_id
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    page = auth_client.get("/media-library")
    assert "data-strict-confirm-message" in page.text
    for data in (
        {"candidate_id": candidate_id, "match_page": "1"},
        {
            "candidate_id": candidate_id,
            "match_page": "1",
            "confirm": "1",
            "confirmation_text": "WRONG",
        },
    ):
        auth_client.post("/media-library/matches/apply", data=data)
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path is None

    applied = auth_client.post(
        "/media-library/matches/apply",
        data={
            "candidate_id": candidate_id,
            "match_page": "1",
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert "候选配对已应用：1 项" in applied.text
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == "/media/Single.cover.png"
    assert media_file.read_bytes() == original


def test_stale_candidate_does_not_overwrite_existing_cover(
    auth_client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Stale.png")
    _write_media(media_root, "existing.png", red=4)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="Stale")
        db.add(item)
        db.commit()
        item_id = item.id
        candidate_id = build_local_media_matches(db).candidates[0].candidate_id
        item.cover_path = "/media/existing.png"
        db.commit()

    response = auth_client.post(
        "/media-library/matches/apply",
        data={"candidate_id": candidate_id, "match_page": "1", "confirm": "1"},
        follow_redirects=True,
    )

    assert "候选已过期" in response.text
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == "/media/existing.png"


def test_commit_time_guard_does_not_overwrite_a_newly_occupied_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Race A.png")
    _write_media(media_root, "Race B.png", red=3)
    _write_media(media_root, "existing.png", red=5)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        first = Item(title="Race A")
        second = Item(title="Race B")
        db.add_all([first, second])
        db.commit()
        first_id = first.id
        second_id = second.id
        stale_scan = build_local_media_matches(db)
        candidate_ids = [candidate.candidate_id for candidate in stale_scan.candidates]
        second.cover_path = "/media/existing.png"
        db.commit()
        monkeypatch.setattr(
            media_matching,
            "build_local_media_matches",
            lambda _db: stale_scan,
        )

        try:
            media_matching.apply_local_media_matches(db, candidate_ids, current_page=1)
        except media_matching.MediaMatchError as exc:
            assert exc.code == "target_already_assigned"
        else:
            raise AssertionError("commit-time overwrite guard was not enforced")

        db.expire_all()
        assert db.get(Item, first_id).cover_path is None
        assert db.get(Item, second_id).cover_path == "/media/existing.png"


def test_bulk_match_rejects_cross_page_atomically_then_applies_selected_page_rows(
    auth_client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    files = {}
    with SessionLocal() as db:
        for index in range(MEDIA_MATCH_PAGE_SIZE + 1):
            name = f"Candidate {index:02d}"
            path = _write_media(media_root, f"{name}.cover.png", red=index)
            files[path] = path.read_bytes()
            db.add(Item(title=name))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        match_scan = build_local_media_matches(db)
        first_page = paginate_media_matches(match_scan, 1)
        second_page = paginate_media_matches(match_scan, 2)
        selected = [first_page.rows[0].candidate_id, first_page.rows[1].candidate_id]

    rejected = auth_client.post(
        "/media-library/matches/apply-bulk",
        data={
            "candidate_ids": [selected[0], second_page.rows[0].candidate_id],
            "match_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    assert "只能处理当前页" in rejected.text
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.cover_path.is_not(None)).count() == 0

    applied = auth_client.post(
        "/media-library/matches/apply-bulk",
        data={
            "candidate_ids": selected,
            "match_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    assert "候选配对已应用：2 项" in applied.text
    with SessionLocal() as db:
        assigned = db.query(Item).filter(Item.cover_path.is_not(None)).all()
        assert len(assigned) == 2
    assert {path: path.read_bytes() for path in files} == files


def test_match_write_routes_require_login_and_reject_get(client: TestClient) -> None:
    for path in (
        "/media-library/matches/apply",
        "/media-library/matches/apply-bulk",
    ):
        assert client.post(path, follow_redirects=False).status_code == 303
        assert client.get(path).status_code == 405
