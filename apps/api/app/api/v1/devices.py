import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, bad_request, conflict, forbidden, not_found
from app.core.ratelimit import limiter
from app.iot.mqtt_auth import authenticate_device, provision_credentials, revoke_credentials, write_passwd_file_from_db
from app.models import Calibration, CollectionPoint, Device, DeviceReading, Village
from app.models.enums import CalibrationStatus, ConnectionStatus, DeviceType, ReadingQuality, RoleKey
from app.schemas.common import Kg, Page
from app.security.deps import DB, CurrentUser, Principal, require
from app.services.audit import audit, snapshot
from app.services.listing import PageParams, paginate
from app.services.telemetry import TelemetryIn, TelemetryRejected, ingest, record_calibration

router = APIRouter()
_NONE = {uuid.UUID(int=0)}


# ---------- schemas ----------
class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: str
    device_type: DeviceType
    firmware_version: str | None
    organization_id: uuid.UUID
    collection_point_id: uuid.UUID | None
    collection_point_code: str | None = None
    collection_point_name: str | None = None
    village_name: str | None = None
    is_simulated: bool
    connection_status: ConnectionStatus
    last_seen_at: datetime | None
    last_reading_at: datetime | None
    battery_percent: int | None
    last_weight_kg: Kg | None
    last_fill_percent: float | None
    last_sensor_status: str | None
    weight_min_kg: Kg
    weight_max_kg: Kg
    bin_depth_cm: float | None
    telemetry_interval_s: int
    calibration_status: CalibrationStatus
    last_calibration_at: datetime | None
    active: bool
    notes: str | None


class DeviceIn(BaseModel):
    device_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,39}$", description="Hardware id, e.g. DEV-ESP32-010")
    device_type: DeviceType = DeviceType.COMBO_NODE
    collection_point_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    is_simulated: bool = False
    weight_max_kg: Decimal = Field(Decimal("200"), gt=0, le=10000)
    bin_depth_cm: float | None = Field(None, gt=0, le=500)
    telemetry_interval_s: int = Field(300, ge=10, le=86400)
    notes: str | None = Field(None, max_length=500)


class DevicePatch(BaseModel):
    collection_point_id: uuid.UUID | None = None
    detach: bool = False
    weight_max_kg: Decimal | None = Field(None, gt=0, le=10000)
    bin_depth_cm: float | None = Field(None, gt=0, le=500)
    telemetry_interval_s: int | None = Field(None, ge=10, le=86400)
    active: bool | None = None
    notes: str | None = Field(None, max_length=500)


class DeviceCreated(BaseModel):
    device: DeviceOut
    device_key: str = Field(description="Shown ONCE. Store it on the device; only a hash is kept on the server.")
    mqtt_username: str
    topics: dict[str, str]


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reading_id: str
    device_timestamp: datetime
    received_at: datetime
    weight_kg: Kg | None
    fill_percent: float | None
    battery_percent: int | None
    sensor_status: str
    firmware_version: str | None
    transport: str
    quality: ReadingQuality
    quality_notes: str | None
    is_synthetic: bool


class LatestReadingOut(ReadingOut):
    device_id: str
    calibration_status: CalibrationStatus


class CalibrationIn(BaseModel):
    method: Literal["tare", "known_mass", "two_point", "factory"]
    result: Literal["pass", "fail"]
    reference_mass_kg: float | None = Field(None, gt=0, le=10000)
    scale_factor: float | None = None
    offset: float | None = None
    notes: str | None = Field(None, max_length=500)


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    performed_at: datetime
    performed_by: uuid.UUID | None
    method: str
    reference_mass_kg: Kg | None
    scale_factor: float | None
    offset: float | None
    result: str
    source: str
    notes: str | None


class CommandIn(BaseModel):
    command: Literal["tare", "calibrate", "set_interval", "reboot", "ping"]
    known_mass_kg: float | None = Field(None, gt=0, le=10000)
    interval_s: int | None = Field(None, ge=10, le=86400)


class TelemetryAck(BaseModel):
    status: Literal["accepted", "duplicate"]
    reading_id: str
    quality: ReadingQuality


def topics(device_id: str) -> dict[str, str]:
    base = f"plasticloop/devices/{device_id}"
    return {"telemetry": f"{base}/telemetry", "status": f"{base}/status", "commands": f"{base}/commands"}


