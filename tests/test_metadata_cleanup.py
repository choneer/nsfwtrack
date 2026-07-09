from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models import (
    Collection,
    Creator,
    Item,
    ItemCollection,
    ItemCreator,
    ItemTag,
    Tag,
)


def _direct_item(title: str) -> int:
    with SessionLocal() as db:
        item = Item(title=title)
        db.add(item)
        db.commit()
        db.refresh(item)
        return int(item.id)


def _load_items(db: Any, item_ids: list[int] | None) -> list[Item]:
    if not item_ids:
        return []
    return list(db.scalars(select(Item).where(Item.id.in_(item_ids))).all())


def _direct_tag(name: str, item_ids: list[int] | None = None) -> int:
    with SessionLocal() as db:
        tag = Tag(name=name)
        tag.items = _load_items(db, item_ids)
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return int(tag.id)


def _direct_creator(name: str, item_ids: list[int] | None = None) -> int:
    with SessionLocal() as db:
        creator = Creator(name=name, type="other")
        creator.items = _load_items(db, item_ids)
        db.add(creator)
        db.commit()
        db.refresh(creator)
        return int(creator.id)


def _direct_collection(
    name: str,
    item_ids: list[int] | None = None,
    *,
    description: str | None = None,
) -> int:
    with SessionLocal() as db:
        collection = Collection(name=name, description=description)
        collection.items = _load_items(db, item_ids)
        db.add(collection)
        db.commit()
        db.refresh(collection)
        return int(collection.id)


def _table_count(model: Any) -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _item_exists(item_id: int) -> bool:
    with SessionLocal() as db:
        return db.get(Item, item_id) is not None


def _tag_item_ids(tag_id: int) -> set[int]:
    with SessionLocal() as db:
        tag = db.scalar(
            select(Tag).where(Tag.id == tag_id).options(selectinload(Tag.items))
        )
        assert tag is not None
        return {int(item.id) for item in tag.items}


def _creator_item_ids(creator_id: int) -> set[int]:
    with SessionLocal() as db:
        creator = db.scalar(
            select(Creator)
            .where(Creator.id == creator_id)
            .options(selectinload(Creator.items))
        )
        assert creator is not None
        return {int(item.id) for item in creator.items}


def _collection_item_ids(collection_id: int) -> set[int]:
    with SessionLocal() as db:
        collection = db.scalar(
            select(Collection)
            .where(Collection.id == collection_id)
            .options(selectinload(Collection.items))
        )
        assert collection is not None
        return {int(item.id) for item in collection.items}


def _collection_description(collection_id: int) -> str | None:
    with SessionLocal() as db:
        collection = db.get(Collection, collection_id)
        assert collection is not None
        return collection.description


def _object_exists(model: Any, object_id: int) -> bool:
    with SessionLocal() as db:
        return db.get(model, object_id) is not None


