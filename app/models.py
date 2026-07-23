from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC-naive SQLite DATETIME values and expose aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: object,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


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


class ProviderRuntimeState(Base):
    """Non-secret, optimistic runtime configuration for a reviewed Provider."""

    __tablename__ = "provider_runtime_states"
    __table_args__ = (
        CheckConstraint("trim(provider_key) != ''", name="ck_provider_runtime_key"),
        CheckConstraint(
            "runtime_status IN ('disabled','ready','blocked','error')",
            name="ck_provider_runtime_status",
        ),
        CheckConstraint(
            "configuration_status IN ('not_configured','valid','invalid')",
            name="ck_provider_runtime_configuration_status",
        ),
        CheckConstraint(
            "session_status IN ('not_required','missing','available','expired','unknown')",
            name="ck_provider_runtime_session_status",
        ),
        CheckConstraint(
            "configuration_version >= 1",
            name="ck_provider_runtime_configuration_version",
        ),
        CheckConstraint(
            "optimistic_version >= 1",
            name="ck_provider_runtime_optimistic_version",
        ),
    )

    provider_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    runtime_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="disabled", server_default="disabled"
    )
    configuration_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_configured",
        server_default="not_configured",
    )
    egress_profile: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", server_default="default"
    )
    session_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_required",
        server_default="not_required",
    )
    session_updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    session_expires_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    configuration_version: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1"
    )
    optimistic_version: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
        Index(
            "uq_item_sources_provider_identity",
            "provider_key",
            "external_id",
            unique=True,
            sqlite_where=text(
                "provider_key IS NOT NULL AND external_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    metadata_hash: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.current_timestamp()
    )


class OperationTask(Base):
    """Persistent, provider-neutral facts for explicitly controlled work."""

    __tablename__ = "operation_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('asset_download','source_check','metadata_update')",
            name="ck_operation_tasks_type",
        ),
        CheckConstraint(
            "state IN ('planned','awaiting_confirmation','queued','running',"
            "'paused','cancelling','cancelled','succeeded','failed','blocked',"
            "'outcome_unknown')",
            name="ck_operation_tasks_state",
        ),
        CheckConstraint("version >= 1", name="ck_operation_tasks_version"),
        CheckConstraint("attempt_count >= 0", name="ck_operation_tasks_attempts"),
        CheckConstraint("bytes_processed >= 0", name="ck_operation_tasks_bytes"),
        CheckConstraint(
            "expected_bytes IS NULL OR expected_bytes >= 0",
            name="ck_operation_tasks_expected_bytes",
        ),
        CheckConstraint(
            "lease_generation >= 0", name="ck_operation_tasks_lease_generation"
        ),
        CheckConstraint(
            "trim(intent_key) != ''", name="ck_operation_tasks_intent_key"
        ),
        CheckConstraint(
            "error_code IS NULL OR length(error_code) <= 64",
            name="ck_operation_tasks_error_code",
        ),
        CheckConstraint(
            "provider_key IS NULL OR trim(provider_key) != ''",
            name="ck_operation_tasks_provider_key",
        ),
        CheckConstraint(
            "sha256 IS NULL OR length(sha256) = 64",
            name="ck_operation_tasks_sha256",
        ),
        UniqueConstraint("intent_key", name="uq_operation_tasks_intent_key"),
        Index("ix_operation_tasks_state_created", "state", "created_at"),
        Index("ix_operation_tasks_type_created", "task_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    intent_key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asset_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relative_target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    bytes_processed: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    expected_bytes: Mapped[int | None] = mapped_column(nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lease_owner: Mapped[str | None] = mapped_column(String(96), nullable=True)
    lease_generation: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    lease_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_task_events_version"),
        CheckConstraint("trim(event_type) != ''", name="ck_task_events_type"),
        UniqueConstraint("task_id", "version", name="uq_task_events_task_version"),
        Index("ix_task_events_task_created", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("operation_tasks.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class DownloadTaskFact(Base):
    __tablename__ = "download_task_facts"
    __table_args__ = (
        CheckConstraint("trim(asset_id) != ''", name="ck_download_task_facts_asset"),
        CheckConstraint("max_bytes > 0", name="ck_download_task_facts_max_bytes"),
        CheckConstraint(
            "resume_offset >= 0", name="ck_download_task_facts_resume_offset"
        ),
        UniqueConstraint("task_id", name="uq_download_task_facts_task"),
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey("operation_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[str] = mapped_column(String(512), nullable=False)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_name: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    max_bytes: Mapped[int] = mapped_column(nullable=False)
    resume_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resume_offset: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    temp_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    temp_device: Mapped[int | None] = mapped_column(nullable=True)
    temp_inode: Mapped[int | None] = mapped_column(nullable=True)


class SourceCheckFact(Base):
    __tablename__ = "source_check_facts"
    __table_args__ = (
        CheckConstraint("length(detail_hash) = 64", name="ck_source_check_facts_hash"),
        UniqueConstraint("task_id", name="uq_source_check_facts_task"),
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey("operation_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    item_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proposed_source_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    proposed_metadata_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class DiscoveredAssetFact(Base):
    __tablename__ = "discovered_asset_facts"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "asset_id", name="uq_discovered_asset_facts_task_asset"
        ),
        CheckConstraint(
            "expected_bytes IS NULL OR expected_bytes > 0",
            name="ck_discovered_asset_facts_expected_bytes",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("operation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(String(512), nullable=False)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    suggested_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_bytes: Mapped[int | None] = mapped_column(nullable=True)
    expected_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resume_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ItemLocalAsset(Base):
    __tablename__ = "item_local_assets"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_item_local_assets_size"),
        CheckConstraint("length(sha256) = 64", name="ck_item_local_assets_sha256"),
        UniqueConstraint("relative_path", name="uq_item_local_assets_path"),
        UniqueConstraint(
            "item_id", "provider_key", "asset_identity_hash",
            name="uq_item_local_assets_provider_asset",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("operation_tasks.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)
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
