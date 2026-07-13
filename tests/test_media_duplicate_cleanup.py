from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.media_duplicate_cleanup import (
    MediaDuplicateCleanupError,
    execute_media_duplicate_cleanup,
)
from app.services.media_item_candidates import build_media_item_candidates
from app.services.media_matching import build_local_media_matches
from app.services.settings import save_app_settings


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


def _anchor_files(media_root: Path) -> list[Path]:
    return list(
        media_root.rglob(f"{local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX}*")
    )


def _assert_database_references_are_valid(digest: str) -> set[str]:
    with SessionLocal() as db:
        paths = {
            path
            for path in [
                *(item.cover_path for item in db.query(Item).all()),
                *(creator.avatar_path for creator in db.query(Creator).all()),
            ]
            if path is not None
        }
    assert paths
    for media_path in paths:
        record = local_media.validate_local_media_file(
            media_path,
            expected_sha256=digest,
        )
        assert record.media_path == media_path
    return paths


def _apply_data(
    digest: str,
    keeper_path: str,
    member_paths: list[str],
    **extra: str,
) -> dict[str, object]:
    return {
        "sha256": digest,
        "keeper_path": keeper_path,
        "member_path": member_paths,
        "confirm": "1",
        **extra,
    }


def test_group_requires_explicit_keeper_and_preview_is_read_only(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Copies/A Keeper.gif", extra=8)
    second = _write_gif(media_root, "Copies/B Second.gif", extra=8)
    third = _write_gif(media_root, "Copies/C Third.gif", extra=8)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    keeper_path = _media_path(keeper, media_root)
    second_path = _media_path(second, media_root)
    third_path = _media_path(third, media_root)
    digest = _digest(keeper)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Preview Item", cover_path=second_path),
                Creator(
                    name="Preview Creator",
                    type="person",
                    avatar_path=third_path,
                ),
            ]
        )
        db.commit()
        before_items = [
            (item.id, item.cover_path) for item in db.query(Item).order_by(Item.id)
        ]
        before_creators = [
            (creator.id, creator.avatar_path)
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
    before_files = {path: path.read_bytes() for path in (keeper, second, third)}

    group_page = auth_client.get("/media-library/duplicates")
    missing_keeper = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest},
        follow_redirects=False,
    )
    preview = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": keeper_path},
    )

    keeper_inputs = re.findall(
        r'<input type="radio" name="keeper_path"[^>]+>', group_page.text
    )
    assert group_page.status_code == 200
    assert len(keeper_inputs) == 3
    assert all("checked" not in field for field in keeper_inputs)
    assert all("required" in field for field in keeper_inputs)
    assert 'action="/media-library/duplicates/organize" method="get"' in group_page.text
    assert missing_keeper.status_code == 303
    assert preview.status_code == 200
    assert f'data-cleanup-keeper="{keeper_path}"' in preview.text
    assert f'data-cleanup-removal="{second_path}"' in preview.text
    assert f'data-cleanup-removal="{third_path}"' in preview.text
    assert "条目封面“Preview Item”将迁移" in preview.text
    assert "创作者头像“Preview Creator”将迁移" in preview.text
    assert 'data-cleanup-member-count>3</strong>' in preview.text
    assert 'data-cleanup-removal-count>2</strong>' in preview.text
    assert 'data-cleanup-reference-count>2</strong>' in preview.text
    assert f'data-cleanup-reclaimable-bytes>{len(keeper.read_bytes()) * 2} B' in preview.text
    assert 'action="/media-library/duplicates/organize/apply" method="post"' in preview.text
    assert preview.text.count('name="member_path"') == 3
    assert "不推荐、不评分且不默认选择 keeper" in preview.text
    with SessionLocal() as db:
        assert [
            (item.id, item.cover_path) for item in db.query(Item).order_by(Item.id)
        ] == before_items
        assert [
            (creator.id, creator.avatar_path)
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
        params={
            "lang": "en",
            "next": "/media-library/duplicates",
        },
    )
    english_group = auth_client.get("/media-library/duplicates")
    english_preview = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": keeper_path},
    )
    assert "Choose the File to Keep" in english_group.text
    assert "Preview Manual Cleanup" in english_group.text
    assert "Duplicate Media Cleanup Preview" in english_preview.text
    assert "does not recommend, score, or preselect a keeper" in english_preview.text