def test_cleanup_page_requires_login(client: TestClient) -> None:
    response = client.get("/cleanup", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_cleanup_page_renders_empty_state(auth_client: TestClient) -> None:
    response = auth_client.get("/cleanup")

    assert response.status_code == 200
    assert "没有重复元数据" in response.text
    assert "候选列表只读" in response.text


def test_cleanup_page_detects_tag_exact_and_normalized_candidates(
    auth_client: TestClient,
) -> None:
    exact_id = _direct_tag("Exact Tag")
    spaced_id = _direct_tag("  Exact Tag  ")
    _direct_tag("Ａ Tag")
    _direct_tag("a tag")
    _direct_tag("Unique Local Tag")

    response = auth_client.get("/cleanup")

    assert response.status_code == 200
    assert "重复标签" in response.text
    assert "名称完全匹配" in response.text
    assert "名称归一化匹配" in response.text
    assert "Exact Tag" in response.text
    assert "Ａ Tag" in response.text
    assert "a tag" in response.text
    assert "Unique Local Tag" not in response.text
    assert (
        f"/cleanup/compare?type=tag&primary_id={exact_id}&duplicate_id={spaced_id}"
        in response.text
    )
    with SessionLocal() as db:
        preserved_name = db.get(Tag, spaced_id).name  # type: ignore[union-attr]
    assert preserved_name == "  Exact Tag  "


def test_cleanup_page_detects_creator_exact_and_normalized_candidates(
    auth_client: TestClient,
) -> None:
    _direct_creator("Exact Creator")
    _direct_creator(" Exact Creator ")
    _direct_creator("Ａrtist")
    _direct_creator("artist")
    _direct_creator("Unique Creator")

    response = auth_client.get("/cleanup")

    assert response.status_code == 200
    assert "重复创作者" in response.text
    assert "Exact Creator" in response.text
    assert "Ａrtist" in response.text
    assert "artist" in response.text
    assert "Unique Creator" not in response.text


def test_cleanup_page_detects_collection_exact_and_normalized_candidates(
    auth_client: TestClient,
) -> None:
    _direct_collection("Exact Collection")
    _direct_collection(" Exact Collection ")
    _direct_collection("Ｆavorites")
    _direct_collection("favorites")
    _direct_collection("Unique Collection")

    response = auth_client.get("/cleanup")

    assert response.status_code == 200
    assert "重复合集" in response.text
    assert "Exact Collection" in response.text
    assert "Ｆavorites" in response.text
    assert "favorites" in response.text
    assert "Unique Collection" not in response.text


def test_cleanup_compare_page_validation_and_content(
    auth_client: TestClient,
) -> None:
    primary_item = _direct_item("Primary Related")
    duplicate_item = _direct_item("Duplicate Related")
    primary_id = _direct_tag("Compare Tag", [primary_item])
    duplicate_id = _direct_tag(" compare tag ", [duplicate_item])

    response = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
    )

    assert response.status_code == 200
    assert "对比元数据" in response.text
    assert "保留对象" in response.text
    assert "将被删除的对象" in response.text
    assert "危险操作" in response.text
    assert "合并标签" in response.text
    assert "Primary Related" in response.text
    assert "Duplicate Related" in response.text

    invalid_type = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "bad",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )
    assert invalid_type.status_code == 200
    assert "清理类型无效" in invalid_type.text

    missing_primary = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "tag",
            "primary_id": "9999",
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )
    assert "对象不存在或 ID 无效" in missing_primary.text

    missing_duplicate = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": "9999",
        },
        follow_redirects=True,
    )
    assert "对象不存在或 ID 无效" in missing_duplicate.text

    same_object = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(primary_id),
        },
        follow_redirects=True,
    )
    assert "不能合并同一对象" in same_object.text


def test_cleanup_compare_page_shows_collection_description_conflict(
    auth_client: TestClient,
) -> None:
    primary_id = _direct_collection(
        "Compare Collection",
        description="primary description",
    )
    duplicate_id = _direct_collection(
        " compare collection ",
        description="duplicate description",
    )

    response = auth_client.get(
        "/cleanup/compare",
        params={
            "type": "collection",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
    )

    assert response.status_code == 200
    assert "primary description" in response.text
    assert "duplicate description" in response.text
    assert "description 冲突" in response.text
    assert "使用重复合集 description" in response.text


def test_cleanup_merge_requires_login_and_post(client: TestClient) -> None:
    primary_id = _direct_tag("Unauth Tag")
    duplicate_id = _direct_tag(" unauth tag ")

    post_response = client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=False,
    )
    get_response = client.get(
        "/cleanup/merge",
        params={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
    )

    assert post_response.status_code == 303
    assert post_response.headers["location"] == "/login"
    assert get_response.status_code == 405
    assert _object_exists(Tag, primary_id)
    assert _object_exists(Tag, duplicate_id)


def test_cleanup_merge_invalid_requests_fail_without_deleting_objects(
    auth_client: TestClient,
) -> None:
    primary_id = _direct_tag("Invalid Merge Tag")
    duplicate_id = _direct_tag(" invalid merge tag ")

    invalid_type = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "bad",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )
    same_object = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(primary_id),
        },
        follow_redirects=True,
    )
    missing_object = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": "9999",
        },
        follow_redirects=True,
    )

    assert "清理类型无效" in invalid_type.text
    assert "不能合并同一对象" in same_object.text
    assert "对象不存在或 ID 无效" in missing_object.text
    assert _object_exists(Tag, primary_id)
    assert _object_exists(Tag, duplicate_id)


def test_tag_merge_transfers_relations_skips_duplicates_and_deletes_duplicate(
    auth_client: TestClient,
) -> None:
    primary_item = _direct_item("Tag Primary Item")
    duplicate_item = _direct_item("Tag Duplicate Item")
    shared_item = _direct_item("Tag Shared Item")
    primary_id = _direct_tag("Merge Tag", [primary_item, shared_item])
    duplicate_id = _direct_tag(" merge tag ", [duplicate_item, shared_item])

    response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "合并摘要" in response.text
    assert "类型 标签" in response.text
    assert "转移关联 1 条" in response.text
    assert "跳过重复关联 1 条" in response.text
    assert "已删除重复对象" in response.text
    assert _tag_item_ids(primary_id) == {primary_item, duplicate_item, shared_item}
    assert not _object_exists(Tag, duplicate_id)
    assert _item_exists(primary_item)
    assert _item_exists(duplicate_item)
    assert _item_exists(shared_item)
    assert _table_count(ItemTag) == 3


