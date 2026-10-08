import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import (
    DataOrigin,
    DocumentationStatus,
    EvidenceStatus,
    ExpenseCategory,
    ListingStatus,
    OfferStatus,
    OutcomeType,
    PaymentStatus,
    TransferStatus,
)


class ProcessingPartner(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "processing_partners"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    supported_category_codes: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[str | None] = mapped_column(Text)
    authorization_refs: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    documentation_status: Mapped[DocumentationStatus] = enum_col(DocumentationStatus, default=DocumentationStatus.NOT_SUBMITTED)
    documentation_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    documentation_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    documentation_reviewed_at: Mapped[datetime | None]
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    active: Mapped[bool] = flag(True)
    is_sample: Mapped[bool] = flag(False)


class ProcessingTransfer(UUIDPk, Timestamps, Base):
    __tablename__ = "processing_transfers"
    __table_args__ = (
        CheckConstraint("allocated_kg > 0", name="allocated_positive"),
        CheckConstraint("received_kg IS NULL OR received_kg >= 0", name="received_non_negative"),
        CheckConstraint(
            "accepted_kg IS NULL OR rejected_kg IS NULL OR received_kg IS NULL OR accepted_kg + rejected_kg <= received_kg",
            name="decision_within_received",
        ),
        Index("ix_processing_transfers_partner_status", "partner_id", "status"),
    )

    code: Mapped[str] = mapped_column(String(30), unique=True)
    source_facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"), index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_partners.id", ondelete="RESTRICT"))
    status: Mapped[TransferStatus] = enum_col(TransferStatus, default=TransferStatus.ALLOCATED)
    allocated_kg: Mapped[Decimal]
    transporter_name: Mapped[str | None] = mapped_column(String(160))
    vehicle_no: Mapped[str | None] = mapped_column(String(20))
    manifest_ref: Mapped[str | None] = mapped_column(String(60))
    dispatched_at: Mapped[datetime | None]
    received_at: Mapped[datetime | None]
    received_kg: Mapped[Decimal | None]
    receipt_discrepancy_kg: Mapped[Decimal | None]
    discrepancy_flag: Mapped[bool] = flag(False)
    accepted_kg: Mapped[Decimal | None]
    rejected_kg: Mapped[Decimal | None]
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    returned_kg: Mapped[Decimal | None]
    receipt_reference: Mapped[str | None] = mapped_column(String(60))
    receipt_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime | None]
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    notes: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}


class ProcessingOutcome(UUIDPk, Base):
    """What the partner reports happened to accepted material. Dispatch alone is never recycling."""

    __tablename__ = "processing_outcomes"
    __table_args__ = (CheckConstraint("output_kg >= 0", name="output_non_negative"),)

    transfer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_transfers.id", ondelete="RESTRICT"), index=True)
    outcome_type: Mapped[OutcomeType] = enum_col(OutcomeType)
    input_kg: Mapped[Decimal]
    output_kg: Mapped[Decimal]
    process_date: Mapped[date]
    process_description: Mapped[str | None] = mapped_column(Text)
    receipt_reference: Mapped[str | None] = mapped_column(String(60))
    evidence_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    attested_by_name: Mapped[str] = mapped_column(String(120))
    attested_by_user: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    attestation_text: Mapped[str | None] = mapped_column(Text)
    evidence_status: Mapped[EvidenceStatus] = enum_col(EvidenceStatus, default=EvidenceStatus.NONE)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped[datetime | None]
    review_notes: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MaterialListing(UUIDPk, Timestamps, Base):
    __tablename__ = "material_listings"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="quantity_positive"),)

    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_categories.id", ondelete="RESTRICT"))
    quantity_kg: Mapped[Decimal]
    asking_price_paise_per_kg: Mapped[int | None] = mapped_column(BigInteger)
    price_is_hypothetical: Mapped[bool] = flag(True)
    quality_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ListingStatus] = enum_col(ListingStatus, default=ListingStatus.OPEN)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}


class MaterialOffer(UUIDPk, Timestamps, Base):
    __tablename__ = "material_offers"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="quantity_positive"),)

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_listings.id", ondelete="RESTRICT"), index=True)
    buyer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))  # quote_request | offer
    quantity_kg: Mapped[Decimal]
    price_paise_per_kg: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[OfferStatus] = enum_col(OfferStatus)
    message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    responded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)


class Sale(UUIDPk, Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="quantity_positive"),
        CheckConstraint("unit_price_paise >= 0 AND total_paise >= 0", name="money_non_negative"),
    )

    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_listings.id", ondelete="RESTRICT"))
    offer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_offers.id", ondelete="RESTRICT"))
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"), index=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    buyer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    quantity_kg: Mapped[Decimal]
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    sold_on: Mapped[date]
    invoice_number: Mapped[str | None] = mapped_column(String(40))
    invoice_date: Mapped[date | None]
    invoice_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_transfers.id", ondelete="RESTRICT"))
    shipment_note: Mapped[str | None] = mapped_column(Text)
    payment_status: Mapped[PaymentStatus] = enum_col(PaymentStatus, default=PaymentStatus.PENDING)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Payment(UUIDPk, Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount_paise > 0", name="amount_positive"),)

    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    paid_on: Mapped[date]
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(60))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Expense(UUIDPk, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_non_negative"),
        Index("ix_expenses_org_date", "organization_id", "incurred_on"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    category: Mapped[ExpenseCategory] = enum_col(ExpenseCategory)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    incurred_on: Mapped[date]
    description: Mapped[str | None] = mapped_column(Text)
    village_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    route_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("routes.id", ondelete="RESTRICT"))
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"))
    is_estimate: Mapped[bool] = flag(False)
    assumption_note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
