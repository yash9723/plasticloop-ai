import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk, enum_col
from app.models.enums import DataOrigin, MediaPurpose, Severity, VisionAdapterKind


class MediaFile(UUIDPk, Base):
    __tablename__ = "media_files"

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    purpose: Mapped[MediaPurpose] = enum_col(MediaPurpose)
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str | None] = mapped_column(String(160))
    width: Mapped[int | None]
    height: Mapped[int | None]
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_dedupe", "user_id", "dedupe_key", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[Severity] = enum_col(Severity, default=Severity.INFO)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    link: Mapped[str | None] = mapped_column(String(255))
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VisionPrediction(UUIDPk, Base):
    """The model's (or heuristic's) suggestion. Never a final label on its own."""

    __tablename__ = "vision_predictions"

    media_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_files.id", ondelete="RESTRICT"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"))
    adapter: Mapped[VisionAdapterKind] = enum_col(VisionAdapterKind)
    model_name: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    candidates: Mapped[list[Any]] = mapped_column(default=list)  # [{label, score}] sorted desc
    top_label: Mapped[str | None] = mapped_column(String(40))
    top_score: Mapped[float | None]
    threshold: Mapped[float]
    low_confidence: Mapped[bool]
    boxes: Mapped[list[Any]] = mapped_column(default=list)
    inference_ms: Mapped[float | None]
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    data_origin: Mapped[DataOrigin] = enum_col(DataOrigin, default=DataOrigin.LIVE)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VisionReview(UUIDPk, Base):
    """Human-verified final classification, stored separately from the suggestion."""

    __tablename__ = "vision_reviews"

    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vision_predictions.id", ondelete="RESTRICT"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    final_label: Mapped[str] = mapped_column(String(40))
    agrees_with_model: Mapped[bool | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
