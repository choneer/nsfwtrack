from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_item_candidates import (
    MEDIA_ITEM_CANDIDATE_PAGE_SIZE,
    MediaItemCandidateError,
    build_media_item_candidates,
    create_items_from_media_candidates,
    find_media_item_candidates,
    paginate_media_item_candidates,
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
        sha256="b" * 64,
        mime_type="image/png",
        available=available,
    )


def _write_media(media_root: Path, filename: str, *, red: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(red))
    return path


def test_candidate_generation_filters_media_and_marks_all_default_conflicts() -> None:
    items = [
        Item(id=1, title="Used", cover_path="/media/used.png"),
        Item(id=2, title="Matched"),
        Item(id=3, title="Existing", cover_path="/media/existing-cover.png"),
        Item(id=4, title="Foo Bar", cover_path="/media/foo-cover.png"),
    ]
    creators = [Creator(id=5, name="Creator Match", type="person")]
    scan = LocalMediaScan(
        (
            _entry("used.png"),
            _entry("Matched.png"),
            _entry("Creator Match.png"),
            _entry("New Item.cover.png"),
            _entry("Portrait.avatar.png"),
            _entry("Existing.png"),
            _entry("foo-bar.png"),
            _entry("Batch Name.cover.png"),
            _entry("Batch-Name.png"),
            _entry("broken.png", available=False),
        ),
        0,
        0,
        1,
    )

    first = find_media_item_candidates(scan, items, creators)
    second = find_media_item_candidates(scan, items, creators)
    by_filename = {candidate.filename: candidate for candidate in first.candidates}

    assert first.eligible_media == 5
    assert first.excluded_matched == 2
    assert first.excluded_avatar == 1
    assert by_filename["New Item.cover.png"].suggested_title == "New Item"
    assert by_filename["New Item.cover.png"].conflicts == ()
    assert by_filename["Existing.png"].conflicts == ("existing_title",)
    assert by_filename["foo-bar.png"].conflicts == ("existing_normalized_title",)
    assert by_filename["Batch Name.cover.png"].conflicts == ("batch_title",)
    assert by_filename["Batch-Name.png"].conflicts == ("batch_title",)
    assert "Portrait.avatar.png" not in by_filename
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]


def test_candidate_page_is_read_only_bilingual_editable_and_excludes_avatar(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    item_file = _write_media(media_root, "Draft Item.cover.png")
    avatar_file = _write_media(media_root, "Person.avatar.png", red=2)
    snapshot = {item_file: item_file.read_bytes(), avatar_file: avatar_file.read_bytes()}
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    chinese = auth_client.get("/media-library")
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )
    english = auth_client.get("/media-library")

    assert chinese.status_code == 200
    assert "未匹配媒体快速建档" in chinese.text
    assert 'value="Draft Item"' in chinese.text
    assert 'maxlength="255"' in chinese.text
    assert "Person.avatar.png" in chinese.text  # Remains visible in the A2 library.
    assert "Create Items from Unmatched Media" in english.text
    assert "Previewing candidates and editing titles creates nothing" in english.text
    assert "Avatar Files Excluded" in english.text
    with SessionLocal() as db:
        assert db.query(Item).count() == 0
    assert {path: path.read_bytes() for path in snapshot} == snapshot


def test_single_creation_requires_strict_confirmation_and_accepts_edited_title(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_file = _write_media(media_root, "Original.cover.png")
    original = media_file.read_bytes()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        candidate_id = build_media_item_candidates(db).candidates[0].candidate_id
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    page = auth_client.get("/media-library")
    assert page.text.count("data-strict-confirm-message") >= 1
    for data in (
        {"candidate_id": candidate_id, "title": "Edited Title", "create_page": "1"},
        {
            "candidate_id": candidate_id,
            "title": "Edited Title",
            "create_page": "1",
            "confirm": "1",
            "confirmation_text": "WRONG",
        },
    ):
        auth_client.post("/media-library/item-candidates/create", data=data)
    with SessionLocal() as db:
        assert db.query(Item).count() == 0

    response = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": candidate_id,
            "title": " Edited Title ",
            "create_page": "1",
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )

    assert "已从本地媒体创建 1 个条目" in response.text
    with SessionLocal() as db:
        item = db.scalar(db.query(Item).statement)
        assert item is not None
        assert item.title == "Edited Title"
        assert item.cover_path == "/media/Original.cover.png"
    assert media_file.read_bytes() == original


