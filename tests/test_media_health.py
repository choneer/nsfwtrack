from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_health
from app.services.data_health import DATA_HEALTH_DETAIL_LIMIT, build_data_health_report
from app.services.data_health_fixes import build_data_health_fix_options
from app.services.media_health import audit_local_media


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(media_root: Path, filename: str, *, extra: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_findings(report) -> list:
    return [issue for issue in report.issues if issue.category == "media"]


def _database_snapshot() -> tuple[list[tuple], list[tuple]]:
    with SessionLocal() as db:
        items = [
            (item.id, item.title, item.cover_path)
            for item in db.query(Item).order_by(Item.id)
        ]
        creators = [
            (creator.id, creator.name, creator.avatar_path)
            for creator in db.query(Creator).order_by(Creator.id)
        ]
    return items, creators


def test_healthy_unique_unused_media_is_not_an_issue(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    unused = _write_gif(media_root, "unused.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    with SessionLocal() as db:
        report = build_data_health_report(db)
    response = auth_client.get("/data-health")

    assert report.status == "healthy"
    assert report.issue_code_counts == {}
    assert next(
        summary for summary in report.category_summaries if summary.category == "media"
    ).count == 0
    assert response.status_code == 200
    assert "媒体完整性" in response.text
    assert "暂无数据问题" in response.text
    assert "媒体完整性检查仅报告" in response.text
    assert unused.read_bytes() == _gif_bytes()


def test_media_audit_reports_invalid_escape_symlink_missing_and_damaged_references(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    healthy = _write_gif(media_root, "healthy.gif")
    broken = media_root / "broken.gif"
    broken.write_bytes(b"broken")
    outside = _write_gif(tmp_path / "outside", "outside.gif")
    (media_root / "linked.gif").symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Invalid", cover_path="https://example.invalid/cover.gif"),
                Item(title="Escape", cover_path="/media/../outside.gif"),
                Item(title="Symlink", cover_path="/media/linked.gif"),
                Item(title="Damaged", cover_path="/media/broken.gif"),
                Item(title="Healthy", cover_path="/media/healthy.gif"),
                Creator(
                    name="Missing Avatar",
                    type="person",
                    avatar_path="/media/missing.gif",
                ),
            ]
        )
        db.commit()
        report = build_data_health_report(db)

    codes = {finding.code for finding in _media_findings(report)}
    response = auth_client.get("/data-health")

    assert {
        "media_reference_invalid_path",
        "media_reference_path_escape",
        "media_reference_symlink",
        "media_reference_missing",
        "media_reference_damaged",
        "media_damaged_file",
        "media_scan_skipped_symlinks",
    }.issubset(codes)
    assert not any(
        finding.detail == "/media/healthy.gif" for finding in _media_findings(report)
    )
    damaged_file = next(
        finding
        for finding in _media_findings(report)
        if finding.code == "media_damaged_file"
    )
    assert damaged_file.object_id == "/media/broken.gif"
    assert "sha256=" in damaged_file.detail
    assert "references=1" in damaged_file.detail
    assert report.problem_count == 6
    assert report.total_issues == 7
    assert response.status_code == 200
    assert "媒体引用路径非法" in response.text
    assert "媒体引用尝试越出根目录" in response.text
    assert "媒体引用经过符号链接" in response.text
    assert "媒体引用文件缺失" in response.text
    assert "媒体引用文件损坏或不可安全读取" in response.text
    assert "条目封面引用" in response.text
    assert "创作者头像引用" in response.text
    assert healthy.read_bytes() == _gif_bytes()
    assert broken.read_bytes() == b"broken"


@pytest.mark.parametrize(
    ("root_kind", "reference_code", "detail"),
    [
        ("missing", "media_reference_missing", "missing"),
        ("file", "media_reference_damaged", "not_directory"),
        ("symlink", "media_reference_symlink", "symlink"),
    ],
)
def test_media_root_unavailable_is_reported_without_500(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    root_kind: str,
    reference_code: str,
    detail: str,
) -> None:
    media_root = tmp_path / "media"
    if root_kind == "file":
        media_root.write_bytes(b"not-a-directory")
    elif root_kind == "symlink":
        target = tmp_path / "target"
        target.mkdir()
        media_root.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Root Failure", cover_path="/media/cover.gif"))
        db.commit()
        report = build_data_health_report(db)

    response = auth_client.get("/data-health")
    findings = _media_findings(report)

    assert any(
        finding.code == "media_root_unavailable" and finding.detail == detail
        for finding in findings
    )
    assert any(finding.code == reference_code for finding in findings)
    assert response.status_code == 200
    assert "媒体根目录不可用" in response.text


def test_media_root_readability_check_rejects_path_replaced_by_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    moved_root = tmp_path / "moved-media"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "private.txt"
    sentinel.write_text("outside", encoding="utf-8")
    original_open = media_health.os.open
    raced = False

    def replace_root_before_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal raced
        if Path(path) == media_root and dir_fd is None and not raced:
            media_root.rename(moved_root)
            media_root.symlink_to(outside, target_is_directory=True)
            raced = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(media_health.os, "open", replace_root_before_open)
    state = media_health._root_state(media_root, has_references=True)

    assert raced is True
    assert state == "unreadable"
    assert media_root.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "outside"


def test_unscanned_reference_parent_symlink_race_never_inspects_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    parent = media_root / "nested"
    parent.mkdir(parents=True)
    moved_parent = media_root / "moved-nested"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "external.gif"
    outside_file.write_bytes(_gif_bytes(17))
    original_stat = media_health.os.stat
    raced = False
    external_inspected = False

    def replace_parent_after_lstat(
        path: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> object:
        nonlocal raced, external_inspected
        if path == "external.gif":
            external_inspected = True
            raise AssertionError("external symlink target must not be inspected")
        result = original_stat(
            path,
            dir_fd=dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if path == "nested" and dir_fd is not None and not raced:
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
            raced = True
        return result

    monkeypatch.setattr(media_health.os, "stat", replace_parent_after_lstat)
    code = media_health._classify_unscanned_reference(
        media_root,
        "/media/nested/external.gif",
    )

    assert raced is True
    assert external_inspected is False
    assert code == "media_reference_damaged"
    assert parent.is_symlink()
    assert outside_file.read_bytes() == _gif_bytes(17)


def test_upload_residue_duplicate_content_and_scan_skips_are_warning_only(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    first = _write_gif(media_root, "first.gif")
    second = _write_gif(media_root, "nested/second.gif")
    unique = _write_gif(media_root, "unique.gif", extra=5)
    residue = media_root / "library" / ".upload-stale.tmp"
    residue.parent.mkdir()
    residue.write_bytes(b"partial")
    unsupported = media_root / "notes.txt"
    unsupported.write_text("local note", encoding="utf-8")
    target = tmp_path / "outside.gif"
    target.write_bytes(_gif_bytes(9))
    (media_root / "skipped.gif").symlink_to(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_files = {
        first: first.read_bytes(),
        second: second.read_bytes(),
        unique: unique.read_bytes(),
        residue: residue.read_bytes(),
        unsupported: unsupported.read_bytes(),
    }

    with SessionLocal() as db:
        report = build_data_health_report(db)
    before_db = _database_snapshot()
    response = auth_client.get("/data-health")
    after_db = _database_snapshot()
    findings = _media_findings(report)
    by_code = {finding.code: finding for finding in findings}

    assert report.status == "warning"
    assert report.problem_count == 0
    assert {
        "media_upload_residue",
        "media_duplicate_content",
        "media_scan_skipped_symlinks",
        "media_scan_skipped_unsupported",
    }.issubset(by_code)
    assert all(finding.severity == "warning" for finding in findings)
    assert "count=2" in by_code["media_duplicate_content"].detail
    assert "/media/first.gif" in by_code["media_duplicate_content"].detail
    assert "/media/nested/second.gif" in by_code["media_duplicate_content"].detail
    assert by_code["media_scan_skipped_symlinks"].detail == "count=1"
    assert by_code["media_scan_skipped_unsupported"].detail == "count=2"
    assert build_data_health_fix_options(report) == []
    assert response.status_code == 200
    assert 'action="/data-health/fix"' not in response.text
    assert "发现上传临时残留" in response.text
    assert "不同路径存在相同 SHA-256 内容" in response.text
    assert (
        'href="/media-library/duplicates?duplicate_q='
        f'{by_code["media_duplicate_content"].object_id}"'
    ) in response.text
    assert "媒体扫描跳过了符号链接" in response.text
    assert "媒体扫描跳过了不支持文件" in response.text
    assert after_db == before_db
    assert {path: path.read_bytes() for path in before_files} == before_files
    assert (media_root / "skipped.gif").is_symlink()

    duplicate_page = auth_client.get(
        "/media-library/duplicates",
        params={"duplicate_q": by_code["media_duplicate_content"].object_id},
    )
    assert duplicate_page.status_code == 200
    assert 'data-duplicate-total-groups>1<' in duplicate_page.text
    assert by_code["media_duplicate_content"].object_id in duplicate_page.text


def test_upload_residue_findings_reuse_verified_scan_without_path_rewalk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    scan = local_media.LocalMediaScan(
        (),
        1,
        3,
        0,
        (
            local_media.LocalMediaScanSkip(
                path="nested/.upload-safe.tmp",
                reason="unsupported_extension",
                extension=".tmp",
                size=7,
                device=1,
                inode=2,
                modified_ns=3,
                changed_ns=4,
            ),
            local_media.LocalMediaScanSkip(
                path="linked/.upload-outside.tmp",
                reason="symlink",
                extension=".tmp",
                size=9,
                device=5,
                inode=6,
                modified_ns=7,
                changed_ns=8,
            ),
            local_media.LocalMediaScanSkip(
                path="notes.txt",
                reason="unsupported_extension",
                extension=".txt",
                size=11,
                device=9,
                inode=10,
                modified_ns=11,
                changed_ns=12,
            ),
        ),
    )
    monkeypatch.setattr(local_media, "scan_local_media", lambda **kwargs: scan)
    original_scandir = media_health.os.scandir
    path_scans = 0

    def reject_independent_path_rewalk(path: object) -> object:
        nonlocal path_scans
        if not isinstance(path, int):
            path_scans += 1
            raise AssertionError("Data Health must use verified directory FDs")
        return original_scandir(path)

    monkeypatch.setattr(media_health.os, "scandir", reject_independent_path_rewalk)
    with SessionLocal() as db:
        findings = audit_local_media(db)

    residues = [
        finding
        for finding in findings
        if finding.code == "media_upload_residue"
    ]
    assert path_scans == 0
    assert [(finding.object_id, finding.detail) for finding in residues] == [
        ("nested/.upload-safe.tmp", "size=7")
    ]


def test_media_findings_share_the_existing_global_two_hundred_detail_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", tmp_path / "missing-media")
    with SessionLocal() as db:
        db.add_all(
            Item(
                title=f"Invalid Media {index:03d}",
                cover_path=f"https://example.invalid/{index}.gif",
            )
            for index in range(DATA_HEALTH_DETAIL_LIMIT + 5)
        )
        db.commit()
        report = build_data_health_report(db)

    media_summary = next(
        summary for summary in report.category_summaries if summary.category == "media"
    )
    assert report.total_issues == DATA_HEALTH_DETAIL_LIMIT + 5
    assert report.displayed_issue_count == DATA_HEALTH_DETAIL_LIMIT
    assert len(report.issues) == DATA_HEALTH_DETAIL_LIMIT
    assert report.details_truncated is True
    assert media_summary.count == DATA_HEALTH_DETAIL_LIMIT + 5
    assert report.issue_code_counts["media_reference_invalid_path"] == (
        DATA_HEALTH_DETAIL_LIMIT + 5
    )


def test_media_health_page_renders_english_readonly_get_and_bounded_repair_copy(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.write_bytes(b"not-a-directory")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/data-health"},
    )

    assert response.status_code == 200
    assert "Media Integrity" in response.text
    assert "Media root is unavailable" in response.text
    assert "Root path is not a directory" in response.text
    assert "Media integrity findings are report-only" in response.text
    assert "separate individual preview and confirmed POST" in response.text
    assert "media files are never changed" in response.text


def test_media_findings_cannot_be_submitted_as_a_health_fix(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cover = _write_gif(media_root, "cover.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="Protected Media", cover_path="/media/cover.gif")
        db.add(item)
        db.commit()
        item_id = item.id

    response = auth_client.post(
        "/data-health/fix",
        data={"fix_type": "media_reference_missing", "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "修复类型无效" in response.text
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        assert item is not None
        assert item.cover_path == "/media/cover.gif"
    assert cover.read_bytes() == _gif_bytes()
