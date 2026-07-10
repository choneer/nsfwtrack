from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload, selectinload

from app import models
from app.services.pagination import PageInfo, build_page_info


METADATA_TYPES = ("tag", "creator", "collection")
METADATA_CANDIDATE_PAGE_SIZE = 20


class MetadataCleanupError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MetadataCandidateObject:
    id: int
    name: str
    item_count: int


@dataclass(frozen=True)
class MetadataCandidateGroup:
    metadata_type: str
    match_type: str
    match_key: str
    objects: list[MetadataCandidateObject]
    total_objects: int


@dataclass(frozen=True)
class MetadataCandidateSection:
    metadata_type: str
    groups: list[MetadataCandidateGroup]


@dataclass(frozen=True)
class MetadataCandidatePage:
    sections: list[MetadataCandidateSection]
    page_info: PageInfo


@dataclass(frozen=True)
class MetadataComparison:
    metadata_type: str
    primary: Any
    duplicate: Any
    primary_items: list[models.Item]
    duplicate_items: list[models.Item]
    description_conflict: bool
    description_action_preview: str


@dataclass(frozen=True)
class MetadataMergeResult:
    metadata_type: str
    primary_id: int
    primary_name: str
    duplicate_name: str
    transferred_relations: int
    skipped_relations: int
    description_action: str
    duplicate_deleted: bool


def exact_name_key(name: str) -> str:
    return name.strip()


def normalized_name_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name)
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized.casefold()


def _model_for(metadata_type: str) -> type[Any]:
    if metadata_type == "tag":
        return models.Tag
    if metadata_type == "creator":
        return models.Creator
    if metadata_type == "collection":
        return models.Collection
    raise MetadataCleanupError("invalid_type")


def _validate_type(metadata_type: str | None) -> str:
    if metadata_type not in METADATA_TYPES:
        raise MetadataCleanupError("invalid_type")
    return metadata_type


def _parse_id(value: str | int | None) -> int:
    try:
        parsed = int(value) if value not in {None, ""} else 0
    except (TypeError, ValueError) as exc:
        raise MetadataCleanupError("invalid_object") from exc
    if parsed <= 0:
        raise MetadataCleanupError("invalid_object")
    return parsed


def _relation_for(metadata_type: str) -> tuple[type[Any], Any]:
    if metadata_type == "tag":
        return models.ItemTag, models.ItemTag.tag_id
    if metadata_type == "creator":
        return models.ItemCreator, models.ItemCreator.creator_id
    if metadata_type == "collection":
        return models.ItemCollection, models.ItemCollection.collection_id
    raise MetadataCleanupError("invalid_type")


def _load_objects(
    db: Session,
    metadata_type: str,
) -> list[MetadataCandidateObject]:
    model = _model_for(metadata_type)
    relation, relation_target = _relation_for(metadata_type)
    rows = db.execute(
        select(
            model.id,
            model.name,
            func.count(relation.item_id).label("item_count"),
        )
        .outerjoin(relation, relation_target == model.id)
        .group_by(model.id, model.name)
        .order_by(model.name.asc(), model.id.asc())
    ).all()
    return [
        MetadataCandidateObject(
            id=int(object_id),
            name=str(name),
            item_count=int(item_count),
        )
        for object_id, name, item_count in rows
    ]


def _candidate_groups(
    objects: list[MetadataCandidateObject],
    *,
    metadata_type: str,
    match_type: str,
    key_func: Any,
) -> list[MetadataCandidateGroup]:
    buckets: dict[str, list[MetadataCandidateObject]] = {}
    for metadata_object in objects:
        key = key_func(metadata_object.name)
        if key:
            buckets.setdefault(key, []).append(metadata_object)
    groups = [
        MetadataCandidateGroup(
            metadata_type=metadata_type,
            match_type=match_type,
            match_key=key,
            objects=sorted(bucket, key=lambda row: row.id),
            total_objects=len(bucket),
        )
        for key, bucket in buckets.items()
        if len(bucket) > 1
    ]
    return sorted(groups, key=lambda group: (group.match_key, group.objects[0].id))


def _find_type_candidates(
    db: Session,
    metadata_type: str,
) -> list[MetadataCandidateGroup]:
    objects = _load_objects(db, metadata_type)
    groups = _candidate_groups(
        objects,
        metadata_type=metadata_type,
        match_type="exact_name",
        key_func=exact_name_key,
    )
    exact_sets = {frozenset(row.id for row in group.objects) for group in groups}
    for group in _candidate_groups(
        objects,
        metadata_type=metadata_type,
        match_type="normalized_name",
        key_func=normalized_name_key,
    ):
        object_ids = frozenset(row.id for row in group.objects)
        if object_ids not in exact_sets:
            groups.append(group)
    return groups


def _all_candidate_sections(db: Session) -> list[MetadataCandidateSection]:
    return [
        MetadataCandidateSection(
            metadata_type=metadata_type,
            groups=_find_type_candidates(db, metadata_type),
        )
        for metadata_type in METADATA_TYPES
    ]