# ---------- scoping ----------
def _visible_clause(principal: Principal):
    scope = principal.scope
    if scope.sees_all:
        return None
    village_ids = scope.village_ids or _NONE
    points = select(CollectionPoint.id).where(CollectionPoint.village_id.in_(village_ids))
    return or_(Device.collection_point_id.in_(points),
               Device.collection_point_id.is_(None) & Device.organization_id.in_(scope.org_ids or _NONE))


def _get_visible(db: Session, device_pk: uuid.UUID, principal: Principal) -> Device:
    stmt = select(Device).where(Device.id == device_pk, Device.deleted_at.is_(None))
    clause = _visible_clause(principal)
    if clause is not None:
        stmt = stmt.where(clause)
    device = db.scalar(stmt)
    if device is None:
        raise not_found("Device")
    return device


def _serialize(db: Session, devices: list[Device]) -> list[DeviceOut]:
    cp_ids = {d.collection_point_id for d in devices if d.collection_point_id}
    cps = {}
    if cp_ids:
        rows = db.execute(
            select(CollectionPoint.id, CollectionPoint.code, CollectionPoint.name, Village.name)
            .join(Village, Village.id == CollectionPoint.village_id).where(CollectionPoint.id.in_(cp_ids))
        ).all()
        cps = {r[0]: r[1:] for r in rows}
    out = []
    for d in devices:
        o = DeviceOut.model_validate(d)
        if d.collection_point_id in cps:
            o.collection_point_code, o.collection_point_name, o.village_name = cps[d.collection_point_id]
        out.append(o)
    return out


def _attach_point(db: Session, principal: Principal, device: Device, cp_id: uuid.UUID) -> None:
    cp = db.get(CollectionPoint, cp_id)
    if cp is None or cp.deleted_at is not None:
        raise not_found("Collection point")
    principal.scope.ensure_village(cp.village_id, "Collection point")
    taken = db.scalar(select(Device.device_id).where(Device.collection_point_id == cp_id, Device.id != device.id,
                                                     Device.deleted_at.is_(None)))
    if taken:
        raise conflict("POINT_HAS_DEVICE", f"{cp.code} already has device {taken}")
    device.collection_point_id = cp_id


def _sync_broker_credentials(db: Session) -> None:
    try:
        write_passwd_file_from_db(db)
    except OSError as exc:  # broker file is best-effort; HTTPS ingestion keeps working
        from app.core.logging import get_logger

        get_logger("app.devices").warning("mqtt_passwd_write_failed", extra={"fields": {"error": str(exc)}})


# ---------- device ingestion (device credentials, not user JWT) ----------
@router.post("/telemetry", response_model=TelemetryAck, summary="HTTPS telemetry from a device",
             description="Header `Authorization: Device <device_id>:<device_key>`. Idempotent on `reading_id`.")
def post_telemetry(body: TelemetryIn, request: Request, db: DB, authorization: str = Header(...)):
    scheme, _, cred = authorization.partition(" ")
    device_id, _, key = cred.partition(":")
    if scheme != "Device" or not device_id or not key:
        raise AppError(401, "DEVICE_AUTH_REQUIRED", "Use 'Authorization: Device <device_id>:<device_key>'")
    limiter.check(f"telemetry:{device_id[:40]}", 120, 60)
    device = authenticate_device(db, device_id, key)
    if device is None:
        raise AppError(401, "DEVICE_AUTH_FAILED", "Unknown device or invalid key")
    try:
        reading, duplicate = ingest(db, device, body, transport="https")
    except TelemetryRejected as exc:
        raise bad_request("TELEMETRY_REJECTED", str(exc)) from exc
    db.commit()
    return TelemetryAck(status="duplicate" if duplicate else "accepted", reading_id=reading.reading_id, quality=reading.quality)


# ---------- user endpoints ----------
@router.get("", response_model=Page[DeviceOut])
def list_devices(db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR)),
                 params: PageParams = Depends(), status: ConnectionStatus | None = None, simulated: bool | None = None,
                 q: str | None = None):
    stmt = select(Device).where(Device.deleted_at.is_(None))
    clause = _visible_clause(principal)
    if clause is not None:
        stmt = stmt.where(clause)
    if status:
        stmt = stmt.where(Device.connection_status == status)
    if simulated is not None:
        stmt = stmt.where(Device.is_simulated.is_(simulated))
    if q:
        stmt = stmt.where(Device.device_id.ilike(f"%{q.strip()[:40]}%"))
    page = paginate(db, stmt, params, {"device_id": Device.device_id, "last_seen": Device.last_seen_at,
                                       "battery": Device.battery_percent, "status": Device.connection_status}, "device_id")
    page["items"] = _serialize(db, page["items"])
    return page


