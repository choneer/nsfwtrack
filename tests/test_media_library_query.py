from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Item
from app.services import local_media
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_item_candidates import build_media_item_candidates
from app.services.media_library_query import (
    MEDIA_LIST_PAGE_SIZE,
    query_media_library,
)
from app.services.media_matching import build_local_media_matches


def _entry(
    filename: str,
    *,
    size: int,
    available: bool = True,
    sha256: str | None = None,
) -> LocalMediaEntry:
    if sha256 is None:
        sha256 = hashlib.sha256(filename.encode()).hexdigest() if available else ""
    return LocalMediaEntry(
        media_path=f"/media/{filename}",
        filename=filename,
        size=size,
        sha256=sha256,
        mime_type="image/png" if available else "",
        available=available,
        detail="" if available else "invalid_image",
    )


def _scan(*entries: LocalMediaEntry) -> LocalMediaScan:
    return LocalMediaScan(tuple(entries), 0, 0, sum(not row.available for row in entries))


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(media_root: Path, filename: str, *, extra: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_paths(page_text: str) -> list[str]:
    return re.findall(r'data-media-path="([^"]+)"', page_text)


def _media_library_link_queries(page_text: str) -> list[dict[str, list[str]]]:
    hrefs = re.findall(r'href="([^"]+)"', html.unescape(page_text))
    return [
        parse_qs(urlsplit(href).query)
        for href in hrefs
        if urlsplit(href).path == "/media-library"
    ]


def test_query_normalizes_search_and_safely_falls_back_for_invalid_parameters() -> None:
    scan = _scan(
        _entry("zeta.png", size=30),
        _entry("Folder/Ａrt.png", size=20),
        _entry("alpha.png", size=10),
    )

    searched = query_media_library(
        scan,
        set(),
        q=" folder/art ",
        status="all",
        sort="filename_asc",
        page="not-a-page",
    )
    path_searched = query_media_library(
        scan,
        set(),
        q="/MEDIA/folder",
        status="all",
        sort="filename_asc",
        page=1,
    )
    fallback = query_media_library(
        scan,
        set(),
        q="x" * 201,
        status="not-a-status",
        sort="not-a-sort",
        page="-50",
    )

    assert [row.entry.filename for row in searched.rows] == ["Folder/Ａrt.png"]
    assert searched.filters.q == "folder/art"
    assert searched.page_info.page == 1
    assert [row.entry.filename for row in path_searched.rows] == ["Folder/Ａrt.png"]
    assert fallback.filters.q == ""
    assert fallback.filters.status == "all"
    assert fallback.filters.sort == "filename_asc"
    assert fallback.page_info.page == 1
    assert [row.entry.filename for row in fallback.rows] == [
        "alpha.png",
        "Folder/Ａrt.png",
        "zeta.png",
    ]


def test_query_supports_available_damaged_used_and_unused_filters() -> None:
    scan = _scan(
        _entry("available-used.png", size=10),
        _entry("available-unused.png", size=20),
        _entry("damaged-used.png", size=0, available=False),
        _entry("damaged-unused.png", size=0, available=False),
    )
    used_paths = {"/media/available-used.png", "/media/damaged-used.png"}

    def names(status: str) -> list[str]:
        result = query_media_library(
            scan,
            used_paths,
            q=None,
            status=status,
            sort=None,
            page=1,
        )
        return [row.entry.filename for row in result.rows]

    assert names("all") == [
        "available-unused.png",
        "available-used.png",
        "damaged-unused.png",
        "damaged-used.png",
    ]
    assert names("available") == ["available-unused.png", "available-used.png"]
    assert names("damaged") == ["damaged-unused.png", "damaged-used.png"]
    assert names("used") == ["available-used.png", "damaged-used.png"]
    assert names("unused") == ["available-unused.png", "damaged-unused.png"]


def test_query_builds_stable_duplicate_groups_and_supports_sha_prefix_search() -> None:
    duplicate_digest = "a" * 64
    scan = _scan(
        _entry("copies/Zulu.png", size=12, sha256=duplicate_digest),
        _entry("copies/alpha.png", size=12, sha256=duplicate_digest.upper()),
        _entry("single.png", size=7, sha256="b" * 64),
        _entry("empty.png", size=9, sha256=""),
        _entry("short.png", size=9, sha256="c" * 63),
        _entry("damaged.png", size=0, available=False, sha256=duplicate_digest),
        _entry("same-path.png", size=5, sha256="d" * 64),
        _entry("same-path.png", size=5, sha256="d" * 64),
    )

    duplicate = query_media_library(
        scan,
        set(),
        q=None,
        status="duplicate",
        sort="filename_asc",
        page=1,
    )
    prefix = query_media_library(
        scan,
        set(),
        q="A" * 16,
        status="all",
        sort="filename_desc",
        page=1,
    )

    assert duplicate.duplicate_summary.group_count == 1
    assert duplicate.duplicate_summary.file_count == 2
    assert duplicate.duplicate_summary.reclaimable_bytes == 12
    assert [row.entry.filename for row in duplicate.rows] == [
        "copies/alpha.png",
        "copies/Zulu.png",
    ]
    assert duplicate.rows[0].duplicate_count == 2
    assert duplicate.rows[0].duplicate_paths == ("/media/copies/Zulu.png",)
    assert duplicate.rows[1].duplicate_paths == ("/media/copies/alpha.png",)
    assert [row.entry.filename for row in prefix.rows] == [
        "copies/Zulu.png",
        "copies/alpha.png",
    ]


def test_query_supports_stable_filename_and_size_sorting() -> None:
    scan = _scan(
        _entry("bravo.png", size=20),
        _entry("Alpha.png", size=30),
        _entry("charlie.png", size=20),
    )

    def names(sort: str) -> list[str]:
        result = query_media_library(
            scan,
            set(),
            q=None,
            status=None,
            sort=sort,
            page=1,
        )
        return [row.entry.filename for row in result.rows]

    assert names("filename_asc") == ["Alpha.png", "bravo.png", "charlie.png"]
    assert names("filename_desc") == ["charlie.png", "bravo.png", "Alpha.png"]
    assert names("size_asc") == ["bravo.png", "charlie.png", "Alpha.png"]
    assert names("size_desc") == ["Alpha.png", "bravo.png", "charlie.png"]


def test_query_paginates_twenty_rows_and_clamps_large_pages() -> None:
    scan = _scan(*(_entry(f"File {index:02d}.png", size=index) for index in range(45)))

    second = query_media_library(
        scan,
        set(),
        q=None,
        status=None,
        sort=None,
        page=2,
    )
    clamped = query_media_library(
        scan,
        set(),
        q=None,
        status=None,
        sort=None,
        page=999,
    )

    assert MEDIA_LIST_PAGE_SIZE == 20
    assert second.page_info.page == 2
    assert second.page_info.total == 45
    assert len(second.rows) == 20
    assert second.rows[0].entry.filename == "File 20.png"
    assert second.rows[-1].entry.filename == "File 39.png"
    assert clamped.page_info.page == 3
    assert len(clamped.rows) == 5


def test_page_search_status_sort_and_empty_result_are_bilingual(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    used = _write_gif(media_root, "Folder/Used.gif", extra=20)
    unused = _write_gif(media_root, "Folder/Unused.gif", extra=5)
    damaged = media_root / "Folder" / "Damaged.gif"
    damaged.write_bytes(b"not-an-image")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Used Item", cover_path="/media/Folder/Used.gif"))
        db.commit()

    used_page = auth_client.get(
        "/media-library",
        params={
            "media_q": "folder",
            "media_status": "used",
            "media_sort": "size_desc",
        },
    )
    damaged_page = auth_client.get(
        "/media-library",
        params={"media_status": "damaged"},
    )
    empty_page = auth_client.get(
        "/media-library",
        params={"media_q": "missing-name"},
    )
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )
    english = auth_client.get("/media-library")

    assert _media_paths(used_page.text) == ["/media/Folder/Used.gif"]
    assert _media_paths(damaged_page.text) == ["/media/Folder/Damaged.gif"]
    assert _media_paths(empty_page.text) == []
    assert "当前搜索和筛选条件没有匹配" in empty_page.text
    assert "媒体文件浏览" in used_page.text
    assert "Browse Media Files" in english.text
    assert "Filename / Path / SHA-256 Search" in english.text
    assert "Damaged or Unavailable" in english.text
    assert "Duplicate Content" in english.text
    assert used.read_bytes() == _gif_bytes(20)
    assert unused.read_bytes() == _gif_bytes(5)
    assert damaged.read_bytes() == b"not-an-image"


def test_duplicate_page_reports_summary_paths_and_remains_read_only(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    first = _write_gif(media_root, "Copies/First.gif", extra=12)
    second = _write_gif(media_root, "Copies/Second.gif", extra=12)
    unique = _write_gif(media_root, "Unique.gif", extra=3)
    damaged = media_root / "Copies" / "Damaged.gif"
    damaged.write_bytes(_gif_bytes(12)[:-1])
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path="/media/Copies/First.gif"))
        db.commit()
        before_items = [(item.id, item.title, item.cover_path) for item in db.query(Item)]
        before_matches = [
            candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        ]
        before_creates = [
            candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        ]
    before_files = {
        path: path.read_bytes()
        for path in (first, second, unique, damaged)
    }
    digest_prefix = hashlib.sha256(first.read_bytes()).hexdigest()[:20].upper()

    response = auth_client.get(
        "/media-library",
        params={
            "match_page": "2",
            "create_page": "3",
            "media_page": "1",
            "media_q": digest_prefix,
            "media_status": "duplicate",
            "media_sort": "filename_desc",
        },
    )
    assert response.status_code == 200
    assert _media_paths(response.text) == [
        "/media/Copies/Second.gif",
        "/media/Copies/First.gif",
    ]
    assert 'data-media-duplicate-groups>1</strong>' in response.text
    assert 'data-media-duplicate-files>2</strong>' in response.text
    assert f'data-media-reclaimable-bytes>{len(first.read_bytes())} B</strong>' in response.text
    assert response.text.count('data-media-duplicate-count="2"') == 2
    assert 'data-media-duplicate-path="/media/Copies/First.gif"' in response.text
    assert 'data-media-duplicate-path="/media/Copies/Second.gif"' in response.text
    assert f'name="media_q" value="{digest_prefix}"' in response.text
    assert '<option value="duplicate" selected>' in response.text
    assert '<option value="filename_desc" selected>' in response.text
    with SessionLocal() as db:
        assert [(item.id, item.title, item.cover_path) for item in db.query(Item)] == before_items
        assert [
            candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        ] == before_matches
        assert [
            candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        ] == before_creates
    assert {path: path.read_bytes() for path in before_files} == before_files


