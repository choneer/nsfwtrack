from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_reference_repair
from app.services.data_health import build_data_health_report
from app.services.media_reference_repair import (
    MediaReferenceRepairError,
    build_media_reference_repair_preview,
    execute_media_reference_repair,
)
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, name: str, *, extra: int = 0) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_path(path: Path, root: Path) -> str:
    return f"/media/{path.relative_to(root).as_posix()}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_snapshot(root: Path) -> dict[str, bytes | str]:
    snapshot: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = f"symlink:{path.readlink()}"
        elif path.is_file():
            snapshot[relative] = path.read_bytes()
    return snapshot


def _database_snapshot() -> tuple[tuple[object, ...], ...]:
    with SessionLocal() as db:
        items = db.execute(
            select(
                Item.id,
                Item.title,
                Item.cover_path,
                Item.summary,
                Item.release_date,
                Item.extra,
                Item.created_at,
                Item.updated_at,
            ).order_by(Item.id)
        ).all()
        creators = db.execute(
            select(
                Creator.id,
                Creator.name,
                Creator.type,
                Creator.avatar_path,
                Creator.created_at,
            ).order_by(Creator.id)
        ).all()
    return tuple(tuple(row) for row in (*items, *creators))


def _target_form(preview: object, *, mode: str) -> dict[str, str]:
    target = preview.target
    return {
        "object_type": target.object_type,
        "object_id": str(target.object_id),
        "expected_object_token": target.object_token,
        "expected_original_path": target.original_path,
        "expected_issue_code": target.issue_code,
        "mode": mode,
    }


def _replacement_form(replacement: object) -> dict[str, str]:
    media = replacement.media
    return {
        "replacement_path": media.media_path,
        "replacement_sha256": media.sha256,
        "expected_size": str(media.size),
        "expected_device": str(media.device),
        "expected_inode": str(media.inode),
        "expected_modified_ns": str(media.modified_ns),
        "expected_changed_ns": str(media.changed_ns),
    }


def test_data_health_offers_authenticated_zero_write_previews_for_all_reference_issues(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    damaged = root / "damaged.gif"
    damaged.write_bytes(b"not-an-image")
    damaged_anchor = root / ".cleanup-anchor-damaged.gif"
    damaged_anchor.write_bytes(b"damaged-anchor")
    outside = _write_gif(tmp_path, "outside.gif", extra=1)
    (root / "linked.gif").symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Missing", cover_path="/media/missing.gif"),
                Item(title="Damaged", cover_path="/media/damaged.gif"),
                Item(title="Symlink", cover_path="/media/linked.gif"),
                Item(title="Invalid", cover_path="https://invalid.example/a.gif"),
                Item(title="Escape", cover_path="/media/../outside.gif"),
                Creator(
                    name="Damaged Anchor",
                    type="person",
                    avatar_path="/media/.cleanup-anchor-damaged.gif",
                ),
            ]
        )
        db.commit()
    before_db = _database_snapshot()
    before_files = _file_snapshot(root)

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/data-health/media-reference/repair",
            params={"object_type": "item_cover", "object_id": "1"},
            follow_redirects=False,
        )
    health = auth_client.get("/data-health")

    assert denied.status_code == 303
    assert health.status_code == 200
    assert health.text.count("预览修复引用") == 6
    for object_type, object_id, issue_text, original_path in (
        ("item_cover", 1, "媒体引用文件缺失", "/media/missing.gif"),
        ("item_cover", 2, "媒体引用文件损坏", "/media/damaged.gif"),
        ("item_cover", 3, "媒体引用经过符号链接", "/media/linked.gif"),
        ("item_cover", 4, "媒体引用路径非法", "https://invalid.example/a.gif"),
        ("item_cover", 5, "媒体引用尝试越出根目录", "/media/../outside.gif"),
        (
            "creator_avatar",
            1,
            "媒体引用文件损坏",
            "/media/.cleanup-anchor-damaged.gif",
        ),
    ):
        response = auth_client.get(
            "/data-health/media-reference/repair",
            params={"object_type": object_type, "object_id": object_id},
        )
        assert response.status_code == 200
        assert "data-media-reference-repair-preview" in response.text
        assert original_path in response.text
        assert issue_text in response.text
        assert "不会修改、删除、移动或重命名任何媒体文件" in response.text
        assert 'action="/data-health/media-reference/repair"' in response.text

    assert auth_client.get("/data-health/media-reference/repair").status_code == 400
    assert auth_client.get("/data-health/media-reference/repair", params={"object_type": "item_cover", "object_id": 999}).status_code == 400
    assert auth_client.get("/data-health/media-reference/repair", params={"object_type": "item", "object_id": 1}).status_code == 400
    assert auth_client.get("/data-health/media-reference/repair", params={"object_type": "item_cover", "object_id": 1}, follow_redirects=False).status_code == 200
    assert _database_snapshot() == before_db
    assert _file_snapshot(root) == before_files


