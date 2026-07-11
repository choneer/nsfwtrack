from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.local_media import normalize_local_media_path


StatusValue = Literal["wish", "watching", "watched", "like", "dislike", "ignore"]


class LoginRequest(BaseModel):
    password: str


class TagBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=128)

    @field_validator("name", "category")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=128)

    @field_validator("name", "category")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TagRead(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class CreatorBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="other", max_length=64)
    avatar_path: str | None = Field(default=None, max_length=500)

    @field_validator("name", "type")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("avatar_path")
    @classmethod
    def validate_avatar_path(cls, value: str | None) -> str | None:
        return normalize_local_media_path(value)


class CreatorCreate(CreatorBase):
    pass


class CreatorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = Field(default=None, max_length=64)
    avatar_path: str | None = Field(default=None, max_length=500)

    @field_validator("name", "type")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("avatar_path")
    @classmethod
    def validate_avatar_path(cls, value: str | None) -> str | None:
        return normalize_local_media_path(value)


class CreatorRead(CreatorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class StateBase(BaseModel):
    status: StatusValue
    rating: int | None = Field(default=None, ge=1, le=5)
    review: str | None = None

    @field_validator("review")
    @classmethod
    def strip_review(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class StateCreate(StateBase):
    pass


class StateRead(StateBase):
    id: int
    item_id: int
    created_at: datetime
    updated_at: datetime


class ItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    cover_path: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    release_date: str | None = Field(default=None, max_length=32)
    extra: dict[str, Any] | None = None

    @field_validator("title", "summary", "release_date")
    @classmethod
    def strip_item_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("cover_path")
    @classmethod
    def validate_cover_path(cls, value: str | None) -> str | None:
        return normalize_local_media_path(value)


class ItemCreate(ItemBase):
    tags: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    cover_path: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    release_date: str | None = Field(default=None, max_length=32)
    extra: dict[str, Any] | None = None
    tags: list[str] | None = None
    creators: list[str] | None = None

    @field_validator("title", "summary", "release_date")
    @classmethod
    def strip_item_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("cover_path")
    @classmethod
    def validate_cover_path(cls, value: str | None) -> str | None:
        return normalize_local_media_path(value)


class ItemRead(ItemBase):
    id: int
    tags: list[TagRead] = Field(default_factory=list)
    creators: list[CreatorRead] = Field(default_factory=list)
    state: StateRead | None = None
    created_at: datetime
    updated_at: datetime
