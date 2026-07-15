from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_reference_management
from app.services.media_reference_management import (
    MediaReferenceManagementError,
    build_media_reference_management_preview,
    execute_media_reference_management,
)
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, *, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _service_args(
    preview: media_reference_management.MediaReferenceManagementPreview,
) -> dict[str, object]:
    return {
        "media_path": preview.media.media_path,
        "object_type": preview.target.object_type,
        "object_id": preview.target.object_id,
        "operation": "clear" if preview.action == "clear" else "set",
        "expected_object_token": preview.target.object_token,
        "expected_action": preview.action,
        "expected_sha256": preview.media.sha256,
        "expected_mode": preview.media.mode,
        "expected_size": preview.media.size,
        "expected_device": preview.media.device,
        "expected_inode": preview.media.inode,
        "expected_modified_ns": preview.media.modified_ns,
        "expected_changed_ns": preview.media.changed_ns,
    }


def _form(
    preview: media_reference_management.MediaReferenceManagementPreview,
) -> dict[str, object]:
    return {**_service_args(preview), "confirm": "1"}


def _item_snapshot(item_id: int) -> tuple[object, ...]:
    with SessionLocal() as db:
        row = db.execute(
            select(
                Item.id,
                Item.title,
                Item.cover_path,
                Item.summary,
                Item.release_date,
                Item.extra,
                Item.created_at,
                Item.updated_at,
            ).where(Item.id == item_id)
        ).one()
    return tuple(row)


def _creator_snapshot(creator_id: int) -> tuple[object, ...]:
    with SessionLocal() as db:
        row = db.execute(
            select(
                Creator.id,
                Creator.name,
                Creator.type,
                Creator.avatar_path,
                Creator.created_at,
            ).where(Creator.id == creator_id)
        ).one()
    return tuple(row)


def test_reference_preview_is_authenticated_write_free_and_exposed_from_detail(
    client: TestClient,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    selected = _write_gif(root, "Selected.gif", extra=2)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Empty", cover_path=None),
                Creator(name="Empty Creator", type="person", avatar_path=None),
            ]
        )
        db.commit()
    before_file = selected.read_bytes()
    before_item = _item_snapshot(1)

    with TestClient(client.app) as anonymous:
        denied_get = anonymous.get(
            "/media-library/detail/reference",
            params={
                "media_path": "/media/Selected.gif",
                "object_type": "item_cover",
                "object_id": 1,
                "operation": "set",
            },
            follow_redirects=False,
        )
        denied_post = anonymous.post(
            "/media-library/detail/reference",
            data={},
            follow_redirects=False,
        )
    detail = auth_client.get(
        "/media-library/detail",
        params={"media_path": "/media/Selected.gif"},
    )
    preview = auth_client.get(
        "/media-library/detail/reference",
        params={
            "media_path": "/media/Selected.gif",
            "object_type": "item_cover",
            "object_id": 1,
            "operation": "set",
        },
    )

    assert denied_get.status_code == denied_post.status_code == 303
    assert detail.status_code == preview.status_code == 200
    assert "data-media-reference-entry" in detail.text
    assert "data-media-reference-management-preview" in preview.text
    assert 'data-reference-action="set"' in preview.text
    assert 'name="expected_object_token"' in preview.text
    assert "仅修改一个引用字段" in preview.text
    assert _item_snapshot(1) == before_item
    assert selected.read_bytes() == before_file


def test_set_replace_and_clear_change_only_the_selected_reference_field(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "Selected.gif", extra=4)
    _write_gif(root, "Old.gif", extra=5)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(
                    title="Set Item",
                    cover_path=None,
                    summary="summary",
                    release_date="2026-01-01",
                    extra='{"keep":true}',
                ),
                Item(
                    title="Clear Item",
                    cover_path="/media/Selected.gif",
                    summary="clear summary",
                    release_date="2026-02-02",
                    extra='{"clear":false}',
                ),
                Creator(
                    name="Replace Creator",
                    type="studio",
                    avatar_path="/media/Old.gif",
                ),
            ]
        )
        db.commit()
    item_before = _item_snapshot(1)
    clear_before = _item_snapshot(2)
    creator_before = _creator_snapshot(1)

    with SessionLocal() as db:
        set_preview = build_media_reference_management_preview(
            db,
            media_path="/media/Selected.gif",
            object_type="item_cover",
            object_id=1,
            operation="set",
        )
        assert set_preview.action == "set"
        set_result = execute_media_reference_management(db, **_service_args(set_preview))
    with SessionLocal() as db:
        replace_preview = build_media_reference_management_preview(
            db,
            media_path="/media/Selected.gif",
            object_type="creator_avatar",
            object_id=1,
            operation="set",
        )
        assert replace_preview.action == "replace"
        replace_result = execute_media_reference_management(
            db,
            **_service_args(replace_preview),
        )
    with SessionLocal() as db:
        clear_preview = build_media_reference_management_preview(
            db,
            media_path="/media/Selected.gif",
            object_type="item_cover",
            object_id=2,
            operation="clear",
        )
        assert clear_preview.action == "clear"
        clear_result = execute_media_reference_management(
            db,
            **_service_args(clear_preview),
        )

    item_after = _item_snapshot(1)
    clear_after = _item_snapshot(2)
    creator_after = _creator_snapshot(1)
    assert set_result.warning_code is None
    assert replace_result.warning_code is None
    assert clear_result.warning_code is None
    assert item_after[2] == "/media/Selected.gif"
    assert item_after[:2] + item_after[3:] == item_before[:2] + item_before[3:]
    assert clear_after[2] is None
    assert clear_after[:2] + clear_after[3:] == clear_before[:2] + clear_before[3:]
    assert creator_after[3] == "/media/Selected.gif"
    assert creator_after[:3] + creator_after[4:] == creator_before[:3] + creator_before[4:]
    assert (root / "Selected.gif").exists() and (root / "Old.gif").exists()