def test_default_existing_conflict_can_be_resolved_by_editing_title(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Existing.png")
    _write_media(media_root, "other.png", red=1)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Existing", cover_path="/media/other.png"))
        db.commit()
        candidate = build_media_item_candidates(db).candidates[0]
        assert candidate.conflicts == ("existing_title",)

    response = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": candidate.candidate_id,
            "title": "Resolved Title",
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert "已从本地媒体创建 1 个条目" in response.text
    with SessionLocal() as db:
        created = db.scalar(db.query(Item).filter(Item.title == "Resolved Title").statement)
        assert created is not None
        assert created.cover_path == "/media/Existing.png"


def test_existing_exact_normalized_and_selected_batch_title_conflicts_reject_all(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "First.png")
    _write_media(media_root, "Second.png", red=2)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Taken Title", cover_path="/media/already-used.png"))
        db.commit()
        candidates = build_media_item_candidates(db).candidates
        candidate_ids = [candidate.candidate_id for candidate in candidates]

    exact = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": candidate_ids[0],
            "title": "Taken Title",
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    normalized = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": candidate_ids[0],
            "title": "taken-title",
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    batch = auth_client.post(
        "/media-library/item-candidates/create-bulk",
        data={
            "candidate_ids": candidate_ids,
            "candidate_titles": ["Same Title", "same-title"],
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert "与已有条目标题相同" in exact.text
    assert "与已有条目规范化同名" in normalized.text
    assert "本批次内规范化同名" in batch.text
    with SessionLocal() as db:
        assert db.query(Item).count() == 1


def test_bulk_creation_rejects_cross_page_then_creates_only_selected_rows(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    files: dict[Path, bytes] = {}
    for index in range(MEDIA_ITEM_CANDIDATE_PAGE_SIZE + 1):
        path = _write_media(media_root, f"New {index:02d}.cover.png", red=index)
        files[path] = path.read_bytes()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        candidate_scan = build_media_item_candidates(db)
        first_page = paginate_media_item_candidates(candidate_scan, 1)
        second_page = paginate_media_item_candidates(candidate_scan, 2)
        selected = [first_page.rows[0], first_page.rows[1]]

    rejected = auth_client.post(
        "/media-library/item-candidates/create-bulk",
        data={
            "candidate_ids": [selected[0].candidate_id, second_page.rows[0].candidate_id],
            "candidate_titles": ["First Page", "Second Page"],
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    assert "只能处理当前页" in rejected.text
    with SessionLocal() as db:
        assert db.query(Item).count() == 0

    created = auth_client.post(
        "/media-library/item-candidates/create-bulk",
        data={
            "candidate_ids": [candidate.candidate_id for candidate in selected],
            "candidate_titles": ["Edited One", "Edited Two"],
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    assert "已从本地媒体创建 2 个条目" in created.text
    with SessionLocal() as db:
        items = db.query(Item).order_by(Item.title).all()
        assert [(item.title, item.cover_path) for item in items] == [
            ("Edited One", selected[0].media_path),
            ("Edited Two", selected[1].media_path),
        ]
    assert {path: path.read_bytes() for path in files} == files


def test_stale_forged_and_malformed_submissions_create_nothing(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_media(media_root, "Stale.png")
    _write_media(media_root, "Other.png", red=2)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        candidates = build_media_item_candidates(db).candidates
        stale = next(candidate for candidate in candidates if candidate.filename == "Stale.png")
        other = next(candidate for candidate in candidates if candidate.filename == "Other.png")
        db.add(Creator(name="Occupier", type="person", avatar_path=stale.media_path))
        db.commit()

    stale_response = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": stale.candidate_id,
            "title": "Stale",
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    forged_response = auth_client.post(
        "/media-library/item-candidates/create",
        data={
            "candidate_id": "0" * 24,
            "title": "Forged",
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )
    malformed_response = auth_client.post(
        "/media-library/item-candidates/create-bulk",
        data={
            "candidate_ids": [other.candidate_id],
            "candidate_titles": ["One", "Extra"],
            "create_page": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert "候选已过期、被占用或媒体不可用" in stale_response.text
    assert "候选已过期、被占用或媒体不可用" in forged_response.text
    assert "候选与标题数据不一致" in malformed_response.text
    with SessionLocal() as db:
        assert db.query(Item).count() == 0


def test_database_failure_rolls_back_entire_batch_without_touching_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    first_file = _write_media(media_root, "Good.png")
    second_file = _write_media(media_root, "Fail.png", red=2)
    snapshot = {first_file: first_file.read_bytes(), second_file: second_file.read_bytes()}
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    def fail_second_insert(_mapper, _connection, target: Item) -> None:
        if target.title == "Fail Insert":
            raise RuntimeError("injected insert failure")

    event.listen(Item, "before_insert", fail_second_insert)
    try:
        with SessionLocal() as db:
            candidates = build_media_item_candidates(db).candidates
            with pytest.raises(MediaItemCandidateError, match="create_failed") as exc_info:
                create_items_from_media_candidates(
                    db,
                    [candidate.candidate_id for candidate in candidates],
                    ["Good Insert", "Fail Insert"],
                    current_page=1,
                )
            assert exc_info.value.code == "create_failed"
            assert db.query(Item).count() == 0
    finally:
        event.remove(Item, "before_insert", fail_second_insert)

    assert {path: path.read_bytes() for path in snapshot} == snapshot


def test_item_candidate_write_routes_require_login_and_reject_get(
    client: TestClient,
) -> None:
    for path in (
        "/media-library/item-candidates/create",
        "/media-library/item-candidates/create-bulk",
    ):
        assert client.post(path, follow_redirects=False).status_code == 303
        assert client.get(path).status_code == 405