@router.get("/latest-reading", response_model=LatestReadingOut, summary="Latest OK reading for the collector 'read scale' button")
def latest_reading(device_id: str, db: DB, principal: CurrentUser):
    device = db.scalar(select(Device).where(Device.device_id == device_id, Device.deleted_at.is_(None)))
    if device is None:
        raise not_found("Device")
    _get_visible(db, device.id, principal)
    reading = db.scalar(
        select(DeviceReading)
        .where(DeviceReading.device_pk == device.id, DeviceReading.quality == ReadingQuality.OK,
               DeviceReading.weight_kg.is_not(None))
        .order_by(DeviceReading.device_timestamp.desc()).limit(1)
    )
    if reading is None:
        raise not_found("Reading")
    return LatestReadingOut(**ReadingOut.model_validate(reading).model_dump(), device_id=device.device_id,
                            calibration_status=device.calibration_status)


@router.get("/{device_pk}", response_model=DeviceOut)
def get_device(device_pk: uuid.UUID, db: DB,
               principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR))):
    return _serialize(db, [_get_visible(db, device_pk, principal)])[0]


@router.post("", response_model=DeviceCreated, status_code=201, summary="Register a device and provision its key (shown once)")
def create_device(body: DeviceIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    if db.scalar(select(Device.id).where(Device.device_id == body.device_id)):
        raise conflict("DEVICE_EXISTS", f"Device {body.device_id} is already registered")
    if body.is_simulated and not settings.demo_enabled:
        raise bad_request("SIMULATION_DISABLED", "Simulated devices can only be registered in demo mode")
    org_id = body.organization_id
    if body.collection_point_id:
        cp = db.get(CollectionPoint, body.collection_point_id)
        if cp is None:
            raise not_found("Collection point")
        org_id = db.get(Village, cp.village_id).organization_id
    if org_id is None:
        if len(principal.scope.org_ids) != 1:
            raise bad_request("ORGANIZATION_REQUIRED", "Choose a collection point or organisation for this device")
        org_id = next(iter(principal.scope.org_ids))
    principal.scope.ensure_org(org_id, "Organisation")
    device = Device(device_id=body.device_id, device_type=body.device_type, organization_id=org_id,
                    is_simulated=body.is_simulated, weight_max_kg=body.weight_max_kg, bin_depth_cm=body.bin_depth_cm,
                    telemetry_interval_s=body.telemetry_interval_s, notes=body.notes)
    db.add(device)
    db.flush()
    if body.collection_point_id:
        _attach_point(db, principal, device, body.collection_point_id)
    key = provision_credentials(db, device, principal.id)
    audit(db, principal, "device.registered", "device", device.id, after=snapshot(device, "device_id", "collection_point_id"))
    db.commit()
    _sync_broker_credentials(db)
    db.refresh(device)
    return DeviceCreated(device=_serialize(db, [device])[0], device_key=key, mqtt_username=device.device_id,
                         topics=topics(device.device_id))


@router.patch("/{device_pk}", response_model=DeviceOut)
def update_device(device_pk: uuid.UUID, body: DevicePatch, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    device = _get_visible(db, device_pk, principal)
    before = snapshot(device, "collection_point_id", "active", "weight_max_kg", "telemetry_interval_s")
    if body.detach:
        device.collection_point_id = None
    elif body.collection_point_id:
        _attach_point(db, principal, device, body.collection_point_id)
    for field in ("weight_max_kg", "bin_depth_cm", "telemetry_interval_s", "notes"):
        value = getattr(body, field)
        if value is not None:
            setattr(device, field, value)
    deactivated = body.active is False and device.active
    if body.active is not None:
        device.active = body.active
    audit(db, principal, "device.updated", "device", device.id, before=before,
          after=snapshot(device, "collection_point_id", "active", "weight_max_kg", "telemetry_interval_s"))
    db.commit()
    if deactivated or body.active:
        _sync_broker_credentials(db)
    db.refresh(device)
    return _serialize(db, [device])[0]


@router.post("/{device_pk}/rotate-key", response_model=DeviceCreated, summary="Issue a new key; the old one stops working")
def rotate_key(device_pk: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    device = _get_visible(db, device_pk, principal)
    key = provision_credentials(db, device, principal.id)
    audit(db, principal, "device.key_rotated", "device", device.id)
    db.commit()
    _sync_broker_credentials(db)
    return DeviceCreated(device=_serialize(db, [device])[0], device_key=key, mqtt_username=device.device_id,
                         topics=topics(device.device_id))


@router.post("/{device_pk}/revoke", response_model=DeviceOut, summary="Revoke all credentials (device can no longer connect)")
def revoke(device_pk: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    device = _get_visible(db, device_pk, principal)
    revoke_credentials(db, device)
    device.connection_status = ConnectionStatus.OFFLINE
    audit(db, principal, "device.revoked", "device", device.id)
    db.commit()
    _sync_broker_credentials(db)
    db.refresh(device)
    return _serialize(db, [device])[0]


@router.get("/{device_pk}/readings", response_model=Page[ReadingOut])
def readings(device_pk: uuid.UUID, db: DB, params: PageParams = Depends(), quality: ReadingQuality | None = None,
             since: datetime | None = None,
             principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR))):
    device = _get_visible(db, device_pk, principal)
    stmt = select(DeviceReading).where(DeviceReading.device_pk == device.id)
    if quality:
        stmt = stmt.where(DeviceReading.quality == quality)
    if since:
        stmt = stmt.where(DeviceReading.device_timestamp >= since)
    return paginate(db, stmt, params, {"time": DeviceReading.device_timestamp, "received": DeviceReading.received_at}, "-time")


@router.get("/{device_pk}/calibrations", response_model=list[CalibrationOut])
def calibrations(device_pk: uuid.UUID, db: DB,
                 principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR))):
    device = _get_visible(db, device_pk, principal)
    return db.scalars(select(Calibration).where(Calibration.device_pk == device.id).order_by(Calibration.performed_at.desc()).limit(50)).all()