def test_cleanup_migrates_all_references_before_deleting_only_target_group(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Target/A.gif", extra=7)
    second = _write_gif(media_root, "Target/B.gif", extra=7)
    third = _write_gif(media_root, "Target/C.gif", extra=7)
    other_first = _write_gif(media_root, "Other/A.gif", extra=12)
    other_second = _write_gif(media_root, "Other/B.gif", extra=12)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, second, third)]
    keeper_path, second_path, third_path = paths
    digest = _digest(keeper)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Keeper Reference", cover_path=keeper_path),
                Item(title="Second Reference", cover_path=second_path),
                Item(title="Third Reference", cover_path=third_path),
                Creator(
                    name="Second Avatar",
                    type="person",
                    avatar_path=second_path,
                ),
                Creator(
                    name="Third Avatar",
                    type="person",
                    avatar_path=third_path,
                ),
            ]
        )
        db.commit()

    original_delete = local_media.delete_validated_local_media_file

    def assert_references_committed_before_delete(
        record: local_media.ValidatedLocalMediaFile,
    ) -> None:
        with SessionLocal() as db:
            assert db.query(Item).filter(Item.cover_path == record.media_path).count() == 0
            assert (
                db.query(Creator)
                .filter(Creator.avatar_path == record.media_path)
                .count()
                == 0
            )
        reference_paths = _assert_database_references_are_valid(digest)
        assert len(reference_paths) == 1
        assert next(iter(reference_paths)).rsplit("/", 1)[-1].startswith(
            local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX
        )
        original_delete(record)

    monkeypatch.setattr(
        local_media,
        "delete_validated_local_media_file",
        assert_references_committed_before_delete,
    )
    response = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, keeper_path, paths),
    )

    assert response.status_code == 200
    assert 'data-result-item-migrations>2</strong>' in response.text
    assert 'data-result-creator-migrations>2</strong>' in response.text
    assert 'data-result-deleted-count>2</strong>' in response.text
    assert f'data-result-released-bytes>{len(keeper.read_bytes()) * 2} B' in response.text
    assert second_path in response.text
    assert third_path in response.text
    assert keeper.exists()
    assert not second.exists()
    assert not third.exists()
    assert other_first.exists()
    assert other_second.exists()
    assert _digest(other_first) == _digest(other_second)
    with SessionLocal() as db:
        assert {item.cover_path for item in db.query(Item).all()} == {keeper_path}
        assert {creator.avatar_path for creator in db.query(Creator).all()} == {
            keeper_path
        }
    assert _anchor_files(media_root) == []


def test_cleanup_routes_require_login(client: TestClient) -> None:
    preview = client.get(
        "/media-library/duplicates/organize",
        params={"sha256": "a" * 64, "keeper_path": "/media/A.gif"},
        follow_redirects=False,
    )
    apply = client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(
            "a" * 64,
            "/media/A.gif",
            ["/media/A.gif", "/media/B.gif"],
        ),
        follow_redirects=False,
    )

    assert preview.status_code == 303
    assert apply.status_code == 303


def test_cleanup_requires_post_and_exact_strict_confirmation(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Strict/A.gif", extra=5)
    duplicate = _write_gif(media_root, "Strict/B.gif", extra=5)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, duplicate)]
    digest = _digest(keeper)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    missing_text = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, paths[0], paths),
        follow_redirects=False,
    )
    wrong_text = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(
            digest,
            paths[0],
            paths,
            confirmation_text="confirm",
        ),
        follow_redirects=False,
    )

    assert missing_text.status_code == 303
    assert wrong_text.status_code == 303
    assert keeper.exists() and duplicate.exists()
    preview = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": paths[0]},
    )
    assert "data-strict-confirm-message" in preview.text

    accepted = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(
            digest,
            paths[0],
            paths,
            confirmation_text="CONFIRM",
        ),
    )
    assert accepted.status_code == 200
    assert keeper.exists()
    assert not duplicate.exists()
    assert auth_client.get(
        "/media-library/duplicates/organize/apply"
    ).status_code == 405


@pytest.mark.parametrize(
    "mutation",
    ["missing", "hash", "damaged", "symlink", "expanded"],
)
def test_cleanup_rejects_every_stale_file_or_group_state_without_writes(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Stale/A.gif", extra=9)
    duplicate = _write_gif(media_root, "Stale/B.gif", extra=9)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    keeper_path = _media_path(keeper, media_root)
    duplicate_path = _media_path(duplicate, media_root)
    paths = [keeper_path, duplicate_path]
    digest = _digest(keeper)
    with SessionLocal() as db:
        item = Item(title=f"Stale {mutation}", cover_path=duplicate_path)
        db.add(item)
        db.commit()
        item_id = item.id

    preview = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": keeper_path},
    )
    assert preview.status_code == 200
    if mutation == "missing":
        duplicate.unlink()
    elif mutation == "hash":
        duplicate.write_bytes(_gif_bytes(10))
    elif mutation == "damaged":
        duplicate.write_bytes(_gif_bytes(9)[:-1])
    elif mutation == "symlink":
        duplicate.unlink()
        duplicate.symlink_to(keeper)
    else:
        _write_gif(media_root, "Stale/C.gif", extra=9)

    response = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, keeper_path, paths),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "组成员、哈希或文件状态已变化" in response.text
    assert keeper.exists()
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == duplicate_path