def test_creator_merge_transfers_relations_skips_duplicates_and_deletes_duplicate(
    auth_client: TestClient,
) -> None:
    primary_item = _direct_item("Creator Primary Item")
    duplicate_item = _direct_item("Creator Duplicate Item")
    shared_item = _direct_item("Creator Shared Item")
    primary_id = _direct_creator("Merge Creator", [primary_item, shared_item])
    duplicate_id = _direct_creator(" merge creator ", [duplicate_item, shared_item])

    response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "creator",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "类型 创作者" in response.text
    assert "转移关联 1 条" in response.text
    assert "跳过重复关联 1 条" in response.text
    assert _creator_item_ids(primary_id) == {primary_item, duplicate_item, shared_item}
    assert not _object_exists(Creator, duplicate_id)
    assert _item_exists(primary_item)
    assert _item_exists(duplicate_item)
    assert _item_exists(shared_item)
    assert _table_count(ItemCreator) == 3


def test_collection_merge_keeps_primary_description_and_deletes_no_items(
    auth_client: TestClient,
) -> None:
    primary_item = _direct_item("Collection Primary Item")
    duplicate_item = _direct_item("Collection Duplicate Item")
    shared_item = _direct_item("Collection Shared Item")
    _direct_tag("Collection Safety Tag", [duplicate_item])
    _direct_creator("Collection Safety Creator", [duplicate_item])
    primary_id = _direct_collection(
        "Merge Collection",
        [primary_item, shared_item],
        description="primary description",
    )
    duplicate_id = _direct_collection(
        " merge collection ",
        [duplicate_item, shared_item],
        description="duplicate description",
    )
    before_tag_count = _table_count(Tag)
    before_creator_count = _table_count(Creator)

    response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "collection",
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "类型 合集" in response.text
    assert "description 保留 primary" in response.text
    assert _collection_item_ids(primary_id) == {primary_item, duplicate_item, shared_item}
    assert _collection_description(primary_id) == "primary description"
    assert not _object_exists(Collection, duplicate_id)
    assert _item_exists(primary_item)
    assert _item_exists(duplicate_item)
    assert _item_exists(shared_item)
    assert _table_count(ItemCollection) == 3
    assert _table_count(Tag) == before_tag_count
    assert _table_count(Creator) == before_creator_count


def test_collection_merge_can_copy_or_overwrite_description(
    auth_client: TestClient,
) -> None:
    copy_primary_id = _direct_collection("Copy Description")
    copy_duplicate_id = _direct_collection(
        " copy description ",
        description="copied description",
    )

    copy_response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "collection",
            "primary_id": str(copy_primary_id),
            "duplicate_id": str(copy_duplicate_id),
        },
        follow_redirects=True,
    )

    assert copy_response.status_code == 200
    assert "description 已复制" in copy_response.text
    assert _collection_description(copy_primary_id) == "copied description"
    assert not _object_exists(Collection, copy_duplicate_id)

    overwrite_primary_id = _direct_collection(
        "Overwrite Description",
        description="primary description",
    )
    overwrite_duplicate_id = _direct_collection(
        " overwrite description ",
        description="duplicate description",
    )

    overwrite_response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "collection",
            "primary_id": str(overwrite_primary_id),
            "duplicate_id": str(overwrite_duplicate_id),
            "use_duplicate_description": "1",
        },
        follow_redirects=True,
    )

    assert overwrite_response.status_code == 200
    assert "description 已覆盖" in overwrite_response.text
    assert _collection_description(overwrite_primary_id) == "duplicate description"
    assert not _object_exists(Collection, overwrite_duplicate_id)


def test_cleanup_i18n_zh_and_en_labels(auth_client: TestClient) -> None:
    zh_response = auth_client.get("/cleanup")
    assert zh_response.status_code == 200
    assert "元数据清理" in zh_response.text
    assert "没有重复元数据" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/cleanup"},
        follow_redirects=True,
    )

    assert en_response.status_code == 200
    assert "Metadata Cleanup" in en_response.text
    assert "No Duplicate Metadata" in en_response.text
