"""Pure, deterministic planning for incoming video metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from collections.abc import Mapping
from typing import Any

from app.video_metadata.contracts import (
    VideoAsset,
    VideoDetail,
    VideoOrganization,
    VideoPerson,
    VideoRating,
    VideoSeries,
    VideoTag,
    bounded_text,
)


class VideoFieldAction(str, Enum):
    KEEP_LOCAL = "keep_local"
    APPLY_INCOMING = "apply_incoming"
    ADD_CANDIDATE = "add_candidate"
    CONFLICT = "conflict"
    SKIP_MISSING = "skip_missing"
    SKIP_EMPTY = "skip_empty"
    UNKNOWN = "unknown"


class VideoFieldSource(str, Enum):
    USER = "user"
    PROVIDER = "provider"
    NONE = "none"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class VideoFieldDecision:
    field_name: str
    action: VideoFieldAction
    source: VideoFieldSource
    current_value: Any = None
    incoming_value: Any = None
    provider_key: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        normalized_field = bounded_text(self.field_name, 64, field="field_name")
        object.__setattr__(self, "field_name", normalized_field)
        if not isinstance(self.action, VideoFieldAction):
            raise TypeError("action must be VideoFieldAction")
        if not isinstance(self.source, VideoFieldSource):
            raise TypeError("source must be VideoFieldSource")
        if self.provider_key is not None and (
            not isinstance(self.provider_key, str) or not self.provider_key.strip()
        ):
            raise ValueError("provider_key is invalid")
        if self.reason is not None and (
            not isinstance(self.reason, str) or not self.reason.strip()
        ):
            raise ValueError("reason is invalid")
        _validate_plan_value(self.current_value)
        _validate_plan_value(self.incoming_value)


@dataclass(frozen=True, slots=True)
class VideoMetadataMergePlan:
    decisions: tuple[VideoFieldDecision, ...]
    asset_links: tuple[VideoAsset, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decisions, tuple) or not all(
            isinstance(value, VideoFieldDecision) for value in self.decisions
        ):
            raise TypeError("decisions must be a tuple of VideoFieldDecision")
        if not isinstance(self.asset_links, tuple) or not all(
            isinstance(value, VideoAsset) for value in self.asset_links
        ):
            raise TypeError("asset_links must be a tuple of VideoAsset")
        names = tuple(value.field_name for value in self.decisions)
        if names != tuple(sorted(names)):
            raise ValueError("decisions must be in stable field order")
        if len(set(names)) != len(names):
            raise ValueError("decisions contain duplicate fields")


@dataclass(frozen=True, slots=True)
class LocalVideoMetadata:
    """A database-free local snapshot used by the planner.

    ``values`` contains only typed values or immutable tuples.  ``authored``
    marks fields edited by a user; ``provider_values`` records the last value
    observed from each provider so same-provider updates can be distinguished
    from a competing provider.  This object is intentionally not an ORM model.
    """

    values: tuple[tuple[str, object], ...] = ()
    authored: tuple[str, ...] = ()
    provider_values: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or not all(
            isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], str)
            for pair in self.values
        ):
            raise TypeError("values must be tuple pairs")
        if not isinstance(self.authored, tuple) or not all(
            isinstance(value, str) for value in self.authored
        ):
            raise TypeError("authored must be a tuple of field names")
        if not isinstance(self.provider_values, tuple):
            raise TypeError("provider_values must be a tuple")
        names = tuple(name for name, _ in self.values)
        if len(set(names)) != len(names):
            raise ValueError("values contains duplicate fields")
        if len(set(self.authored)) != len(self.authored):
            raise ValueError("authored contains duplicate fields")
        provider_names = tuple(provider for provider, _ in self.provider_values)
        if not all(isinstance(provider, str) and provider.strip() for provider in provider_names):
            raise TypeError("provider_values contains an invalid provider")
        if len(set(provider_names)) != len(provider_names):
            raise ValueError("provider_values contains duplicate providers")
        for _, values in self.provider_values:
            if not isinstance(values, tuple) or not all(
                isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], str)
                for pair in values
            ):
                raise TypeError("provider values must be tuple pairs")
        for _, value in self.values:
            _validate_plan_value(value)
        for _, values in self.provider_values:
            for _, value in values:
                _validate_plan_value(value)

    def value_map(self) -> dict[str, object]:
        return dict(self.values)

    def provider_map(self) -> dict[str, dict[str, object]]:
        return {provider: dict(values) for provider, values in self.provider_values}


_DETAIL_FIELDS = (
    "title",
    "alternate_titles",
    "summary",
    "release_date",
    "duration_seconds",
    "performers",
    "director",
    "studio",
    "publisher",
    "series",
    "tags",
    "rating",
    "cover",
    "preview_images",
    "preview_video",
    "source_updated_at",
)


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, tuple):
        return bool(value)
    return True


def _validate_plan_value(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int, float, date, datetime, Enum)):
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_plan_value(item)
        return
    if isinstance(
        value,
        (
            VideoAsset,
            VideoPerson,
            VideoOrganization,
            VideoRating,
            VideoSeries,
            VideoTag,
        ),
    ):
        return
    if isinstance(value, Mapping) or isinstance(value, (list, set, frozenset)):
        raise TypeError("merge snapshots must not contain mutable mappings or collections")
    raise TypeError("merge snapshot contains an unsupported value")


def _same_identity(left: object, right: object) -> bool:
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(
            _same_identity(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, (VideoPerson, VideoOrganization, VideoSeries, VideoTag)) and isinstance(
        right, type(left)
    ):
        return left.identity == right.identity
    if isinstance(left, VideoAsset) and isinstance(right, VideoAsset):
        return left.identity == right.identity
    return left == right


def _stable_value(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(_stable_value(item) for item in value)
    return value


def _incoming_value(detail: VideoDetail, field_name: str) -> object:
    return getattr(detail, field_name)


def _decision(
    field_name: str,
    action: VideoFieldAction,
    source: VideoFieldSource,
    *,
    current: object = None,
    incoming: object = None,
    provider_key: str | None = None,
    reason: str | None = None,
) -> VideoFieldDecision:
    return VideoFieldDecision(
        field_name=field_name,
        action=action,
        source=source,
        current_value=_stable_value(current),
        incoming_value=_stable_value(incoming),
        provider_key=provider_key,
        reason=reason,
    )


def _normalize_local(local: LocalVideoMetadata | None) -> LocalVideoMetadata:
    if local is None:
        return LocalVideoMetadata()
    if not isinstance(local, LocalVideoMetadata):
        raise TypeError("local must be LocalVideoMetadata")
    return local


def build_video_metadata_merge_plan(
    local: LocalVideoMetadata | None,
    incoming: VideoDetail,
    *,
    provider_priority: tuple[str, ...] | Mapping[str, int] = (),
) -> VideoMetadataMergePlan:
    """Build a plan without mutating local values or performing I/O.

    Priority is explicit: lower tuple index wins.  An absent provider is
    lower priority than every listed provider.  Equal-priority conflicting
    values are retained as ``conflict`` rather than guessed.
    """

    if not isinstance(incoming, VideoDetail):
        raise TypeError("incoming must be VideoDetail")
    if isinstance(provider_priority, Mapping):
        if not all(
            isinstance(key, str) and key.strip() and isinstance(value, int)
            and not isinstance(value, bool)
            for key, value in provider_priority.items()
        ):
            raise TypeError("provider_priority mapping is invalid")
        priority = dict(provider_priority)
    elif isinstance(provider_priority, tuple):
        if not all(isinstance(value, str) and value.strip() for value in provider_priority):
            raise TypeError("provider_priority must contain provider keys")
        if len(set(provider_priority)) != len(provider_priority):
            raise ValueError("provider_priority contains duplicates")
        priority = {provider: index for index, provider in enumerate(provider_priority)}
    else:
        raise TypeError("provider_priority must be a tuple or mapping")
    local_snapshot = _normalize_local(local)
    current = local_snapshot.value_map()
    authored = set(local_snapshot.authored)
    provider_values = local_snapshot.provider_map()
    provider = incoming.provider_key
    default_rank = (max(priority.values()) + 1) if priority else 0
    provider_rank = priority.get(provider, default_rank)
    decisions: list[VideoFieldDecision] = []
    for field_name in _DETAIL_FIELDS:
        incoming_value = _incoming_value(incoming, field_name)
        current_value = current.get(field_name)
        if field_name not in incoming.available_fields:
            decisions.append(_decision(field_name, VideoFieldAction.SKIP_MISSING, VideoFieldSource.NONE, current=current_value, provider_key=provider, reason="incoming field is missing"))
            continue
        if not _present(incoming_value):
            decisions.append(_decision(field_name, VideoFieldAction.SKIP_EMPTY, VideoFieldSource.NONE, current=current_value, incoming=incoming_value, provider_key=provider, reason="empty incoming value cannot erase a value"))
            continue
        if field_name in authored:
            decisions.append(_decision(field_name, VideoFieldAction.KEEP_LOCAL, VideoFieldSource.USER, current=current_value, incoming=incoming_value, provider_key=provider, reason="user-authored value wins"))
            continue
        if field_name in provider_values.get(provider, {}):
            decisions.append(_decision(field_name, VideoFieldAction.APPLY_INCOMING, VideoFieldSource.PROVIDER, current=current_value, incoming=incoming_value, provider_key=provider, reason="same provider update"))
            continue
        competing: list[tuple[int, str, object]] = []
        for other_provider, values in provider_values.items():
            other_value = values.get(field_name)
            if other_value is not None and _present(other_value) and not _same_identity(other_value, incoming_value):
                rank = priority.get(other_provider, default_rank)
                competing.append((rank, other_provider, other_value))
        if competing:
            best_rank = min(rank for rank, _, _ in competing)
            if provider_rank > best_rank:
                decisions.append(_decision(field_name, VideoFieldAction.KEEP_LOCAL, VideoFieldSource.PROVIDER, current=current_value, incoming=incoming_value, provider_key=provider, reason="higher-priority provider value retained"))
                continue
            if provider_rank == best_rank:
                decisions.append(_decision(field_name, VideoFieldAction.CONFLICT, VideoFieldSource.MIXED, current=current_value, incoming=incoming_value, provider_key=provider, reason="equal-priority provider values conflict"))
                continue
            decisions.append(_decision(field_name, VideoFieldAction.APPLY_INCOMING, VideoFieldSource.PROVIDER, current=current_value, incoming=incoming_value, provider_key=provider, reason="incoming provider has higher priority"))
            continue
        if current_value is None or not _present(current_value):
            action = VideoFieldAction.APPLY_INCOMING
            source = VideoFieldSource.PROVIDER
        else:
            action = VideoFieldAction.ADD_CANDIDATE
            source = VideoFieldSource.MIXED
        decisions.append(_decision(field_name, action, source, current=current_value, incoming=incoming_value, provider_key=provider))
    assets = tuple(asset for asset in (incoming.cover, *incoming.preview_images, incoming.preview_video) if asset is not None)
    if assets:
        unique_assets: list[VideoAsset] = []
        seen_assets: set[tuple[str, str]] = set()
        for asset in assets:
            if asset.identity not in seen_assets:
                seen_assets.add(asset.identity)
                unique_assets.append(asset)
    else:
        unique_assets = []
    return VideoMetadataMergePlan(decisions=tuple(sorted(decisions, key=lambda item: item.field_name)), asset_links=tuple(unique_assets))


build_merge_plan = build_video_metadata_merge_plan
plan_metadata_merge = build_video_metadata_merge_plan
VideoMetadataLocalSnapshot = LocalVideoMetadata


__all__ = [
    "LocalVideoMetadata",
    "VideoFieldAction",
    "VideoFieldDecision",
    "VideoFieldSource",
    "VideoMetadataMergePlan",
    "VideoMetadataLocalSnapshot",
    "build_merge_plan",
    "build_video_metadata_merge_plan",
    "plan_metadata_merge",
]
