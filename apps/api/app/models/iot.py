import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import CalibrationStatus, ConnectionStatus, DeviceType, ReadingQuality


class Device(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(40), unique=True)  # hardware identifier, e.g. DEV-ESP32-001
    device_type: Mapped[DeviceType] = enum_col(DeviceType)
    firmware_version: Mapped[str | None] = mapped_column(String(20))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    collection_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_points.id", ondelete="RESTRICT"), unique=True
    )
    is_simulated: Mapped[bool] = flag(False)
    connection_status: Mapped[ConnectionStatus] = enum_col(ConnectionStatus, default=ConnectionStatus.NEVER_SEEN)
    last_seen_at: Mapped[datetime | None]
    last_reading_at: Mapped[datetime | None]
    battery_percent: Mapped[int | None] = mapped_column(SmallInteger)
    last_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    last_fill_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    last_sensor_status: Mapped[str | None] = mapped_column(String(40))
    weight_min_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"), server_default="0")
    weight_max_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("200"), server_default="200")
    bin_depth_cm: Mapped[float | None]
    telemetry_interval_s: Mapped[int] = mapped_column(default=300, server_default="300")
    telemetry_settings: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    calibration_status: Mapped[CalibrationStatus] = enum_col(CalibrationStatus, default=CalibrationStatus.UNCALIBRATED)
    last_calibration_at: Mapped[datetime | None]
    active: Mapped[bool] = flag(True)
    notes: Mapped[str | None] = mapped_column(Text)


class DeviceCredential(UUIDPk, Base):
    """Device secret. Only hashes are stored: SHA-256 (HTTPS ingestion) and Mosquitto PBKDF2 (MQTT)."""

    __tablename__ = "device_credentials"

    device_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    key_prefix: Mapped[str] = mapped_column(String(8))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mqtt_password_hash: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]


class DeviceReading(UUIDPk, Base):
    __tablename__ = "device_readings"
    __table_args__ = (
        UniqueConstraint("device_pk", "reading_id", name="uq_device_reading"),
        Index("ix_device_readings_device_time", "device_pk", "device_timestamp"),
    )

    device_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    reading_id: Mapped[str] = mapped_column(String(64))
    device_timestamp: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    fill_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    battery_percent: Mapped[int | None] = mapped_column(SmallInteger)
    sensor_status: Mapped[str] = mapped_column(String(40))
    firmware_version: Mapped[str | None] = mapped_column(String(20))
    transport: Mapped[str] = mapped_column(String(12))
    quality: Mapped[ReadingQuality] = enum_col(ReadingQuality, default=ReadingQuality.OK)
    quality_notes: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = flag(False)
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Calibration(UUIDPk, Base):
    __tablename__ = "calibrations"

    device_pk: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), index=True)
    performed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    performed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(String(30))  # tare | known_mass | two_point | factory
    reference_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    scale_factor: Mapped[float | None]
    offset: Mapped[float | None]
    result: Mapped[str] = mapped_column(String(10))  # pass | fail
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | device_command
    notes: Mapped[str | None] = mapped_column(Text)