def find_metadata_cleanup_candidates(
    db: Session,
    *,
    page: str | int | None = None,
) -> MetadataCandidatePage:
    all_sections = _all_candidate_sections(db)
    candidate_pairs = [
        (section.metadata_type, group, duplicate)
        for section in all_sections
        for group in section.groups
        for duplicate in group.objects[1:]
    ]
    page_info = build_page_info(
        page=page,
        page_size=METADATA_CANDIDATE_PAGE_SIZE,
        total=len(candidate_pairs),
    )
    start = (page_info.page - 1) * page_info.page_size
    selected_pairs = candidate_pairs[start : start + page_info.page_size]
    grouped: dict[tuple[str, str, str, int], MetadataCandidateGroup] = {}
    ordered_keys: list[tuple[str, str, str, int]] = []
    for metadata_type, source_group, duplicate in selected_pairs:
        primary = source_group.objects[0]
        key = (
            metadata_type,
            source_group.match_type,
            source_group.match_key,
            primary.id,
        )
        display_group = grouped.get(key)
        if display_group is None:
            display_group = MetadataCandidateGroup(
                metadata_type=metadata_type,
                match_type=source_group.match_type,
                match_key=source_group.match_key,
                objects=[primary],
                total_objects=source_group.total_objects,
            )
            grouped[key] = display_group
            ordered_keys.append(key)
        display_group.objects.append(duplicate)

    sections = [
        MetadataCandidateSection(
            metadata_type=metadata_type,
            groups=[
                grouped[key]
                for key in ordered_keys
                if key[0] == metadata_type
            ],
        )
        for metadata_type in METADATA_TYPES
    ]
    return MetadataCandidatePage(sections=sections, page_info=page_info)


def _get_object(db: Session, metadata_type: str, object_id: int) -> Any:
    model = _model_for(metadata_type)
    metadata_object = db.scalar(
        select(model)
        .where(model.id == object_id)
        .options(
            selectinload(model.items).options(
                noload(models.Item.tags),
                noload(models.Item.creators),
                noload(models.Item.collections),
                noload(models.Item.state),
                noload(models.Item.activity),
            )
        )
    )
    if metadata_object is None:
        raise MetadataCleanupError("invalid_object")
    return metadata_object


def _clean_optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _description_action_preview(primary: Any, duplicate: Any) -> str:
    primary_description = _clean_optional(getattr(primary, "description", None))
    duplicate_description = _clean_optional(getattr(duplicate, "description", None))
    if not duplicate_description:
        return "unchanged"
    if not primary_description:
        return "copied"
    if primary_description != duplicate_description:
        return "kept_primary"
    return "unchanged"


def get_metadata_comparison(
    db: Session,
    metadata_type: str | None,
    primary_id: str | int | None,
    duplicate_id: str | int | None,
) -> MetadataComparison:
    parsed_type = _validate_type(metadata_type)
    parsed_primary_id = _parse_id(primary_id)
    parsed_duplicate_id = _parse_id(duplicate_id)
    if parsed_primary_id == parsed_duplicate_id:
        raise MetadataCleanupError("same_object")

    primary = _get_object(db, parsed_type, parsed_primary_id)
    duplicate = _get_object(db, parsed_type, parsed_duplicate_id)
    primary_items = sorted(primary.items, key=lambda item: (item.title, item.id))
    duplicate_items = sorted(duplicate.items, key=lambda item: (item.title, item.id))
    description_conflict = False
    description_action_preview = "not_applicable"
    if parsed_type == "collection":
        primary_description = _clean_optional(primary.description)
        duplicate_description = _clean_optional(duplicate.description)
        description_conflict = bool(
            primary_description
            and duplicate_description
            and primary_description != duplicate_description
        )
        description_action_preview = _description_action_preview(primary, duplicate)

    return MetadataComparison(
        metadata_type=parsed_type,
        primary=primary,
        duplicate=duplicate,
        primary_items=primary_items,
        duplicate_items=duplicate_items,
        description_conflict=description_conflict,
        description_action_preview=description_action_preview,
    )


def _transfer_items(
    primary_items: list[models.Item],
    duplicate_items: list[models.Item],
) -> tuple[int, int]:
    existing_ids = {item.id for item in primary_items}
    transferred = 0
    skipped = 0
    for item in list(duplicate_items):
        if item.id in existing_ids:
            skipped += 1
        else:
            primary_items.append(item)
            existing_ids.add(item.id)
            transferred += 1
    duplicate_items.clear()
    return transferred, skipped


def _apply_collection_description(
    primary: models.Collection,
    duplicate: models.Collection,
    *,
    use_duplicate_description: bool,
) -> str:
    primary_description = _clean_optional(primary.description)
    duplicate_description = _clean_optional(duplicate.description)
    if not duplicate_description:
        return "unchanged"
    if not primary_description:
        primary.description = duplicate.description
        return "copied"
    if (
        use_duplicate_description
        and duplicate_description
        and primary_description != duplicate_description
    ):
        primary.description = duplicate.description
        return "overwritten"
    if primary_description != duplicate_description:
        return "kept_primary"
    return "unchanged"


def merge_metadata_objects(
    db: Session,
    *,
    metadata_type: str | None,
    primary_id: str | int | None,
    duplicate_id: str | int | None,
    use_duplicate_description: bool = False,
) -> MetadataMergeResult:
    try:
        comparison = get_metadata_comparison(
            db,
            metadata_type=metadata_type,
            primary_id=primary_id,
            duplicate_id=duplicate_id,
        )
        primary = comparison.primary
        duplicate = comparison.duplicate
        primary_name = primary.name
        duplicate_name = duplicate.name

        transferred, skipped = _transfer_items(primary.items, duplicate.items)
        description_action = "not_applicable"
        if comparison.metadata_type == "collection":
            description_action = _apply_collection_description(
                primary,
                duplicate,
                use_duplicate_description=use_duplicate_description,
            )

        db.delete(duplicate)
        db.commit()
        db.refresh(primary)
        return MetadataMergeResult(
            metadata_type=comparison.metadata_type,
            primary_id=primary.id,
            primary_name=primary_name,
            duplicate_name=duplicate_name,
            transferred_relations=transferred,
            skipped_relations=skipped,
            description_action=description_action,
            duplicate_deleted=True,
        )
    except MetadataCleanupError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise MetadataCleanupError("merge_failed") from exc