def test_all_three_pagers_preserve_each_other_and_media_filters(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    for index in range(21):
        matched_name = f"Asset Match {index:02d}"
        _write_gif(media_root, f"{matched_name}.gif", extra=index)
        _write_gif(media_root, f"Asset Create {index:02d}.cover.gif", extra=index + 30)
        _write_gif(media_root, f"Asset Duplicate {index:02d}.gif", extra=99)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all([Item(title=f"Asset Match {index:02d}") for index in range(21)])
        db.commit()

    page = auth_client.get(
        "/media-library",
        params={
            "media_page": "2",
            "match_page": "2",
            "create_page": "2",
            "media_q": "Asset",
            "media_status": "duplicate",
            "media_sort": "filename_desc",
        },
    )
    queries = _media_library_link_queries(page.text)
    expected_filters = {
        "media_q": ["Asset"],
        "media_status": ["duplicate"],
        "media_sort": ["filename_desc"],
    }

    def has_state(**pages: str) -> bool:
        return any(
            all(query.get(key) == value for key, value in expected_filters.items())
            and all(query.get(key) == [value] for key, value in pages.items())
            for query in queries
        )

    assert page.status_code == 200
    assert has_state(media_page="1", match_page="2", create_page="2")
    assert has_state(media_page="2", match_page="1", create_page="2")
    assert has_state(media_page="2", match_page="2", create_page="1")


def test_invalid_page_parameters_fall_back_without_writes_or_candidate_changes(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    files = {
        _write_gif(media_root, "Matched.gif"): _gif_bytes(),
        _write_gif(media_root, "Create.cover.gif", extra=4): _gif_bytes(4),
    }
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Matched"))
        db.commit()
        before_items = [(item.id, item.title, item.cover_path) for item in db.query(Item)]
        before_matches = [
            candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        ]
        before_creates = [
            candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        ]

    response = auth_client.get(
        "/media-library",
        params={
            "media_page": "bad",
            "match_page": "bad",
            "create_page": "-9",
            "media_q": "q" * 201,
            "media_status": "invalid",
            "media_sort": "invalid",
        },
    )

    assert response.status_code == 200
    assert 'name="media_q" value=""' in response.text
    assert '<option value="all" selected>' in response.text
    assert '<option value="filename_asc" selected>' in response.text
    with SessionLocal() as db:
        assert [(item.id, item.title, item.cover_path) for item in db.query(Item)] == before_items
        assert [
            candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        ] == before_matches
        assert [
            candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        ] == before_creates
    assert {path: path.read_bytes() for path in files} == files


def test_candidate_post_redirect_preserves_canonical_media_state(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    _write_gif(media_root, "Matched.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Matched"))
        db.commit()
        candidate_id = build_local_media_matches(db).candidates[0].candidate_id

    response = auth_client.post(
        "/media-library/matches/apply",
        data={
            "candidate_id": candidate_id,
            "match_page": "1",
            "create_page": "3",
            "media_page": "4",
            "media_q": "Matched",
            "media_status": "unused",
            "media_sort": "size_desc",
        },
        follow_redirects=False,
    )
    query = parse_qs(urlsplit(response.headers["location"]).query)

    assert response.status_code == 303
    assert query == {
        "match_page": ["1"],
        "create_page": ["3"],
        "media_page": ["4"],
        "media_q": ["Matched"],
        "media_status": ["unused"],
        "media_sort": ["size_desc"],
    }
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.cover_path.is_not(None)).count() == 0
