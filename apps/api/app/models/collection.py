import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import LOCATION_SQL, Base, Geography, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus,
    DataOrigin,
    MeasurementSource,
    PickupStatus,
    PointStatus,
    ReviewStatus,
    SyncReceiptStatus,
)


class Household(UUIDPk, Timestamps, SoftDelete, Base):
    """Private record: never exposed on maps or to other households."""

    __tablename__ = "households"

    village_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    household_code: Mapped[str] = mapped_column(String(30), unique=True)
    head_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    address_line: Mapped[str | None] = mapped_column(String(255))
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    members_count: Mapped[int | None]
    consent_at: Mapped[datetime | None]
    active: Mapped[bool] = flag(True)
    is_sample: Mapped[bool] = flag(False)


class WasteStream(UUIDPk, Timestamps, Base):
    """Configurable source-segregation stream. Seeded streams are DEMO configuration, not an official taxonomy."""

    __tablename__ = "waste_streams"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    description: Mapped[str | None] = mapped_column(Text)
    descriptions: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    color: Mapped[str] = mapped_column(String(9), default="#166534")
    rules: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    active: Mapped[bool] = flag(True)
    is_demo_config: Mapped[bool] = flag(False)


collection_point_streams = Table(
    "collection_point_streams",
    Base.metadata,
    Column("collection_point_id", ForeignKey("collection_points.id", ondelete="CASCADE"), primary_key=True),
    Column("waste_stream_id", ForeignKey("waste_streams.id", ondelete="RESTRICT"), primary_key=True),
)


class CollectionPoint(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "collection_points"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
        CheckConstraint("fill_percent IS NULL OR (fill_percent >= 0 AND fill_percent <= 100)", name="fill_range"),
        Index("ix_collection_points_location", "location", postgresql_using="gist"),
    )

    code: Mapped[str] = mapped_column(String(30), unique=True)
    qr_code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    point_type: Mapped[str] = mapped_column(String(30), default="community_bin")
    village_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"), index=True)
    household_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("households.id", ondelete="RESTRICT"))
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    location: Mapped[Any] = mapped_column(Geography(), Computed(LOCATION_SQL, persisted=True), nullable=True, deferred=True)
    assigned_collector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    pickup_days: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    pickup_window: Mapped[str | None] = mapped_column(String(20))
    bin_capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    fill_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    fill_source: Mapped[str | None] = mapped_column(String(20))
    fill_updated_at: Mapped[datetime | None]
    last_collected_at: Mapped[datetime | None]
    priority: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    emergency_flag: Mapped[bool] = flag(False)
    status: Mapped[PointStatus] = enum_col(PointStatus, default=PointStatus.ACTIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    is_sample: Mapped[bool] = flag(False)

    streams: Mapped[list["WasteStream"]] = relationship(secondary=collection_point_streams, lazy="selectin")

    __mapper_args__ = {"version_id_col": version}


class PickupRequest(UUIDPk, Timestamps, Base):
    __tablename__ = "pickup_requests"
    __table_args__ = (Index("ix_pickup_requests_village_status", "village_id", "status"),)

    village_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    household_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("households.id", ondelete="RESTRICT"), index=True)
    collection_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_points.id", ondelete="RESTRICT"))
    waste_stream_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("waste_streams.id", ondelete="RESTRICT"))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[PickupStatus] = enum_col(PickupStatus, default=PickupStatus.SUBMITTED)
    preferred_date: Mapped[date | None]
    estimated_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    notes: Mapped[str | None] = mapped_column(Text)
    assigned_collector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None]
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}


class CollectionAssignment(UUIDPk, Timestamps, Base):
    __tablename__ = "collection_assignments"
    __table_args__ = (UniqueConstraint("collector_id", "collection_point_id", "scheduled_date", name="uq_assignment_day"),)

    collector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    collection_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_points.id", ondelete="RESTRICT"))
    scheduled_date: Mapped[date] = mapped_column(index=True)
    status: Mapped[AssignmentStatus] = enum_col(AssignmentStatus, default=AssignmentStatus.PENDING)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)


class CollectionEvent(Timestamps, Base):
    """One weighed pickup. `id` is generated by the client (offline-first) and never changes."""

    __tablename__ = "collection_events"
    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_positive"),
        Index("ix_collection_events_village_time", "village_id", "collected_at"),
        Index("ix_collection_events_collector_time", "collector_id", "collected_at"),
        Index("ix_collection_events_point_time", "collection_point_id", "collected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    collection_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_points.id", ondelete="RESTRICT"))
    village_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    collector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    waste_stream_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("waste_streams.id", ondelete="RESTRICT"))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    measurement_source: Mapped[MeasurementSource] = enum_col(MeasurementSource)
    device_reading_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("device_readings.id", ondelete="RESTRICT"))
    calibration_meta: Mapped[dict[str, Any] | None]
    collected_at: Mapped[datetime]
    client_created_at: Mapped[datetime | None]
    gps_lat: Mapped[float | None]
    gps_lng: Mapped[float | None]
    gps_accuracy_m: Mapped[float | None]
    media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    offline_captured: Mapped[bool] = flag(False)
    review_status: Mapped[ReviewStatus] = enum_col(ReviewStatus, default=ReviewStatus.OK)
    review_reason: Mapped[str | None] = mapped_column(Text)
    pickup_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pickup_requests.id", ondelete="RESTRICT"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_assignments.id", ondelete="RESTRICT"))
    route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("routes.id", ondelete="RESTRICT"))
    facility_intake_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("facility_intakes.id", ondelete="RESTRICT"), index=True
    )
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    payload_hash: Mapped[str] = mapped_column(String(64))


class SyncReceipt(Base):
    """Per-event acknowledgement ledger for offline sync. Makes retries idempotent and conflicts auditable."""

    __tablename__ = "sync_receipts"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    client_id: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(30))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[SyncReceiptStatus] = enum_col(SyncReceiptStatus)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    conflict_payload: Mapped[dict[str, Any] | None]
    conflict_count: Mapped[int] = mapped_column(default=0, server_default="0")
    resolution: Mapped[str | None] = mapped_column(String(30))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolved_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Complaint(UUIDPk, Timestamps, Base):
    __tablename__ = "complaints"
    __table_args__ = (Index("ix_complaints_village_status", "village_id", "status"),)

    village_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    household_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("households.id", ondelete="RESTRICT"), index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    category: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    collection_point_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_points.id", ondelete="RESTRICT"))
    pickup_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pickup_requests.id", ondelete="RESTRICT"))
    media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    status: Mapped[ComplaintStatus] = enum_col(ComplaintStatus, default=ComplaintStatus.OPEN)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None]
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}
