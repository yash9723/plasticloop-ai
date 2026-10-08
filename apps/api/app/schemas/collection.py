import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    ComplaintStatus,
    DataOrigin,
    MeasurementSource,
    PickupStatus,
    PointStatus,
    ReviewStatus,
    SyncReceiptStatus,
)
from app.schemas.auth import PHONE_PATTERN
from app.schemas.common import ORM, Kg, KgIn

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PointType = Literal["community_bin", "household", "institution", "market", "other"]
WINDOW_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$"


# ---------- waste streams ----------

class WasteStreamOut(ORM):
    id: uuid.UUID
    code: str
    label: str
    labels: dict[str, Any]
    description: str | None
    descriptions: dict[str, Any]
    color: str
    rules: list[Any]
    sort_order: int
    active: bool
    is_demo_config: bool


class WasteStreamIn(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    label: str = Field(min_length=2, max_length=80)
    labels: dict[str, str] = {}
    description: str | None = Field(default=None, max_length=1000)
    descriptions: dict[str, str] = {}
    color: str = Field(default="#166534", pattern=r"^#[0-9A-Fa-f]{6}$")
    rules: list[str] = []
    sort_order: int = 0


class WasteStreamPatch(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=80)
    labels: dict[str, str] | None = None
    description: str | None = Field(default=None, max_length=1000)
    descriptions: dict[str, str] | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    rules: list[str] | None = None
    sort_order: int | None = None
    active: bool | None = None


# ---------- collection points ----------

class DeviceBrief(BaseModel):
    id: uuid.UUID
    device_id: str
    connection_status: str
    last_seen_at: datetime | None
    battery_percent: int | None
    is_simulated: bool


class CollectionPointOut(BaseModel):
    id: uuid.UUID
    code: str
    qr_code: str
    name: str
    point_type: str
    village_id: uuid.UUID
    village_name: str | None
    household_id: uuid.UUID | None
    lat: float | None
    lng: float | None
    location_precision: Literal["exact", "approximate"]
    assigned_collector_id: uuid.UUID | None
    assigned_collector_name: str | None
    pickup_days: list[str]
    pickup_window: str | None
    bin_capacity_kg: Kg | None
    fill_percent: float | None
    fill_source: str | None
    fill_updated_at: datetime | None
    last_collected_at: datetime | None
    priority: int
    emergency_flag: bool
    status: PointStatus
    version: int
    is_sample: bool
    stream_ids: list[uuid.UUID]
    device: DeviceBrief | None


class CollectionPointIn(BaseModel):
    village_id: uuid.UUID
    name: str = Field(min_length=2, max_length=160)
    point_type: PointType = "community_bin"
    household_id: uuid.UUID | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    stream_ids: list[uuid.UUID] = Field(min_length=1)
    assigned_collector_id: uuid.UUID | None = None
    pickup_days: list[Weekday] = []
    pickup_window: str | None = Field(default=None, pattern=WINDOW_PATTERN)
    bin_capacity_kg: KgIn | None = None
    priority: int = Field(default=3, ge=1, le=5)


class CollectionPointPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    point_type: PointType | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    stream_ids: list[uuid.UUID] | None = None
    assigned_collector_id: uuid.UUID | None = None
    pickup_days: list[Weekday] | None = None
    pickup_window: str | None = Field(default=None, pattern=WINDOW_PATTERN)
    bin_capacity_kg: KgIn | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    emergency_flag: bool | None = None
    status: PointStatus | None = None
    version: int | None = Field(default=None, description="Optimistic-lock version the client last saw")


class CollectionPointBrief(BaseModel):
    """Compact record cached on the collector's phone for offline QR lookup (no personal data)."""

    id: uuid.UUID
    code: str
    qr_code: str
    name: str
    point_type: str
    village_id: uuid.UUID
    village_name: str | None
    lat: float | None
    lng: float | None
    stream_ids: list[uuid.UUID]
    pickup_days: list[str]
    pickup_window: str | None
    fill_percent: float | None
    last_collected_at: datetime | None
    priority: int
    emergency_flag: bool
    status: PointStatus
    device_id: str | None
    assigned_collector_id: uuid.UUID | None


# ---------- households ----------

class HouseholdOut(BaseModel):
    id: uuid.UUID
    village_id: uuid.UUID
    household_code: str
    head_name: str
    phone: str | None
    address_line: str | None
    lat: float | None
    lng: float | None
    members_count: int | None
    active: bool
    is_sample: bool
    has_account: bool
    created_at: datetime
    redacted: bool = False


class HouseholdIn(BaseModel):
    village_id: uuid.UUID
    head_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    address_line: str | None = Field(default=None, max_length=255)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    members_count: int | None = Field(default=None, ge=1, le=50)


class HouseholdPatch(BaseModel):
    head_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    address_line: str | None = Field(default=None, max_length=255)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    members_count: int | None = Field(default=None, ge=1, le=50)
    active: bool | None = None


# ---------- pickup requests ----------

class PickupRequestOut(ORM):
    id: uuid.UUID
    village_id: uuid.UUID
    household_id: uuid.UUID | None
    collection_point_id: uuid.UUID | None
    waste_stream_id: uuid.UUID | None
    requested_by: uuid.UUID
    status: PickupStatus
    preferred_date: date | None
    estimated_weight_kg: Kg | None
    notes: str | None
    assigned_collector_id: uuid.UUID | None
    cancelled_reason: str | None
    completed_at: datetime | None
    data_origin: DataOrigin
    version: int
    created_at: datetime
    updated_at: datetime


class PickupRequestIn(BaseModel):
    household_id: uuid.UUID | None = None
    collection_point_id: uuid.UUID | None = None
    waste_stream_id: uuid.UUID | None = None
    preferred_date: date | None = None
    estimated_weight_kg: KgIn | None = None
    notes: str | None = Field(default=None, max_length=500)


class PickupRequestPatch(BaseModel):
    status: PickupStatus | None = None
    assigned_collector_id: uuid.UUID | None = None
    cancelled_reason: str | None = Field(default=None, max_length=500)
    version: int


# ---------- collection events ----------

class GPS(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)


class CollectionPayload(BaseModel):
    """The immutable body of an offline collection event (hashed for idempotency)."""

    model_config = ConfigDict(extra="forbid")

    collection_point_id: uuid.UUID
    waste_stream_id: uuid.UUID
    weight_kg: Decimal = Field(gt=0, le=Decimal("2000"), max_digits=10, decimal_places=3)
    measurement_source: MeasurementSource = MeasurementSource.MANUAL_ENTRY
    device_reading_id: uuid.UUID | None = None
    collected_at: datetime
    gps: GPS | None = None
    media_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=500)
    pickup_request_id: uuid.UUID | None = None
    assignment_id: uuid.UUID | None = None
    route_stop_id: uuid.UUID | None = None

    @field_validator("collected_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("collected_at must include a timezone offset")
        return v


class CollectionCreateIn(CollectionPayload):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID | None = None


class CollectionEventOut(BaseModel):
    id: uuid.UUID
    collection_point_id: uuid.UUID
    collection_point_code: str | None
    collection_point_name: str | None
    village_id: uuid.UUID
    collector_id: uuid.UUID
    collector_name: str | None
    waste_stream_id: uuid.UUID
    waste_stream_code: str | None
    weight_kg: Kg
    measurement_source: MeasurementSource
    device_reading_id: uuid.UUID | None
    calibration_meta: dict[str, Any] | None
    collected_at: datetime
    client_created_at: datetime | None
    gps_lat: float | None
    gps_lng: float | None
    gps_accuracy_m: float | None
    media_id: uuid.UUID | None
    photo_url: str | None
    notes: str | None
    offline_captured: bool
    review_status: ReviewStatus
    review_reason: str | None
    pickup_request_id: uuid.UUID | None
    facility_intake_id: uuid.UUID | None
    data_origin: DataOrigin
    created_at: datetime


class CollectionWriteOut(BaseModel):
    status: SyncReceiptStatus
    event: CollectionEventOut | None
    code: str | None = None
    message: str | None = None


class ReceiptOut(BaseModel):
    receipt_no: str
    event_id: uuid.UUID
    collection_point_code: str
    collection_point_name: str
    village_name: str | None
    stream_label: str
    weight_kg: Kg
    measurement_source: MeasurementSource
    collected_at: datetime
    acknowledged_at: datetime
    collector_name: str | None
    data_origin: DataOrigin
    review_status: ReviewStatus


class ReviewIn(BaseModel):
    review_status: Literal["resolved", "flagged"]
    note: str = Field(min_length=3, max_length=500)


class AssignmentIn(BaseModel):
    collector_id: uuid.UUID
    collection_point_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    scheduled_date: date


class AssignmentOut(ORM):
    id: uuid.UUID
    collector_id: uuid.UUID
    collection_point_id: uuid.UUID
    scheduled_date: date
    status: str
    notes: str | None
    created_at: datetime


class TaskStop(BaseModel):
    point: CollectionPointBrief
    due_reasons: list[str]
    assignment_id: uuid.UUID | None
    pickup_request_ids: list[uuid.UUID]


class MyTasksOut(BaseModel):
    date: date
    collector_id: uuid.UUID
    stops: list[TaskStop]
    points: list[CollectionPointBrief]
    streams: list[WasteStreamOut]
    generated_at: datetime


# ---------- offline sync ----------

class SyncEventIn(BaseModel):
    event_id: uuid.UUID
    type: Literal["collection"] = "collection"
    client_created_at: datetime | None = None
    payload: dict[str, Any]


class SyncBatchIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=80)
    events: list[SyncEventIn] = Field(min_length=1, max_length=100)