@router.post("/{device_pk}/calibrations", response_model=CalibrationOut, status_code=201, summary="Record a manual calibration")
def add_calibration(device_pk: uuid.UUID, body: CalibrationIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    device = _get_visible(db, device_pk, principal)
    if body.method in ("known_mass", "two_point") and body.reference_mass_kg is None:
        raise bad_request("REFERENCE_MASS_REQUIRED", "Known-mass calibration needs the reference mass")
    cal = record_calibration(db, device, method=body.method, result=body.result, reference_mass_kg=body.reference_mass_kg,
                             scale_factor=body.scale_factor, offset=body.offset, actor_id=principal.id, notes=body.notes)
    audit(db, principal, "device.calibrated", "device", device.id, after={"method": body.method, "result": body.result})
    db.commit()
    db.refresh(cal)
    return cal


@router.post("/{device_pk}/commands", summary="Send a command over MQTT (tare, calibrate, set_interval, reboot, ping)")
def send_command(device_pk: uuid.UUID, body: CommandIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    device = _get_visible(db, device_pk, principal)
    if not device.active:
        raise forbidden("Device is deactivated")
    if body.command == "calibrate" and body.known_mass_kg is None:
        raise bad_request("KNOWN_MASS_REQUIRED", "calibrate needs known_mass_kg")
    if body.command == "set_interval" and body.interval_s is None:
        raise bad_request("INTERVAL_REQUIRED", "set_interval needs interval_s")
    command_id = str(uuid.uuid4())
    message = {"command_id": command_id, "command": body.command}
    if body.known_mass_kg is not None:
        message["known_mass_kg"] = body.known_mass_kg
    if body.interval_s is not None:
        message["interval_s"] = body.interval_s
    try:
        from paho.mqtt import publish

        publish.single(topics(device.device_id)["commands"], json.dumps(message), qos=1, hostname=settings.mqtt_host,
                       port=settings.mqtt_port, client_id=f"plasticloop-api-{command_id[:8]}",
                       auth={"username": settings.mqtt_service_user, "password": settings.mqtt_service_password})
    except (OSError, ValueError) as exc:
        raise AppError(503, "MQTT_UNAVAILABLE", "Message broker is not reachable; the command was not sent") from exc
    if body.command == "set_interval":
        device.telemetry_interval_s = body.interval_s
    audit(db, principal, f"device.command.{body.command}", "device", device.id, after=message)
    db.commit()
    return {"status": "sent", "command_id": command_id, "topic": topics(device.device_id)["commands"],
            "note": "Delivery is confirmed only when the device reports back on its status topic."}
