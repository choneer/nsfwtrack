from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ItemTag(Base):
    __tablename__ = "item_tags"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class ItemCreator(Base):
    __tablename__ = "item_creators"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True
    )


class ItemCollection(Base):
    __tablename__ = "item_collections"
    __table_args__ = (
        UniqueConstraint("item_id", "collection_id", name="uq_item_collections_pair"),
    )

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )


class SavedView(Base):
    __tablename__ = "saved_views"
    __table_args__ = (
        CheckConstraint("trim(name) != ''", name="ck_saved_views_name_not_blank"),
        UniqueConstraint("name", name="uq_saved_views_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    query_string: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class ItemActivity(Base):
    __tablename__ = "item_activity"
    __table_args__ = (
        CheckConstraint("view_count >= 0", name="ck_item_activity_view_count"),
        CheckConstraint("edit_count >= 0", name="ck_item_activity_edit_count"),
        UniqueConstraint("item_id", name="uq_item_activity_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    last_viewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    view_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    last_edited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    edit_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    item: Mapped[Item] = relationship(back_populates="activity")


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("trim(key) != ''", name="ck_app_settings_key_not_blank"),
        UniqueConstraint("key", name="uq_app_settings_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )


class MediaIndexEntry(Base):
    __tablename__ = "media_index_entries"
    __table_args__ = (
        CheckConstraint(
            "record_type IN ('media','directory')",
            name="ck_media_index_entries_record_type",
        ),
        UniqueConstraint("media_path", name="uq_media_index_entries_media_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    media_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    basename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    parent_directory: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", index=True
    )
    extension: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    size: Mapped[int] = mapped_column(nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    recovered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mode: Mapped[int] = mapped_column(nullable=False)
    device: Mapped[int] = mapped_column(nullable=False)
    inode: Mapped[int] = mapped_column(nullable=False)
    modified_ns: Mapped[int] = mapped_column(nullable=False)
    changed_ns: Mapped[int] = mapped_column(nullable=False)
    directory_mapping_token: Mapped[str] = mapped_column(String(64), nullable=False)
    directory_identity_json: Mapped[str] = mapped_column(Text, nullable=False)
    cache_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(nullable=False)


class MediaIndexState(Base):
    __tablename__ = "media_index_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_media_index_state_singleton"),
        CheckConstraint(
            "last_scan_kind IS NULL OR last_scan_kind IN ('incremental','full')",
            name="ck_media_index_state_scan_kind",
        ),
        CheckConstraint(
            "last_scan_result IN ('never','success','failed')",
            name="ck_media_index_state_scan_result",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    index_format_version: Mapped[int] = mapped_column(nullable=False, default=1)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="never_scanned")
    current_media_root_identity: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    last_incremental_scan_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_full_verification_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_scan_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_scan_result: Mapped[str] = mapped_column(
        String(16), nullable=False, default="never"
    )
    last_scan_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    entry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    valid_count: Mapped[int] = mapped_column(nullable=False, default=0)
    damaged_count: Mapped[int] = mapped_column(nullable=False, default=0)
    recovered_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(nullable=False, default=0)
    reused_count: Mapped[int] = mapped_column(nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    removed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    rehashed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    change_details_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    skipped_details_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    snapshot_signature: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class ItemSource(Base):
    __tablename__ = "item_sources"
    __table_args__ = (
        CheckConstraint("trim(url) != ''", name="ck_item_sources_url_not_blank"),
        CheckConstraint(
            "trim(normalized_url) != ''",
            name="ck_item_sources_normalized_url_not_blank",
        ),
        UniqueConstraint("normalized_url", name="uq_item_sources_normalized_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cover_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    tags: Mapped[list[Tag]] = relationship(
        secondary="item_tags",
        back_populates="items",
        lazy="selectin",
    )
    creators: Mapped[list[Creator]] = relationship(
        secondary="item_creators",
        back_populates="items",
        lazy="selectin",
    )
    collections: Mapped[list[Collection]] = relationship(
        secondary="item_collections",
        back_populates="items",
        lazy="selectin",
    )
    state: Mapped[UserItemState | None] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="selectin",
    )
    activity: Mapped[ItemActivity | None] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="selectin",
    )


class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )

    items: Mapped[list[Item]] = relationship(
        secondary="item_creators",
        back_populates="creators",
        lazy="selectin",
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )

    items: Mapped[list[Item]] = relationship(
        secondary="item_tags",
        back_populates="tags",
        lazy="selectin",
    )


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint("trim(name) != ''", name="ck_collections_name_not_blank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    items: Mapped[list[Item]] = relationship(
        secondary="item_collections",
        back_populates="collections",
        lazy="selectin",
    )


class UserItemState(Base):
    __tablename__ = "user_item_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('wish','watching','watched','like','dislike','ignore')",
            name="ck_user_item_states_status",
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)",
            name="ck_user_item_states_rating",
        ),
        UniqueConstraint("item_id", name="uq_user_item_states_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rating: Mapped[int | None] = mapped_column(nullable=True)
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    item: Mapped[Item] = relationship(back_populates="state")