class SyncEventResult(BaseModel):
    event_id: uuid.UUID
    status: SyncReceiptStatus
    server_id: uuid.UUID | None = None
    code: str | None = None
    message: str | None = None
    review_status: str | None = None
    details: Any = None


class SyncBatchOut(BaseModel):
    results: list[SyncEventResult]
    server_time: datetime


class SyncReceiptOut(ORM):
    event_id: uuid.UUID
    user_id: uuid.UUID
    client_id: str | None
    event_type: str
    status: SyncReceiptStatus
    result: dict[str, Any]
    conflict_payload: dict[str, Any] | None
    conflict_count: int
    resolution: str | None
    resolved_at: datetime | None
    received_at: datetime
    last_seen_at: datetime


class ConflictResolveIn(BaseModel):
    action: Literal["keep_original", "apply_new"]
    note: str | None = Field(default=None, max_length=500)


# ---------- complaints ----------

ComplaintCategory = Literal["missed_pickup", "overflowing_bin", "damaged_bin", "staff_behaviour", "illegal_dumping", "other"]


class ComplaintOut(ORM):
    id: uuid.UUID
    village_id: uuid.UUID
    household_id: uuid.UUID | None
    raised_by: uuid.UUID
    category: str
    description: str
    collection_point_id: uuid.UUID | None
    pickup_request_id: uuid.UUID | None
    media_id: uuid.UUID | None
    photo_url: str | None = None
    status: ComplaintStatus
    assigned_to: uuid.UUID | None
    resolution_note: str | None
    resolved_at: datetime | None
    data_origin: DataOrigin
    version: int
    created_at: datetime
    updated_at: datetime


class ComplaintIn(BaseModel):
    category: ComplaintCategory
    description: str = Field(min_length=5, max_length=1000)
    collection_point_id: uuid.UUID | None = None
    pickup_request_id: uuid.UUID | None = None
    media_id: uuid.UUID | None = None
    household_id: uuid.UUID | None = None
    village_id: uuid.UUID | None = None


class ComplaintPatch(BaseModel):
    status: ComplaintStatus | None = None
    assigned_to: uuid.UUID | None = None
    resolution_note: str | None = Field(default=None, max_length=1000)
    version: int
