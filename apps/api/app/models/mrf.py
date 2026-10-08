import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import LOCATION_SQL, Base, Geography, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import BatchStatus, DataOrigin, FacilityType, MovementType, VerificationStatus


class Facility(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "facilities"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    facility_type: Mapped[FacilityType] = enum_col(FacilityType)
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    location: Mapped[Any] = mapped_column(Geography(), Computed(LOCATION_SQL, persisted=True), nullable=True, deferred=True)
    address: Mapped[str | None] = mapped_column(Text)
    capacity_kg_per_day: Mapped[Decimal | None]
    storage_locations: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    active: Mapped[bool] = flag(True)
    is_sample: Mapped[bool] = flag(False)


class MaterialCategory(UUIDPk, Base):
    __tablename__ = "material_categories"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(80))
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    description: Mapped[str | None] = mapped_column(Text)
    is_mlp: Mapped[bool] = flag(False)
    is_unsorted: Mapped[bool] = flag(False)
    recoverable: Mapped[bool] = flag(True)
    requires_evidence_for_verification: Mapped[bool] = flag(False)
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")


class FacilityIntake(UUIDPk, Base):
    __tablename__ = "facility_intakes"
    __table_args__ = (
        CheckConstraint("gross_kg > 0 AND tare_kg >= 0 AND gross_kg > tare_kg", name="weights_valid"),
        CheckConstraint("net_kg = gross_kg - tare_kg", name="net_consistent"),
    )

    code: Mapped[str] = mapped_column(String(30), unique=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    origin_village_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("routes.id", ondelete="RESTRICT"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    transporter_name: Mapped[str | None] = mapped_column(String(160))
    received_at: Mapped[datetime]
    gross_kg: Mapped[Decimal]
    tare_kg: Mapped[Decimal]
    net_kg: Mapped[Decimal]
    declared_collected_kg: Mapped[Decimal | None]
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    operator_confirmed_at: Mapped[datetime | None]
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MaterialBatch(UUIDPk, Timestamps, Base):
    __tablename__ = "material_batches"
    __table_args__ = (
        CheckConstraint("current_weight_kg >= 0", name="current_non_negative"),
        CheckConstraint("initial_weight_kg >= 0", name="initial_non_negative"),
        Index("ix_material_batches_facility_category_status", "facility_id", "category_id", "status"),
    )

    code: Mapped[str] = mapped_column(String(40), unique=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_categories.id", ondelete="RESTRICT"))
    verification_status: Mapped[VerificationStatus] = enum_col(VerificationStatus, default=VerificationStatus.UNVERIFIED)
    initial_weight_kg: Mapped[Decimal]
    current_weight_kg: Mapped[Decimal]
    storage_location: Mapped[str | None] = mapped_column(String(80))
    custodian_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    processing_eligible: Mapped[bool] = flag(True)
    status: Mapped[BatchStatus] = enum_col(BatchStatus, default=BatchStatus.ACTIVE)
    source: Mapped[str] = mapped_column(String(20))  # intake | sort | split | merge | return
    notes: Mapped[str | None] = mapped_column(Text)
    verification_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    verification_note: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}


class BatchOperation(UUIDPk, Base):
    """A sorting / split / merge / adjustment step. Records measured input vs output so differences stay visible."""

    __tablename__ = "batch_operations"

    operation_type: Mapped[str] = mapped_column(String(20))
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    input_kg: Mapped[Decimal]
    output_kg: Mapped[Decimal]
    difference_kg: Mapped[Decimal]
    notes: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BatchLineage(UUIDPk, Base):
    __tablename__ = "batch_lineage"
    __table_args__ = (CheckConstraint("parent_batch_id <> child_batch_id", name="no_self_link"),)

    parent_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"), index=True)
    child_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"), index=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batch_operations.id", ondelete="RESTRICT"))
    weight_kg: Mapped[Decimal]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BatchMovement(UUIDPk, Base):
    """Append-only signed ledger (enforced by a DB trigger). Sum of quantity_kg per batch == current weight."""

    __tablename__ = "batch_movements"
    __table_args__ = (
        CheckConstraint("quantity_kg <> 0", name="non_zero"),
        CheckConstraint("balance_after_kg >= 0", name="balance_non_negative"),
        Index("ix_batch_movements_batch_time", "batch_id", "occurred_at"),
        Index("ix_batch_movements_facility_type", "facility_id", "movement_type"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"))
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    operation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batch_operations.id", ondelete="RESTRICT"))
    movement_type: Mapped[MovementType] = enum_col(MovementType)
    quantity_kg: Mapped[Decimal]
    balance_after_kg: Mapped[Decimal]
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