def test_replacement_search_is_stable_paginated_and_excludes_unsafe_media(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    for index in range(22):
        _write_gif(root, f"library/image-{index:02d}.gif", extra=index + 1)
    recovered = _write_gif(root, "library/recovered-choice.gif", extra=40)
    anchor = _write_gif(root, "library/.cleanup-anchor-hidden.gif", extra=41)
    damaged = root / "library/damaged.gif"
    damaged.write_bytes(b"damaged")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="Broken", cover_path="/media/missing.gif"))
        db.commit()

    first = auth_client.get(
        "/data-health/media-reference/repair",
        params={"object_type": "item_cover", "object_id": 1},
    )
    second = auth_client.get(
        "/data-health/media-reference/repair",
        params={"object_type": "item_cover", "object_id": 1, "page": 2},
    )
    recovered_search = auth_client.get(
        "/data-health/media-reference/repair",
        params={
            "object_type": "item_cover",
            "object_id": 1,
            "q": _digest(recovered)[10:28],
        },
    )

    assert first.status_code == second.status_code == recovered_search.status_code == 200
    assert first.text.count("data-replacement-path=") == 20
    assert second.text.count("data-replacement-path=") == 3
    assert first.text.index("/media/library/image-00.gif") < first.text.index(
        "/media/library/image-19.gif"
    )
    assert "/media/library/image-20.gif" in second.text
    assert _media_path(recovered, root) in second.text
    assert _media_path(recovered, root) in recovered_search.text
    assert "恢复媒体" in recovered_search.text
    assert _media_path(anchor, root) not in first.text + second.text
    assert _media_path(damaged, root) not in first.text + second.text
    assert "显示 1-20 / 23" in first.text


def test_standard_replace_and_clear_update_only_one_reference_and_keep_all_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    replacement_path = _write_gif(root, "library/replacement.gif", extra=5)
    recovered_path = _write_gif(root, "library/recovered-avatar.gif", extra=6)
    replacement_media_path = _media_path(replacement_path, root)
    recovered_media_path = _media_path(recovered_path, root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(
                    title="Broken Item",
                    cover_path="/media/missing-cover.gif",
                    summary="unchanged",
                    extra='{"keep":true}',
                ),
                Item(title="Untouched", cover_path="/media/other-missing.gif"),
                Creator(
                    name="Broken Creator",
                    type="studio",
                    avatar_path="/media/missing-avatar.gif",
                ),
            ]
        )
        db.commit()
        item_preview = build_media_reference_repair_preview(
            db,
            object_type="item_cover",
            object_id=1,
            q="replacement",
            page=1,
        )
        creator_preview = build_media_reference_repair_preview(
            db,
            object_type="creator_avatar",
            object_id=1,
            q="recovered-avatar",
            page=1,
        )
    before_files = _file_snapshot(root)

    missing_confirmation = auth_client.post(
        "/data-health/media-reference/repair",
        data={
            **_target_form(item_preview, mode="replace"),
            **_replacement_form(item_preview.replacements[0]),
        },
        follow_redirects=True,
    )
    assert "危险操作已拒绝" in missing_confirmation.text

    replaced = auth_client.post(
        "/data-health/media-reference/repair",
        data={
            **_target_form(item_preview, mode="replace"),
            **_replacement_form(item_preview.replacements[0]),
            "confirm": "1",
        },
        follow_redirects=True,
    )
    cleared = auth_client.post(
        "/data-health/media-reference/repair",
        data={**_target_form(creator_preview, mode="clear"), "confirm": "1"},
        follow_redirects=True,
    )

    assert "引用从 /media/missing-cover.gif 替换为" in replaced.text
    assert replacement_media_path in replaced.text
    assert "明确清除原引用 /media/missing-avatar.gif" in cleared.text
    with SessionLocal() as db:
        item = db.get(Item, 1)
        untouched = db.get(Item, 2)
        creator = db.get(Creator, 1)
        assert item is not None and item.cover_path == replacement_media_path
        assert item.summary == "unchanged"
        assert item.extra == '{"keep":true}'
        assert untouched is not None and untouched.cover_path == "/media/other-missing.gif"
        assert creator is not None and creator.avatar_path is None
        assert creator.type == "studio"
        report = build_data_health_report(db)
    issue_targets = {(issue.object_type, issue.object_id) for issue in report.issues}
    assert ("item_cover", "1") not in issue_targets
    assert ("creator_avatar", "1") not in issue_targets
    assert ("item_cover", "2") in issue_targets
    assert recovered_media_path in {
        entry.media_path for entry in local_media.scan_local_media().entries
    }
    assert _file_snapshot(root) == before_files


