from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.data_health import build_data_health_report
from app.services.data_health_fixes import build_data_health_fix_options
from app.services.media_cleanup_recovery import query_media_cleanup_recovery
from app.services.media_duplicate_groups import build_media_duplicate_groups
from app.services.media_item_candidates import build_media_item_candidates
from app.services.media_matching import build_local_media_matches


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(media_root: Path, filename: str, *, extra: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_path(path: Path, media_root: Path) -> str:
    return f"/media/{path.relative_to(media_root).as_posix()}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("value", "anchor", "recovered"),
    [
        (".cleanup-anchor-one.gif", True, False),
        ("nested/.cleanup-anchor-two.gif", True, False),
        (".cleanup-anchor-folder/inside.gif", False, False),
        ("prefix.cleanup-anchor-three.gif", False, False),
        (".cleanup-anchor-", False, False),
        (".Cleanup-anchor-four.gif", False, False),
        ("recovered-one.gif", False, True),
        ("nested/recovered-two.gif", False, True),
        ("recovered-folder/inside.gif", False, False),
        ("not-recovered-three.gif", False, False),
        ("RECOVERED-four.gif", False, False),
        ("recovered-", False, False),
    ],
)
def test_cleanup_filename_classification_uses_exact_basename_prefixes(
    value: str,
    anchor: bool,
    recovered: bool,
) -> None:
    assert local_media.is_cleanup_anchor_filename(value) is anchor
    assert local_media.is_recovered_media_filename(value) is recovered


