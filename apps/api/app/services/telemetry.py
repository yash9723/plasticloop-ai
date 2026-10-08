"""Device telemetry ingestion shared by HTTPS, MQTT (worker) and the demo simulator.

Every reading is stored (even bad ones) with a quality flag; only `ok` readings update bin fill levels.
Simulated devices always produce `is_synthetic=True` readings regardless of what the payload claims.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Calibration, CollectionPoint, Device, DeviceReading
from app.models.enums import CalibrationStatus, ConnectionStatus, ReadingQuality, Severity
from app.security.tokens import utcnow
from app.services import system_settings
from app.services.notifications import notify, village_admins

log = get_logger("app.telemetry")
FUTURE_SKEW = timedelta(minutes=5)
MAX_AGE = timedelta(days=7)
NEGATIVE_DRIFT_KG = Decimal("-0.5")
EVENT_CHANNEL = "plasticloop_events"


class TelemetryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(min_length=3, max_length=40)
    reading_id: str = Field(min_length=1, max_length=64)
    timestamp: AwareDatetime
    weight_kg: float | None = Field(None, ge=-1000, le=100000)
    fill_percent: float | None = Field(None, ge=0, le=100)
    battery_percent: int | None = Field(None, ge=0, le=100)
    sensor_status: str = Field("ok", max_length=40)
    firmware_version: str | None = Field(None, max_length=20)
    synthetic: bool = False


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = Field(None, max_length=20)  # online | offline (LWT)
    type: str | None = Field(None, max_length=30)  # calibration_result | command_ack
    command: str | None = Field(None, max_length=30)
    result: str | None = Field(None, max_length=10)
    reference_mass_kg: float | None = None
    scale_factor: float | None = None
    offset: float | None = None
    firmware_version: str | None = Field(None, max_length=20)


def publish_event(db: Session, kind: str, **data) -> None:
    """Postgres NOTIFY, delivered on commit to /events/stream listeners."""
    payload = json.dumps({"kind": kind, **{k: str(v) if v is not None else None for k, v in data.items()}})
    db.execute(text("SELECT pg_notify(:c, :p)"), {"c": EVENT_CHANNEL, "p": payload})


def assess_quality(device: Device, data: TelemetryIn, now: datetime) -> tuple[ReadingQuality, str | None]:
    if data.sensor_status.lower() not in ("ok", "online"):
        return ReadingQuality.SENSOR_ERROR, f"Device reported sensor status '{data.sensor_status}'"
    if data.timestamp > now + FUTURE_SKEW or data.timestamp < now - MAX_AGE:
        return ReadingQuality.CLOCK_SKEW, "Device timestamp is far from server time; check NTP"
    if data.weight_kg is not None:
        w = Decimal(str(data.weight_kg))
        if w < NEGATIVE_DRIFT_KG:
            return ReadingQuality.NEGATIVE_DRIFT, "Negative weight: scale needs tare/calibration"
        if w > Decimal(str(device.weight_max_kg)) or w < Decimal(str(device.weight_min_kg)) + NEGATIVE_DRIFT_KG:
            return ReadingQuality.OUT_OF_RANGE, f"Weight outside {device.weight_min_kg}-{device.weight_max_kg} kg"
    return ReadingQuality.OK, None


class TelemetryRejected(ValueError):
    pass


def village_of(db: Session, device: Device):
    return db.scalar(select(CollectionPoint.village_id).where(CollectionPoint.id == device.collection_point_id))         if device.collection_point_id else None


def ingest(db: Session, device: Device, data: TelemetryIn, transport: str) -> tuple[DeviceReading, bool]:
    """Returns (reading, duplicate). Caller commits."""
    if data.device_id != device.device_id:
        raise TelemetryRejected("device_id in payload does not match the authenticated device")
    existing = db.scalar(
        select(DeviceReading).where(DeviceReading.device_pk == device.id, DeviceReading.reading_id == data.reading_id)
    )
    if existing:
        return existing, True

    now = utcnow()
    quality, notes = assess_quality(device, data, now)
    synthetic = data.synthetic or device.is_simulated
    reading = DeviceReading(
        device_pk=device.id,
        reading_id=data.reading_id,
        device_timestamp=data.timestamp,
        weight_kg=Decimal(str(round(data.weight_kg, 3))) if data.weight_kg is not None else None,
        fill_percent=Decimal(str(round(data.fill_percent, 1))) if data.fill_percent is not None else None,
        battery_percent=data.battery_percent,
        sensor_status=data.sensor_status,
        firmware_version=data.firmware_version,
        transport=transport,
        quality=quality,
        quality_notes=notes,
        is_synthetic=synthetic,
        raw=data.model_dump(mode="json"),
    )
    try:
        with db.begin_nested():
            db.add(reading)
            db.flush()
    except IntegrityError:  # concurrent duplicate (same reading over MQTT and HTTPS retry)
        return db.scalar(
            select(DeviceReading).where(DeviceReading.device_pk == device.id, DeviceReading.reading_id == data.reading_id)
        ), True

    device.last_seen_at = now
    device.connection_status = ConnectionStatus.ONLINE
    if device.last_reading_at is None or data.timestamp >= device.last_reading_at:
        device.last_reading_at = data.timestamp
        device.battery_percent = data.battery_percent if data.battery_percent is not None else device.battery_percent
        device.last_sensor_status = data.sensor_status
        if data.firmware_version:
            device.firmware_version = data.firmware_version
        if quality == ReadingQuality.OK:
            if data.weight_kg is not None:
                device.last_weight_kg = reading.weight_kg
            if data.fill_percent is not None:
                device.last_fill_percent = reading.fill_percent
    _update_point_and_alert(db, device, reading)
    publish_event(db, "telemetry", device_id=device.device_id, device_pk=device.id, quality=quality,
                  village_id=village_of(db, device))
    return reading, False


def _update_point_and_alert(db: Session, device: Device, reading: DeviceReading) -> None:
    cp = db.get(CollectionPoint, device.collection_point_id) if device.collection_point_id else None
    tag = " (SIMULATED)" if reading.is_synthetic else ""
    admins = village_admins(db, cp.village_id) if cp else []
    if reading.quality == ReadingQuality.OK and cp and reading.fill_percent is not None:
        cp.fill_percent = reading.fill_percent
        cp.fill_source = "simulated_sensor" if reading.is_synthetic else "device"
        cp.fill_updated_at = reading.device_timestamp
        if reading.fill_percent >= Decimal(str(system_settings.get_value(db, "fill_alert_percent"))):
            notify(db, [*admins, cp.assigned_collector_id], type="bin_fill_alert", severity=Severity.WARNING,
                   title=f"{cp.code} is {reading.fill_percent}% full{tag}", body=f"Reported by {device.device_id}.",
                   entity_type="collection_point", entity_id=cp.id, link=f"/collection-points/{cp.id}",
                   dedupe_key=f"fill:{cp.id}", cooldown_minutes=240)
    if reading.battery_percent is not None and reading.battery_percent <= system_settings.get_value(db, "low_battery_percent"):
        notify(db, admins, type="device_low_battery", severity=Severity.WARNING,
               title=f"{device.device_id} battery at {reading.battery_percent}%{tag}",
               entity_type="device", entity_id=device.id, link=f"/devices/{device.id}",
               dedupe_key=f"battery:{device.id}", cooldown_minutes=720)
    if reading.quality != ReadingQuality.OK:
        notify(db, admins, type="device_anomaly", severity=Severity.WARNING,
               title=f"{device.device_id}: {reading.quality.replace('_', ' ')}{tag}", body=reading.quality_notes,
               entity_type="device", entity_id=device.id, link=f"/devices/{device.id}",
               dedupe_key=f"anomaly:{device.id}:{reading.quality}", cooldown_minutes=120)


def handle_status(db: Session, device: Device, data: StatusIn) -> None:
    """MQTT status topic: online/offline (incl. broker LWT) and command results reported by the device."""
    now = utcnow()
    if data.status == "offline":
        device.connection_status = ConnectionStatus.OFFLINE
    elif data.status == "online":
        device.connection_status = ConnectionStatus.ONLINE
        device.last_seen_at = now
    if data.firmware_version:
        device.firmware_version = data.firmware_version
    if data.type == "calibration_result" and data.result in ("pass", "fail"):
        record_calibration(db, device, method="known_mass" if data.reference_mass_kg else "tare", result=data.result,
                           reference_mass_kg=data.reference_mass_kg, scale_factor=data.scale_factor, offset=data.offset,
                           source="device_command", actor_id=None)
    publish_event(db, "device_status", device_id=device.device_id, device_pk=device.id, status=device.connection_status,
                  village_id=village_of(db, device))


def record_calibration(db: Session, device: Device, *, method: str, result: str, reference_mass_kg=None, scale_factor=None,
                       offset=None, source: str = "manual", actor_id=None, notes: str | None = None) -> Calibration:
    cal = Calibration(device_pk=device.id, method=method, result=result, source=source, performed_by=actor_id, notes=notes,
                      reference_mass_kg=Decimal(str(reference_mass_kg)) if reference_mass_kg is not None else None,
                      scale_factor=scale_factor, offset=offset)
    db.add(cal)
    device.calibration_status = CalibrationStatus.CALIBRATED if result == "pass" else CalibrationStatus.FAILED
    device.last_calibration_at = utcnow() if result == "pass" else device.last_calibration_at
    db.flush()
    return cal


def refresh_connection_states(db: Session) -> dict[str, int]:
    """Worker tick: online → stale (half the timeout) → offline. Notifies admins once per outage."""
    timeout = timedelta(minutes=int(system_settings.get_value(db, "device_offline_after_minutes")))
    now = utcnow()
    changed = {"stale": 0, "offline": 0}
    devices = db.scalars(
        select(Device).where(Device.deleted_at.is_(None), Device.active.is_(True), Device.last_seen_at.is_not(None),
                             Device.connection_status.in_([ConnectionStatus.ONLINE, ConnectionStatus.STALE]))
    )
    for d in devices:
        age = now - d.last_seen_at
        if age >= timeout:
            d.connection_status = ConnectionStatus.OFFLINE
            changed["offline"] += 1
            cp = db.get(CollectionPoint, d.collection_point_id) if d.collection_point_id else None
            if cp:
                notify(db, village_admins(db, cp.village_id), type="device_offline", severity=Severity.WARNING,
                       title=f"{d.device_id} is offline{' (SIMULATED)' if d.is_simulated else ''}",
                       body=f"No telemetry for {int(age.total_seconds() // 60)} minutes.", entity_type="device",
                       entity_id=d.id, link=f"/devices/{d.id}", dedupe_key=f"offline:{d.id}", cooldown_minutes=720)
            publish_event(db, "device_status", device_id=d.device_id, device_pk=d.id, status=d.connection_status,
                          village_id=cp.village_id if cp else None)
        elif age >= timeout / 2 and d.connection_status == ConnectionStatus.ONLINE:
            d.connection_status = ConnectionStatus.STALE
            changed["stale"] += 1
    return changed