def test_strict_confirmation_requires_exact_confirm_for_replace_and_clear(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    replacement = _write_gif(root, "recovered-strict.gif", extra=7)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="Strict", cover_path="/media/missing.gif"))
        db.commit()
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        preview = build_media_reference_repair_preview(
            db,
            object_type="item_cover",
            object_id=1,
            q=None,
            page=None,
        )
    assert preview.replacements[0].is_recovered
    form = {
        **_target_form(preview, mode="replace"),
        **_replacement_form(preview.replacements[0]),
        "confirm": "1",
    }

    wrong = auth_client.post(
        "/data-health/media-reference/repair",
        data={**form, "confirmation_text": "confirm"},
        follow_redirects=True,
    )
    assert "严格模式要求输入固定文本 CONFIRM" in wrong.text
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path == "/media/missing.gif"

    accepted = auth_client.post(
        "/data-health/media-reference/repair",
        data={**form, "confirmation_text": "CONFIRM"},
        follow_redirects=True,
    )
    assert _media_path(replacement, root) in accepted.text
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path == _media_path(replacement, root)


def test_stale_object_reference_issue_and_replacement_requests_are_rejected(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    replacement = _write_gif(root, "replacement.gif", extra=8)
    anchor = _write_gif(root, ".cleanup-anchor-forged.gif", extra=9)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Object Changes", cover_path="/media/missing-1.gif"),
                Item(title="Reference Changes", cover_path="/media/missing-2.gif"),
                Item(title="Issue Changes", cover_path="/media/missing-3.gif"),
                Item(title="Replacement Changes", cover_path="/media/missing-4.gif"),
                Item(title="Anchor Forgery", cover_path="/media/missing-5.gif"),
                Item(title="Healthy", cover_path=_media_path(replacement, root)),
            ]
        )
        db.commit()
        previews = {
            item_id: build_media_reference_repair_preview(
                db,
                object_type="item_cover",
                object_id=item_id,
                q=None,
                page=None,
            )
            for item_id in range(1, 6)
        }
        anchor_identity = local_media.validate_local_media_file(
            _media_path(anchor, root),
            expected_sha256=_digest(anchor),
        )
    before_files = _file_snapshot(root)
    with SessionLocal() as db:
        db.execute(text("UPDATE items SET title = 'Changed' WHERE id = 1"))
        db.execute(
            text("UPDATE items SET cover_path = '/media/new-missing.gif' WHERE id = 2")
        )
        db.commit()
    _write_gif(root, "missing-3.gif", extra=10)
    replacement.write_bytes(_gif_bytes(11))

    responses = []
    for item_id in (1, 2, 3, 4):
        preview = previews[item_id]
        responses.append(
            auth_client.post(
                "/data-health/media-reference/repair",
                data={
                    **_target_form(preview, mode="replace"),
                    **_replacement_form(preview.replacements[0]),
                    "confirm": "1",
                },
                follow_redirects=True,
            )
        )
    forged_anchor = auth_client.post(
        "/data-health/media-reference/repair",
        data={
            **_target_form(previews[5], mode="replace"),
            "replacement_path": anchor_identity.media_path,
            "replacement_sha256": anchor_identity.sha256,
            "expected_size": str(anchor_identity.size),
            "expected_device": str(anchor_identity.device),
            "expected_inode": str(anchor_identity.inode),
            "expected_modified_ns": str(anchor_identity.modified_ns),
            "expected_changed_ns": str(anchor_identity.changed_ns),
            "confirm": "1",
        },
        follow_redirects=True,
    )
    healthy_preview = auth_client.get(
        "/data-health/media-reference/repair",
        params={"object_type": "item_cover", "object_id": 6},
    )

    assert "对象内容已变化" in responses[0].text
    assert "原封面或头像引用已变化" in responses[1].text
    assert "不再属于可修复问题" in responses[2].text
    assert "替代媒体已缺失、损坏或完整身份发生变化" in responses[3].text
    assert "cleanup anchor 不能设置为封面或头像" in forged_anchor.text
    assert healthy_preview.status_code == 400
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path == "/media/missing-1.gif"
        assert db.get(Item, 2).cover_path == "/media/new-missing.gif"
        assert db.get(Item, 3).cover_path == "/media/missing-3.gif"
        assert db.get(Item, 4).cover_path == "/media/missing-4.gif"
        assert db.get(Item, 5).cover_path == "/media/missing-5.gif"
    after_files = _file_snapshot(root)
    assert after_files == {
        **before_files,
        "missing-3.gif": _gif_bytes(10),
        "replacement.gif": _gif_bytes(11),
    }