def test_cleanup_rejects_forged_escaping_and_nonmember_paths(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Forged/A.gif", extra=6)
    duplicate = _write_gif(media_root, "Forged/B.gif", extra=6)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, duplicate)]
    digest = _digest(keeper)

    invalid_keeper = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": "/media/Forged/Unknown.gif"},
        follow_redirects=True,
    )
    escaping_snapshot = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, paths[0], [paths[0], "/media/../escape.gif"]),
        follow_redirects=True,
    )
    forged_snapshot = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(
            digest,
            paths[0],
            [*paths, "/media/Forged/Unknown.gif"],
        ),
        follow_redirects=True,
    )

    assert "保留路径不是当前重复组成员" in invalid_keeper.text
    assert "预览快照无效或包含伪造路径" in escaping_snapshot.text
    assert "组成员、哈希或文件状态已变化" in forged_snapshot.text
    assert keeper.exists() and duplicate.exists()


def test_delete_failure_keeps_references_safe_and_supports_retry(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Retry/A.gif", extra=4)
    failed = _write_gif(media_root, "Retry/B.gif", extra=4)
    removable = _write_gif(media_root, "Retry/C.gif", extra=4)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, failed, removable)]
    keeper_path, failed_path, removable_path = paths
    digest = _digest(keeper)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Retry Item", cover_path=failed_path),
                Creator(
                    name="Retry Creator",
                    type="person",
                    avatar_path=removable_path,
                ),
            ]
        )
        db.commit()

    original_delete = local_media.delete_validated_local_media_file

    def fail_one(record: local_media.ValidatedLocalMediaFile) -> None:
        if record.media_path == failed_path:
            raise local_media.LocalMediaDeleteError("delete_failed")
        original_delete(record)

    monkeypatch.setattr(local_media, "delete_validated_local_media_file", fail_one)
    first = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, keeper_path, paths),
    )

    assert first.status_code == 200
    assert "未删除文件，可安全重试" in first.text
    assert failed_path in first.text
    assert 'data-result-deleted-count>1</strong>' in first.text
    assert keeper.exists() and failed.exists()
    assert not removable.exists()
    assert _anchor_files(media_root) == []
    with SessionLocal() as db:
        assert {item.cover_path for item in db.query(Item).all()} == {keeper_path}
        assert {creator.avatar_path for creator in db.query(Creator).all()} == {
            keeper_path
        }

    monkeypatch.setattr(
        local_media,
        "delete_validated_local_media_file",
        original_delete,
    )
    retry_preview = auth_client.get(
        "/media-library/duplicates/organize",
        params={"sha256": digest, "keeper_path": keeper_path},
    )
    retry = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, keeper_path, [keeper_path, failed_path]),
    )

    assert retry_preview.status_code == 200
    assert retry.status_code == 200
    assert 'data-result-deleted-count>1</strong>' in retry.text
    assert keeper.exists()
    assert not failed.exists()
    assert _anchor_files(media_root) == []


def test_database_failure_rolls_back_references_before_any_file_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Database/A.gif", extra=3)
    duplicate = _write_gif(media_root, "Database/B.gif", extra=3)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, duplicate)]
    with SessionLocal() as db:
        item = Item(title="Database Failure", cover_path=paths[1])
        db.add(item)
        db.commit()
        item_id = item.id

        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(MediaDuplicateCleanupError) as error:
            execute_media_duplicate_cleanup(
                db,
                sha256=_digest(keeper),
                keeper_path=paths[0],
                expected_member_paths=paths,
            )
        assert error.value.code == "database_failed"

    assert keeper.exists() and duplicate.exists()
    assert _anchor_files(media_root) == []
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == paths[1]


