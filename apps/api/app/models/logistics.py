import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import RouteStatus, StopStatus, VehicleType


class Vehicle(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "vehicles"
    __table_args__ = (CheckConstraint("capacity_kg > 0", name="capacity_positive"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    registration_no: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    vehicle_type: Mapped[VehicleType] = enum_col(VehicleType)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    depot_name: Mapped[str | None] = mapped_column(String(120))
    depot_lat: Mapped[float]
    depot_lng: Mapped[float]
    cost_per_km_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    active: Mapped[bool] = flag(True)
    is_sample: Mapped[bool] = flag(False)


class Route(UUIDPk, Timestamps, Base):
    __tablename__ = "routes"

    plan_id: Mapped[uuid.UUID] = mapped_column(index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    planned_date: Mapped[date] = mapped_column(index=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[RouteStatus] = enum_col(RouteStatus, default=RouteStatus.PLANNED)
    distance_m: Mapped[int] = mapped_column(default=0)
    duration_s: Mapped[int] = mapped_column(default=0)
    load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    distance_basis: Mapped[str] = mapped_column(String(30))  # osrm_road | haversine_estimate
    baseline_distance_m: Mapped[int | None]
    solver_status: Mapped[str] = mapped_column(String(40))
    inputs: Mapped[dict[str, Any]] = mapped_column(default=dict)
    warnings: Mapped[list[Any]] = mapped_column(default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    actual_load_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    delay_reports: Mapped[list[Any]] = mapped_column(default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    stops: Mapped[list["RouteStop"]] = relationship(order_by="RouteStop.sequence", lazy="selectin")

    __mapper_args__ = {"version_id_col": version}


class RouteStop(UUIDPk, Base):
    __tablename__ = "route_stops"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int]
    collection_point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_points.id", ondelete="RESTRICT"))
    planned_arrival_s: Mapped[int] = mapped_column(default=0)
    expected_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    cumulative_load_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    leg_distance_m: Mapped[int] = mapped_column(default=0)
    status: Mapped[StopStatus] = enum_col(StopStatus, default=StopStatus.PENDING)
    completed_at: Mapped[datetime | None]
    skip_reason: Mapped[str | None] = mapped_column(Text)
    collection_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_events.id", ondelete="RESTRICT"))