def test_anchors_are_isolated_while_recovered_files_remain_ordinary_media(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    ordinary = _write_gif(media_root, "Movie cover.gif", extra=2)
    recovered = _write_gif(media_root, "recovered-movie-copy.gif", extra=2)
    lookalike = _write_gif(
        media_root,
        "prefix.cleanup-anchor-visible.gif",
        extra=3,
    )
    nested = _write_gif(media_root, ".cleanup-anchor-folder/inside.gif", extra=4)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Movie"))
        db.commit()
        before_matches = {
            candidate.media_path: candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        }
        before_items = {
            candidate.media_path: candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        }

    anchor = _write_gif(media_root, ".cleanup-anchor-dedup-only.gif", extra=12)
    unsupported_anchor = media_root / ".cleanup-anchor-residue.tmp"
    unsupported_anchor.write_bytes(b"internal-residue")
    symlink_anchor = media_root / ".cleanup-anchor-linked.gif"
    symlink_anchor.symlink_to(ordinary)
    anchor_path = _media_path(anchor, media_root)
    unsupported_anchor_path = _media_path(unsupported_anchor, media_root)
    symlink_anchor_path = _media_path(symlink_anchor, media_root)
    ordinary_scan = local_media.scan_local_media()
    recovery_scan = local_media.scan_local_media(include_cleanup_anchors=True)
    ordinary_paths = {entry.media_path for entry in ordinary_scan.entries}
    recovery_entries = {entry.media_path: entry for entry in recovery_scan.entries}

    assert anchor_path not in ordinary_paths
    assert unsupported_anchor_path not in ordinary_paths
    assert symlink_anchor_path not in ordinary_paths
    assert anchor_path in recovery_entries
    assert unsupported_anchor_path in recovery_entries
    assert symlink_anchor_path in recovery_entries
    assert recovery_entries[anchor_path].is_cleanup_anchor is True
    assert recovery_entries[unsupported_anchor_path].is_cleanup_anchor is True
    assert recovery_entries[unsupported_anchor_path].available is False
    assert recovery_entries[symlink_anchor_path].is_cleanup_anchor is True
    assert recovery_entries[symlink_anchor_path].available is False
    assert _media_path(lookalike, media_root) in ordinary_paths
    assert _media_path(nested, media_root) in ordinary_paths
    assert recovery_entries[_media_path(lookalike, media_root)].is_cleanup_anchor is False
    assert recovery_entries[_media_path(recovered, media_root)].is_recovered is True

    with SessionLocal() as db:
        after_matches = {
            candidate.media_path: candidate.candidate_id
            for candidate in build_local_media_matches(db).candidates
        }
        after_items = {
            candidate.media_path: candidate.candidate_id
            for candidate in build_media_item_candidates(db).candidates
        }
    assert after_matches == before_matches
    assert after_items == before_items
    assert anchor_path not in after_matches
    assert anchor_path not in after_items
    assert _media_path(recovered, media_root) in after_items

    duplicate_groups = build_media_duplicate_groups(ordinary_scan)
    matching_group = next(
        group for group in duplicate_groups if group.sha256 == _digest(ordinary)
    )
    assert {entry.media_path for entry in matching_group.entries} == {
        _media_path(ordinary, media_root),
        _media_path(recovered, media_root),
    }
    assert all(
        anchor_path not in {entry.media_path for entry in group.entries}
        for group in duplicate_groups
    )

    library = auth_client.get("/media-library")
    recovered_filter = auth_client.get(
        "/media-library",
        params={"media_status": "recovered"},
    )
    duplicate_page = auth_client.get("/media-library/duplicates")
    assert library.status_code == 200
    assert anchor_path not in library.text
    assert anchor_path not in duplicate_page.text
    filtered_media_paths = re.findall(
        r'data-media-path="([^"]+)"',
        recovered_filter.text,
    )
    assert filtered_media_paths == [_media_path(recovered, media_root)]
    assert "data-media-recovered" in recovered_filter.text

    recovered_upload = auth_client.post(
        "/media-library/upload",
        files={
            "files": (
                "recovered-content.gif",
                recovered.read_bytes(),
                "image/gif",
            )
        },
        follow_redirects=True,
    )
    assert recovered_upload.status_code == 200
    assert "新增 0，重复 1" in recovered_upload.text

    upload = auth_client.post(
        "/media-library/upload",
        files={
            "files": (
                "anchor-content.gif",
                anchor.read_bytes(),
                "image/gif",
            )
        },
        follow_redirects=True,
    )
    uploaded_path = (
        media_root
        / local_media.LOCAL_MEDIA_LIBRARY_DIR
        / f"{_digest(anchor)}.gif"
    )
    assert upload.status_code == 200
    assert "新增 1，重复 0" in upload.text
    assert uploaded_path.exists()
    assert anchor.exists()


def test_recovery_center_is_authenticated_read_only_searchable_and_paginated(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    referenced_anchor = _write_gif(
        media_root,
        "Recovery/.cleanup-anchor-referenced.gif",
        extra=5,
    )
    unreferenced_anchor = _write_gif(
        media_root,
        "Recovery/.cleanup-anchor-unreferenced.gif",
        extra=6,
    )
    damaged_anchor = media_root / "Recovery/.cleanup-anchor-damaged.gif"
    damaged_anchor.parent.mkdir(parents=True, exist_ok=True)
    damaged_anchor.write_bytes(b"not-an-image")
    recovered_files = [
        _write_gif(
            media_root,
            f"Recovery/recovered-{index:02d}.gif",
            extra=20 + index,
        )
        for index in range(21)
    ]
    lookalike = _write_gif(
        media_root,
        "Recovery/not-recovered-visible.gif",
        extra=50,
    )
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    referenced_path = _media_path(referenced_anchor, media_root)
    damaged_path = _media_path(damaged_anchor, media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Recovery Cover", cover_path=referenced_path),
                Creator(
                    name="Damaged Recovery Avatar",
                    type="person",
                    avatar_path=damaged_path,
                ),
            ]
        )
        db.commit()
        before_references = (
            tuple(
                (item.id, item.cover_path)
                for item in db.query(Item).order_by(Item.id)
            ),
            tuple(
                (creator.id, creator.avatar_path)
                for creator in db.query(Creator).order_by(Creator.id)
            ),
        )
    before_files = {
        path: path.read_bytes()
        for path in [
            referenced_anchor,
            unreferenced_anchor,
            damaged_anchor,
            *recovered_files,
            lookalike,
        ]
    }

    with TestClient(auth_client.app) as anonymous_client:
        unauthenticated = anonymous_client.get(
            "/media-library/recovery",
            follow_redirects=False,
        )
    page_one = auth_client.get("/media-library/recovery")
    page_two = auth_client.get(
        "/media-library/recovery",
        params={"recovery_page": "2"},
    )
    recovered_only = auth_client.get(
        "/media-library/recovery",
        params={"recovery_status": "recovered"},
    )
    path_search = auth_client.get(
        "/media-library/recovery",
        params={"recovery_q": ".CLEANUP-ANCHOR-REFERENCED.GIF"},
    )
    digest_search = auth_client.get(
        "/media-library/recovery",
        params={"recovery_q": _digest(recovered_files[-1])[:20]},
    )
    sorted_page = auth_client.get(
        "/media-library/recovery",
        params={"recovery_sort": "size_desc"},
    )
    invalid_filters = auth_client.get(
        "/media-library/recovery",
        params={
            "recovery_q": "x" * 201,
            "recovery_status": "unknown",
            "recovery_sort": "unknown",
            "recovery_page": "not-a-page",
        },
    )

    assert unauthenticated.status_code == 303
    assert page_one.status_code == 200
    assert 'data-recovery-anchor-count>3</strong>' in page_one.text
    assert 'data-recovery-referenced-count>1</strong>' in page_one.text
    assert 'data-recovery-unreferenced-count>1</strong>' in page_one.text
    assert 'data-recovery-damaged-count>1</strong>' in page_one.text
    assert 'data-recovery-file-count>21</strong>' in page_one.text
    assert 'data-recovery-result-count>24</strong>' in page_one.text
    assert page_one.text.count("data-recovery-path=") == 20
    assert page_two.text.count("data-recovery-path=") == 4
    assert 'data-recovery-status="anchor_referenced"' in page_one.text
    assert 'data-recovery-status="anchor_unreferenced"' in page_one.text
    assert 'data-recovery-status="anchor_damaged"' in page_one.text
    assert _digest(referenced_anchor) in page_one.text
    assert "Recovery Cover" in page_one.text
    assert "Damaged Recovery Avatar" in page_one.text
    assert f"{len(b'not-an-image')} B" in page_one.text
    assert _media_path(lookalike, media_root) not in page_one.text
    assert recovered_only.text.count("data-recovery-path=") == 20
    assert 'data-recovery-result-count>21</strong>' in recovered_only.text
    assert 'data-recovery-kind="anchor"' not in recovered_only.text
    assert referenced_path in path_search.text
    assert path_search.text.count("data-recovery-path=") == 1
    assert _media_path(recovered_files[-1], media_root) in digest_search.text
    assert digest_search.text.count("data-recovery-path=") == 1
    sorted_paths = re.findall(r'data-recovery-path="([^"]+)"', sorted_page.text)
    assert sorted_paths[0] == _media_path(recovered_files[-1], media_root)
    assert invalid_filters.status_code == 200
    assert 'value="all" selected' in invalid_filters.text
    assert 'value="path_asc" selected' in invalid_filters.text
    assert 'data-recovery-result-count>24</strong>' in invalid_filters.text
    post_actions = re.findall(
        r'<form[^>]+action="([^"]+)"[^>]+method="post"',
        page_one.text.casefold(),
    )
    assert post_actions == ["/logout"]
    assert auth_client.post("/media-library/recovery").status_code == 405

    with SessionLocal() as db:
        after_references = (
            tuple(
                (item.id, item.cover_path)
                for item in db.query(Item).order_by(Item.id)
            ),
            tuple(
                (creator.id, creator.avatar_path)
                for creator in db.query(Creator).order_by(Creator.id)
            ),
        )
    assert after_references == before_references
    assert {path: path.read_bytes() for path in before_files} == before_files

    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library/recovery"},
    )
    english = auth_client.get("/media-library/recovery")
    assert "Media Cleanup Recovery Center" in english.text
    assert "Read-only Recovery Status View" in english.text
    assert "Referenced Safety Anchor" in english.text


