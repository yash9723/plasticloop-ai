"""Recording a weighed collection. Shared by the online endpoint, offline sync and demo steps."""

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    CollectionAssignment,
    CollectionEvent,
    CollectionPoint,
    Device,
    DeviceReading,
    PickupRequest,
    RouteStop,
    User,
    WasteStream,
)
from app.models.enums import (
    AssignmentStatus,
    DataOrigin,
    MeasurementSource,
    PickupStatus,
    PointStatus,
    ReviewStatus,
    RoleKey,
    Severity,
    StopStatus,
)
from app.schemas.collection import CollectionEventOut, CollectionPayload
from app.security.deps import Principal
from app.security.tokens import utcnow
from app.services import system_settings
from app.services.media import signed_url
from app.services.notifications import notify, village_admins

FUTURE_SKEW = timedelta(minutes=10)
OLD_EVENT = timedelta(days=30)
READING_MATCH_TOLERANCE_KG = Decimal("0.05")


class CollectionRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def payload_hash(event_type: str, payload: dict) -> str:
    canonical = json.dumps({"type": event_type, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_collection(
    db: Session,
    actor: Principal,
    event_id: uuid.UUID,
    payload: CollectionPayload,
    *,
    client_created_at: datetime | None = None,
    offline_captured: bool = False,
    origin: DataOrigin | None = None,
) -> CollectionEvent:
    """Validates and inserts one collection event plus its side effects. Raises CollectionRejected."""
    now = utcnow()
    cp = db.get(CollectionPoint, payload.collection_point_id)
    if cp is None or cp.deleted_at is not None:
        raise CollectionRejected("UNKNOWN_COLLECTION_POINT", "Collection point not found")
    if not actor.scope.can_village(cp.village_id):
        raise CollectionRejected("OUT_OF_SCOPE", "This collection point is outside your assigned villages")
    stream = db.get(WasteStream, payload.waste_stream_id)
    if stream is None or not stream.active:
        raise CollectionRejected("UNKNOWN_STREAM", "Waste stream not found or inactive")
    if payload.collected_at > now + FUTURE_SKEW:
        raise CollectionRejected("FUTURE_TIMESTAMP", "Collection time is in the future; check the phone clock")

    device = db.scalar(select(Device).where(Device.collection_point_id == cp.id, Device.deleted_at.is_(None)))
    max_kg = Decimal(str(device.weight_max_kg)) if device else Decimal(str(system_settings.get_value(db, "max_collection_weight_kg")))
    if payload.weight_kg > max_kg:
        raise CollectionRejected("WEIGHT_OUT_OF_RANGE", f"Weight exceeds the allowed maximum of {max_kg} kg for this point")

    # --- measurement provenance: never silently promote simulated or manual values to "measured" ---
    source = payload.measurement_source
    calibration = None
    simulated = False
    if payload.device_reading_id:
        reading = db.get(DeviceReading, payload.device_reading_id)
        if reading is None or device is None or reading.device_pk != device.id:
            raise CollectionRejected("READING_MISMATCH", "Scale reading does not belong to this collection point's device")
        if reading.weight_kg is None or abs(Decimal(str(reading.weight_kg)) - payload.weight_kg) > READING_MATCH_TOLERANCE_KG:
            raise CollectionRejected("READING_WEIGHT_MISMATCH", "Entered weight differs from the attached scale reading")
        simulated = reading.is_synthetic or device.is_simulated
        source = MeasurementSource.SIMULATED_SENSOR if simulated else MeasurementSource.DEVICE_MEASURED
        calibration = {
            "device_id": device.device_id,
            "calibration_status": device.calibration_status,
            "last_calibration_at": device.last_calibration_at.isoformat() if device.last_calibration_at else None,
            "reading_quality": reading.quality,
        }
    elif source == MeasurementSource.DEVICE_MEASURED:
        raise CollectionRejected("DEVICE_READING_REQUIRED", "A device-measured weight must reference the scale reading")
    elif source == MeasurementSource.SIMULATED_SENSOR:
        if not settings.demo_enabled:
            raise CollectionRejected("SIMULATION_DISABLED", "Simulated measurements are only accepted in demo mode")
        simulated = True

    flags: list[str] = []
    if cp.status != PointStatus.ACTIVE:
        flags.append("Collection point is inactive")
    if stream.id not in {s.id for s in cp.streams}:
        flags.append(f"Stream '{stream.code}' is not configured for this point")
    if RoleKey.COLLECTOR in actor.scope.roles and cp.assigned_collector_id not in (None, actor.id):
        flags.append("Recorded by a collector not assigned to this point")
    if payload.collected_at < now - OLD_EVENT:
        flags.append("Collection time is more than 30 days old")

    if origin is None:
        origin = DataOrigin.SIMULATED if simulated else (DataOrigin.DEMO_SEED if cp.is_sample else DataOrigin.LIVE)

    payload_json = payload.model_dump(mode="json")
    event = CollectionEvent(
        id=event_id,
        idempotency_key=str(event_id),
        collection_point_id=cp.id,
        village_id=cp.village_id,
        collector_id=actor.id,
        waste_stream_id=stream.id,
        weight_kg=payload.weight_kg,
        measurement_source=source,
        device_reading_id=payload.device_reading_id,
        calibration_meta=calibration,
        collected_at=payload.collected_at,
        client_created_at=client_created_at,
        gps_lat=payload.gps.lat if payload.gps else None,
        gps_lng=payload.gps.lng if payload.gps else None,
        gps_accuracy_m=payload.gps.accuracy_m if payload.gps else None,
        media_id=payload.media_id,
        notes=payload.notes,
        offline_captured=offline_captured,
        review_status=ReviewStatus.FLAGGED if flags else ReviewStatus.OK,
        review_reason="; ".join(flags) or None,
        pickup_request_id=payload.pickup_request_id,
        assignment_id=payload.assignment_id,
        data_origin=origin,
        payload_hash=payload_hash("collection", payload_json),
    )
    db.add(event)
    db.flush()

    # Side effects use Core UPDATEs so concurrent collectors don't trip optimistic locks on the point.
    db.execute(
        update(CollectionPoint)
        .where(CollectionPoint.id == cp.id)
        .values(
            last_collected_at=func.greatest(func.coalesce(CollectionPoint.last_collected_at, payload.collected_at), payload.collected_at),
            fill_percent=0,
            fill_source="collection",
            fill_updated_at=now,
        )
    )
    if payload.pickup_request_id:
        db.execute(
            update(PickupRequest)
            .where(
                PickupRequest.id == payload.pickup_request_id,
                PickupRequest.village_id == cp.village_id,
                PickupRequest.status.notin_([PickupStatus.CANCELLED, PickupStatus.COMPLETED]),
            )
            .values(status=PickupStatus.COMPLETED, completed_at=now, version=PickupRequest.version + 1)
        )
    if payload.assignment_id:
        db.execute(
            update(CollectionAssignment)
            .where(CollectionAssignment.id == payload.assignment_id, CollectionAssignment.collection_point_id == cp.id)
            .values(status=AssignmentStatus.COMPLETED)
        )
    if payload.route_stop_id:
        db.execute(
            update(RouteStop)
            .where(RouteStop.id == payload.route_stop_id, RouteStop.collection_point_id == cp.id)
            .values(status=StopStatus.COMPLETED, completed_at=now, collection_event_id=event.id)
        )
    if flags:
        notify(
            db,
            village_admins(db, cp.village_id),
            type="collection_flagged",
            title=f"Collection at {cp.code} needs review",
            body="; ".join(flags),
            severity=Severity.WARNING,
            entity_type="collection_event",
            entity_id=event.id,
            link=f"/collections/{event.id}",
            dedupe_key=f"collection_flagged:{event.id}",
        )
    return event


def serialize_events(db: Session, events: Sequence[CollectionEvent]) -> list[CollectionEventOut]:
    if not events:
        return []
    cps = {
        c.id: c
        for c in db.scalars(select(CollectionPoint).where(CollectionPoint.id.in_({e.collection_point_id for e in events})))
    }
    users = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({e.collector_id for e in events}))).all())
    streams = dict(
        db.execute(select(WasteStream.id, WasteStream.code).where(WasteStream.id.in_({e.waste_stream_id for e in events}))).all()
    )
    out = []
    for e in events:
        cp = cps.get(e.collection_point_id)
        out.append(
            CollectionEventOut(
                id=e.id,
                collection_point_id=e.collection_point_id,
                collection_point_code=cp.code if cp else None,
                collection_point_name=cp.name if cp else None,
                village_id=e.village_id,
                collector_id=e.collector_id,
                collector_name=users.get(e.collector_id),
                waste_stream_id=e.waste_stream_id,
                waste_stream_code=streams.get(e.waste_stream_id),
                weight_kg=e.weight_kg,
                measurement_source=e.measurement_source,
                device_reading_id=e.device_reading_id,
                calibration_meta=e.calibration_meta,
                collected_at=e.collected_at,
                client_created_at=e.client_created_at,
                gps_lat=e.gps_lat,
                gps_lng=e.gps_lng,
                gps_accuracy_m=e.gps_accuracy_m,
                media_id=e.media_id,
                photo_url=signed_url(e.media_id),
                notes=e.notes,
                offline_captured=e.offline_captured,
                review_status=e.review_status,
                review_reason=e.review_reason,
                pickup_request_id=e.pickup_request_id,
                facility_intake_id=e.facility_intake_id,
                data_origin=e.data_origin,
                created_at=e.created_at,
            )
        )
    return out