def test_database_commit_failure_rolls_back_reference_and_never_touches_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    replacement = _write_gif(root, "replacement.gif", extra=12)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as setup_db:
        setup_db.add(Item(title="Rollback", cover_path="/media/missing.gif"))
        setup_db.commit()
        preview = build_media_reference_repair_preview(
            setup_db,
            object_type="item_cover",
            object_id=1,
            q=None,
            page=None,
        )
    before_db = _database_snapshot()
    before_files = _file_snapshot(root)

    with SessionLocal() as db:
        def fail_commit() -> None:
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(MediaReferenceRepairError, match="database_failed"):
            execute_media_reference_repair(
                db,
                **_target_form(preview, mode="replace"),
                **_replacement_form(preview.replacements[0]),
            )

    assert _database_snapshot() == before_db
    assert _file_snapshot(root) == before_files
    assert replacement.exists()


def test_conditional_update_refuses_a_racing_original_reference_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "replacement.gif", extra=13)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as setup_db:
        setup_db.add(Item(title="Race", cover_path="/media/missing.gif"))
        setup_db.commit()
        preview = build_media_reference_repair_preview(
            setup_db,
            object_type="item_cover",
            object_id=1,
            q=None,
            page=None,
        )
    before_files = _file_snapshot(root)
    real_validate = media_reference_repair._validate_submission_target
    validation_count = 0

    def race_after_locked_validation(*args: object, **kwargs: object) -> object:
        nonlocal validation_count
        target = real_validate(*args, **kwargs)
        validation_count += 1
        if validation_count == 2:
            db = kwargs["db"] if "db" in kwargs else args[0]
            db.execute(
                text(
                    "UPDATE items SET cover_path = '/media/racing-reference.gif' "
                    "WHERE id = 1"
                )
            )
        return target

    monkeypatch.setattr(
        media_reference_repair,
        "_validate_submission_target",
        race_after_locked_validation,
    )
    with SessionLocal() as db:
        with pytest.raises(MediaReferenceRepairError, match="stale_reference"):
            execute_media_reference_repair(
                db,
                **_target_form(preview, mode="replace"),
                **_replacement_form(preview.replacements[0]),
            )

    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path == "/media/missing.gif"
    assert _file_snapshot(root) == before_files