def test_reference_management_rejects_stale_object_reference_and_media_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    selected = _write_gif(root, "Selected.gif", extra=7)
    _write_gif(root, "Other.gif", extra=8)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Metadata Race", cover_path=None, summary="old"),
                Item(title="Reference Race", cover_path=None),
                Item(title="Media Race", cover_path=None),
            ]
        )
        db.commit()
        previews = [
            build_media_reference_management_preview(
                db,
                media_path="/media/Selected.gif",
                object_type="item_cover",
                object_id=item_id,
                operation="set",
            )
            for item_id in (1, 2, 3)
        ]
    with SessionLocal() as db:
        db.execute(media_reference_management.text("UPDATE items SET summary='new' WHERE id=1"))
        db.execute(
            media_reference_management.text(
                "UPDATE items SET cover_path='/media/Other.gif' WHERE id=2"
            )
        )
        db.commit()
    selected.write_bytes(_gif_bytes(70))

    codes: list[str] = []
    for preview in previews:
        with SessionLocal() as db, pytest.raises(
            MediaReferenceManagementError
        ) as exc_info:
            execute_media_reference_management(db, **_service_args(preview))
        codes.append(exc_info.value.code)

    assert codes == ["stale_preview", "stale_preview", "stale_preview"]
    with SessionLocal() as db:
        assert [db.get(Item, item_id).cover_path for item_id in (1, 2, 3)] == [
            None,
            "/media/Other.gif",
            None,
        ]


def test_reference_commit_after_error_and_query_failure_are_reported_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "Selected.gif", extra=9)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as setup_db:
        setup_db.add_all(
            [
                Item(title="Committed", cover_path=None),
                Item(title="Unknown Committed", cover_path=None),
                Item(title="Unknown Not Committed", cover_path=None),
            ]
        )
        setup_db.commit()
        previews = [
            build_media_reference_management_preview(
                setup_db,
                media_path="/media/Selected.gif",
                object_type="item_cover",
                object_id=item_id,
                operation="set",
            )
            for item_id in (1, 2, 3)
        ]

    with SessionLocal() as db:
        real_commit = db.commit

        def commit_then_raise() -> None:
            real_commit()
            raise RuntimeError("after commit")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        committed = execute_media_reference_management(db, **_service_args(previews[0]))
    assert committed.warning_code == "committed_after_error"

    monkeypatch.setattr(
        media_reference_management,
        "_inspect_commit_outcome",
        lambda **_: "unknown",
    )
    with SessionLocal() as db:
        real_commit = db.commit

        def commit_then_raise_unknown() -> None:
            real_commit()
            raise RuntimeError("after commit")

        monkeypatch.setattr(db, "commit", commit_then_raise_unknown)
        unknown_committed = execute_media_reference_management(
            db,
            **_service_args(previews[1]),
        )
    with SessionLocal() as db:
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("before commit")),
        )
        unknown_not_committed = execute_media_reference_management(
            db,
            **_service_args(previews[2]),
        )

    assert unknown_committed.warning_code == "commit_outcome_unknown"
    assert unknown_not_committed.warning_code == "commit_outcome_unknown"
    with SessionLocal() as db:
        assert [db.get(Item, item_id).cover_path for item_id in (1, 2, 3)] == [
            "/media/Selected.gif",
            "/media/Selected.gif",
            None,
        ]
    assert (root / "Selected.gif").exists()


def test_reference_commit_inspection_treats_query_failure_and_missing_object_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = media_reference_management.MediaReferenceTarget(
        object_type="item_cover",
        object_id=99,
        object_name="Missing",
        original_path="/media/Old.gif",
        object_token="0" * 64,
    )

    def fail_query(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected independent query failure")

    monkeypatch.setattr(
        media_reference_management,
        "_current_reference",
        fail_query,
    )
    assert (
        media_reference_management._inspect_commit_outcome(
            target=target,
            desired_path=None,
        )
        == "unknown"
    )
    monkeypatch.setattr(
        media_reference_management,
        "_current_reference",
        lambda *_args, **_kwargs: media_reference_management._MISSING_OBJECT,
    )
    assert (
        media_reference_management._inspect_commit_outcome(
            target=target,
            desired_path=None,
        )
        == "unknown"
    )


def test_reference_route_uses_standard_and_strict_confirm(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "Selected.gif", extra=11)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="Strict", cover_path=None))
        db.commit()
        preview = build_media_reference_management_preview(
            db,
            media_path="/media/Selected.gif",
            object_type="item_cover",
            object_id=1,
            operation="set",
        )
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    missing = auth_client.post(
        "/media-library/detail/reference",
        data=_form(preview),
        follow_redirects=False,
    )
    assert missing.status_code == 303
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path is None
    wrong = auth_client.post(
        "/media-library/detail/reference",
        data={**_form(preview), "confirmation_text": "confirm"},
        follow_redirects=False,
    )
    assert wrong.status_code == 303
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path is None
    success = auth_client.post(
        "/media-library/detail/reference",
        data={**_form(preview), "confirmation_text": "CONFIRM"},
        follow_redirects=False,
    )

    assert success.status_code == 303
    with SessionLocal() as db:
        assert db.get(Item, 1).cover_path == "/media/Selected.gif"