def test_recovery_query_sort_is_stable_and_data_health_audits_anchor_states(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    referenced = _write_gif(
        media_root,
        "Health/.cleanup-anchor-referenced.gif",
        extra=7,
    )
    unreferenced = _write_gif(
        media_root,
        "Health/.cleanup-anchor-unreferenced.gif",
        extra=8,
    )
    damaged = media_root / "Health/.cleanup-anchor-damaged.gif"
    damaged.parent.mkdir(parents=True, exist_ok=True)
    damaged.write_bytes(b"broken")
    recovered = _write_gif(media_root, "Health/recovered-normal.gif", extra=9)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    referenced_path = _media_path(referenced, media_root)
    damaged_path = _media_path(damaged, media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Health Anchor", cover_path=referenced_path),
                Creator(
                    name="Broken Anchor",
                    type="person",
                    avatar_path=damaged_path,
                ),
            ]
        )
        db.commit()
        scan = local_media.scan_local_media(include_cleanup_anchors=True)
        first = query_media_cleanup_recovery(
            db,
            scan,
            q=None,
            status=None,
            sort="status_desc",
            page=1,
        )
        second = query_media_cleanup_recovery(
            db,
            scan,
            q=None,
            status=None,
            sort="status_desc",
            page=1,
        )
        report = build_data_health_report(db)

    assert [row.entry.media_path for row in first.rows] == [
        row.entry.media_path for row in second.rows
    ]
    assert report.issue_code_counts["media_cleanup_anchor_referenced"] == 1
    assert report.issue_code_counts["media_cleanup_anchor_unreferenced"] == 1
    assert report.issue_code_counts["media_cleanup_anchor_damaged"] == 1
    assert report.issue_code_counts["media_reference_damaged"] == 1
    assert build_data_health_fix_options(report) == []
    anchor_issues = [
        issue
        for issue in report.issues
        if issue.object_type == "media_cleanup_anchor"
    ]
    assert {issue.object_id for issue in anchor_issues} == {
        referenced_path,
        _media_path(unreferenced, media_root),
        damaged_path,
    }
    assert _media_path(recovered, media_root) not in {
        issue.object_id for issue in anchor_issues
    }
    assert all("references=" in issue.detail for issue in anchor_issues)

    page = auth_client.get("/data-health")
    assert page.status_code == 200
    assert "发现仍被封面或头像引用的安全锚点" in page.text
    assert "发现未引用的安全锚点残留" in page.text
    assert "发现损坏或非法的安全锚点" in page.text
    assert 'href="/media-library/recovery"' in page.text
