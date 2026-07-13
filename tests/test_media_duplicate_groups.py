from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_duplicate_groups import (
    MEDIA_DUPLICATE_GROUP_PAGE_SIZE,
    build_media_duplicate_groups,
    query_media_duplicate_groups,
)
from app.services.media_item_candidates import build_media_item_candidates
from app.services.media_library_query import query_media_library
from app.services.media_matching import build_local_media_matches


def _entry(
    filename: str,
    *,
    size: int,
    sha256: str,
    available: bool = True,
) -> LocalMediaEntry:
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


def _group_entries(
    name: str,
    digest: str,
    *,
    size: int,
    count: int,
) -> list[LocalMediaEntry]:
    return [
        _entry(f"{name}/Member {index}.png", size=size, sha256=digest)
        for index in range(count)
    ]


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(media_root: Path, filename: str, *, extra: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def test_shared_builder_preserves_b1_duplicate_boundary_and_group_metrics() -> None:
    digest = "a" * 64
    same_path_digest = "d" * 64
    scan = _scan(
        _entry("Copies/Zulu.png", size=12, sha256=digest),
        _entry("Copies/alpha.png", size=12, sha256=digest.upper()),
        _entry("single.png", size=8, sha256="b" * 64),
        _entry("empty.png", size=8, sha256=""),
        _entry("short.png", size=8, sha256="c" * 63),
        _entry("damaged.png", size=0, sha256=digest, available=False),
        _entry("same.png", size=5, sha256=same_path_digest),
        _entry("same.png", size=5, sha256=same_path_digest),
    )

    groups = build_media_duplicate_groups(scan)
    b1 = query_media_library(
        scan,
        set(),
        q=None,
        status="duplicate",
        sort="filename_asc",
        page=1,
    )

    assert len(groups) == 1
    assert groups[0].sha256 == digest
    assert [entry.media_path for entry in groups[0].entries] == [
        "/media/Copies/alpha.png",
        "/media/Copies/Zulu.png",
    ]
    assert groups[0].member_count == 2
    assert groups[0].file_size == 12
    assert groups[0].total_bytes == 24
    assert groups[0].reclaimable_bytes == 12
    assert [row.entry.media_path for row in b1.rows] == [
        entry.media_path for entry in groups[0].entries
    ]
    assert b1.duplicate_summary.group_count == 1
    assert b1.duplicate_summary.file_count == 2
    assert b1.duplicate_summary.reclaimable_bytes == 12


def test_group_query_searches_and_stably_supports_all_sort_options() -> None:
    scan = _scan(
        *_group_entries("Alpha", "a" * 64, size=10, count=2),
        *_group_entries("Folder/Beta", "b" * 64, size=5, count=3),
        *_group_entries("Gamma", "c" * 64, size=20, count=3),
    )

    def hashes(sort: str) -> list[str]:
        result = query_media_duplicate_groups(
            scan,
            q=None,
            sort=sort,
            page=1,
        )
        return [group.sha256 for group in result.groups]

    filename = query_media_duplicate_groups(
        scan,
        q=" beta/member 1 ",
        sort=None,
        page=1,
    )
    path = query_media_duplicate_groups(
        scan,
        q="/MEDIA/FOLDER/BETA",
        sort=None,
        page=1,
    )
    sha = query_media_duplicate_groups(
        scan,
        q="C" * 18,
        sort=None,
        page=1,
    )
    fallback = query_media_duplicate_groups(
        scan,
        q="x" * 201,
        sort="invalid",
        page="invalid",
    )

    assert [group.sha256 for group in filename.groups] == ["b" * 64]
    assert [group.sha256 for group in path.groups] == ["b" * 64]
    assert [group.sha256 for group in sha.groups] == ["c" * 64]
    assert hashes("members_asc") == ["a" * 64, "b" * 64, "c" * 64]
    assert hashes("members_desc") == ["b" * 64, "c" * 64, "a" * 64]
    assert hashes("reclaimable_asc") == ["a" * 64, "b" * 64, "c" * 64]
    assert hashes("reclaimable_desc") == ["c" * 64, "a" * 64, "b" * 64]
    assert hashes("sha256_asc") == ["a" * 64, "b" * 64, "c" * 64]
    assert hashes("sha256_desc") == ["c" * 64, "b" * 64, "a" * 64]
    assert fallback.filters.q == ""
    assert fallback.filters.sort == "members_desc"
    assert fallback.page_info.page == 1
    assert [group.sha256 for group in fallback.groups] == [
        "b" * 64,
        "c" * 64,
        "a" * 64,
    ]


def test_group_query_paginates_twenty_groups_and_clamps_large_pages() -> None:
    entries = [
        entry
        for index in range(25)
        for entry in _group_entries(
            f"Group {index:02d}",
            f"{index:064x}",
            size=index + 1,
            count=2,
        )
    ]
    scan = _scan(*entries)

    second = query_media_duplicate_groups(
        scan,
        q=None,
        sort="sha256_asc",
        page=2,
    )
    clamped = query_media_duplicate_groups(
        scan,
        q=None,
        sort="sha256_asc",
        page=999,
    )

    assert MEDIA_DUPLICATE_GROUP_PAGE_SIZE == 20
    assert second.total_groups == 25
    assert second.page_info.total == 25
    assert second.page_info.page == 2
    assert [group.sha256 for group in second.groups] == [
        f"{index:064x}" for index in range(20, 25)
    ]
    assert clamped.page_info.page == 2
    assert len(clamped.groups) == 5


def test_duplicate_group_page_requires_login_and_rejects_post(
    client: TestClient,
) -> None:
    get_response = client.get(
        "/media-library/duplicates",
        follow_redirects=False,
    )
    post_response = client.post(
        "/media-library/duplicates",
        follow_redirects=False,
    )

    assert get_response.status_code == 303
    assert post_response.status_code == 405


def test_duplicate_group_page_shows_references_exact_link_and_is_read_only(
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
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    with SessionLocal() as db:
        db.add(Item(title="Referenced Item", cover_path="/media/Copies/First.gif"))
        db.add(Creator(name="Referenced Creator", avatar_path="/media/Copies/Second.gif"))
        db.commit()
        before_items = [
            (item.id, item.title, item.cover_path)
            for item in db.query(Item).order_by(Item.id)
        ]
        before_creators = [
            (creator.id, creator.name, creator.avatar_path)
            for creator in db.query(Creator).order_by(Creator.id)
        ]
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

    response = auth_client.get(
        "/media-library/duplicates",
        params={
            "duplicate_q": digest[:20].upper(),
            "duplicate_sort": "reclaimable_desc",
        },
    )
    link_match = re.search(r'data-exact-media-filter href="([^"]+)"', response.text)
    main_content = re.search(r"<main>(.*)</main>", response.text, re.DOTALL)

    assert response.status_code == 200
    assert f'data-duplicate-sha="{digest}"' in response.text
    assert f"<code>{digest}</code>" in response.text
    assert 'data-group-member-count>2</strong>' in response.text
    assert f'data-group-file-size>{len(first.read_bytes())} B</strong>' in response.text
    assert f'data-group-total-bytes>{len(first.read_bytes()) * 2} B</strong>' in response.text
    assert f'data-group-reclaimable-bytes>{len(first.read_bytes())} B</strong>' in response.text
    assert 'data-media-path="/media/Copies/First.gif"' in response.text
    assert 'data-media-path="/media/Copies/Second.gif"' in response.text
    assert "条目封面：Referenced Item" in response.text
    assert "创作者头像：Referenced Creator" in response.text
    assert "不会自动建议保留哪一份" in response.text
    assert main_content is not None
    assert 'method="post"' not in main_content.group(1)
    assert link_match is not None
    exact_url = urlsplit(html.unescape(link_match.group(1)))
    assert exact_url.path == "/media-library"
    assert exact_url.fragment == "media-files"
    assert parse_qs(exact_url.query) == {
        "media_q": [digest],
        "media_status": ["duplicate"],
    }
    with SessionLocal() as db:
        assert [
            (item.id, item.title, item.cover_path)
            for item in db.query(Item).order_by(Item.id)
        ] == before_items
        assert [
            (creator.id, creator.name, creator.avatar_path)
            for creator in db.query(Creator).order_by(Creator.id)
        ] == before_creators
        assert [
            candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        ] == before_matches
        assert [
            candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        ] == before_creates
    assert {path: path.read_bytes() for path in before_files} == before_files

    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library/duplicates"},
    )
    english = auth_client.get("/media-library/duplicates")
    assert "Duplicate Media Groups" in english.text
    assert "Most Reclaimable Space First" in english.text
    assert "never recommends which copy to keep" in english.text


def test_duplicate_group_page_preserves_query_sort_and_twenty_group_pagination(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    for index in range(21):
        _write_gif(media_root, f"Group {index:02d}/First.gif", extra=index)
        _write_gif(media_root, f"Group {index:02d}/Second.gif", extra=index)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    page = auth_client.get(
        "/media-library/duplicates",
        params={
            "duplicate_page": "2",
            "duplicate_q": "Group",
            "duplicate_sort": "sha256_asc",
        },
    )
    invalid = auth_client.get(
        "/media-library/duplicates",
        params={
            "duplicate_page": "invalid",
            "duplicate_q": "q" * 201,
            "duplicate_sort": "invalid",
        },
    )
    hrefs = re.findall(r'href="([^"]+)"', html.unescape(page.text))
    queries = [
        parse_qs(urlsplit(href).query)
        for href in hrefs
        if urlsplit(href).path == "/media-library/duplicates"
    ]

    assert page.status_code == 200
    assert page.text.count('data-duplicate-sha="') == 1
    assert 'data-duplicate-total-groups>21</strong>' in page.text
    assert 'data-duplicate-filtered-groups>21</strong>' in page.text
    assert any(
        query == {
            "duplicate_q": ["Group"],
            "duplicate_sort": ["sha256_asc"],
            "duplicate_page": ["1"],
        }
        for query in queries
    )
    assert invalid.status_code == 200
    assert invalid.text.count('data-duplicate-sha="') == 20
    assert re.search(r'name="duplicate_q"\s+value=""', invalid.text)
    assert '<option value="members_desc" selected>' in invalid.text