def test_keeper_change_before_anchor_creation_preserves_original_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, "Keeper Change/A.gif", extra=2)
    duplicate = _write_gif(media_root, "Keeper Change/B.gif", extra=2)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    paths = [_media_path(path, media_root) for path in (keeper, duplicate)]
    digest = _digest(keeper)
    with SessionLocal() as db:
        item = Item(title="Keeper Change", cover_path=paths[1])
        db.add(item)
        db.commit()
        item_id = item.id

        def fail_anchor_creation(
            record: local_media.ValidatedLocalMediaFile,
        ) -> local_media.ValidatedLocalMediaFile:
            raise local_media.LocalMediaSafetyAnchorError("source_changed")

        monkeypatch.setattr(
            local_media,
            "create_local_media_safety_anchor",
            fail_anchor_creation,
        )
        with pytest.raises(MediaDuplicateCleanupError) as error:
            execute_media_duplicate_cleanup(
                db,
                sha256=digest,
                keeper_path=paths[0],
                expected_member_paths=paths,
            )
        assert error.value.code == "keeper_changed"

    assert keeper.exists() and duplicate.exists()
    assert _anchor_files(media_root) == []
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == paths[1]


@pytest.mark.parametrize(
    ("race_phase", "replacement"),
    [
        ("before_first_delete", False),
        ("after_half_deleted", True),
        ("during_final_delete", False),
    ],
)
def test_keeper_race_always_keeps_references_on_verified_content(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    race_phase: str,
    replacement: bool,
) -> None:
    media_root = tmp_path / "media"
    keeper = _write_gif(media_root, f"Race {race_phase}/Keeper.gif", extra=13)
    duplicates = [
        _write_gif(
            media_root,
            f"Race {race_phase}/Duplicate {index}.gif",
            extra=13,
        )
        for index in range(1, 5)
    ]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    keeper_path = _media_path(keeper, media_root)
    duplicate_paths = [_media_path(path, media_root) for path in duplicates]
    member_paths = [keeper_path, *duplicate_paths]
    digest = _digest(keeper)
    replacement_content = _gif_bytes(31)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Race Keeper", cover_path=keeper_path),
                Item(title="Race Duplicate", cover_path=duplicate_paths[0]),
                Creator(
                    name="Race Avatar",
                    type="person",
                    avatar_path=duplicate_paths[-1],
                ),
            ]
        )
        db.commit()

    original_delete = local_media.delete_validated_local_media_file
    delete_count = 0

    def mutate_keeper() -> None:
        keeper.unlink()
        if replacement:
            keeper.write_bytes(replacement_content)

    def delete_with_keeper_race(
        record: local_media.ValidatedLocalMediaFile,
    ) -> None:
        nonlocal delete_count
        delete_count += 1
        if race_phase == "before_first_delete" and delete_count == 1:
            mutate_keeper()
        _assert_database_references_are_valid(digest)
        original_delete(record)
        if race_phase == "after_half_deleted" and delete_count == 2:
            mutate_keeper()
        if race_phase == "during_final_delete" and delete_count == 4:
            mutate_keeper()
        _assert_database_references_are_valid(digest)

    monkeypatch.setattr(
        local_media,
        "delete_validated_local_media_file",
        delete_with_keeper_race,
    )
    response = auth_client.post(
        "/media-library/duplicates/organize/apply",
        data=_apply_data(digest, keeper_path, member_paths),
    )

    assert response.status_code == 200
    assert delete_count == 4
    assert 'data-result-deleted-count>4</strong>' in response.text
    assert 'data-result-keeper-recovery' in response.text
    assert all(not path.exists() for path in duplicates)
    final_reference_paths = _assert_database_references_are_valid(digest)
    assert len(final_reference_paths) == 1
    final_path = next(iter(final_reference_paths))
    if replacement:
        assert keeper.read_bytes() == replacement_content
        assert final_path != keeper_path
        assert local_media.LOCAL_MEDIA_RECOVERY_PREFIX in final_path
        assert 'data-result-keeper-recovery="relocated"' in response.text
    else:
        assert keeper.exists()
        assert _digest(keeper) == digest
        assert final_path == keeper_path
        assert 'data-result-keeper-recovery="restored"' in response.text
    assert _anchor_files(media_root) == []


def test_validated_delete_rejects_same_content_inode_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_file = _write_gif(media_root, "Identity/File.gif", extra=1)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    media_path = _media_path(media_file, media_root)
    record = local_media.validate_local_media_file(
        media_path,
        expected_sha256=_digest(media_file),
    )
    content = media_file.read_bytes()
    media_file.unlink()
    media_file.write_bytes(content)

    with pytest.raises(local_media.LocalMediaDeleteError) as error:
        local_media.delete_validated_local_media_file(record)

    assert error.value.code == "changed"
    assert media_file.exists()
