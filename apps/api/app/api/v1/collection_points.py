import secrets
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.db.base import Geography
from app.models import (
    CollectionEvent,
    CollectionPoint,
    Device,
    Household,
    PickupRequest,
    User,
    UserMembership,
    Village,
    WasteStream,
)
from app.models.enums import PickupStatus, PointStatus, RoleKey
from app.schemas.collection import (
    CollectionPointBrief,
    CollectionPointIn,
    CollectionPointOut,
    CollectionPointPatch,
    DeviceBrief,
    PickupRequestOut,
)
from app.schemas.common import Page
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.scope import AccessScope
from app.services.audit import audit, snapshot
from app.services.collections import serialize_events
from app.services.listing import PageParams, paginate

router = APIRouter()
_NONE = {uuid.UUID(int=0)}
SORTS = {
    "code": CollectionPoint.code,
    "name": CollectionPoint.name,
    "fill": CollectionPoint.fill_percent,
    "last_collected": CollectionPoint.last_collected_at,
    "priority": CollectionPoint.priority,
}


def visible_clause(scope: AccessScope):
    if scope.sees_all:
        return true()
    return CollectionPoint.village_id.in_(scope.village_ids | scope.household_village_ids or _NONE)


def _precise(scope: AccessScope) -> bool:
    return scope.has(RoleKey.GP_ADMIN, RoleKey.COLLECTOR, RoleKey.DRIVER, RoleKey.MRF_OPERATOR)


def serialize_points(db: Session, points: Sequence[CollectionPoint], scope: AccessScope) -> list[CollectionPointOut]:
    if not points:
        return []
    ids = [p.id for p in points]
    devices = {
        d.collection_point_id: d
        for d in db.scalars(select(Device).where(Device.collection_point_id.in_(ids), Device.deleted_at.is_(None)))
    }
    collector_ids = {p.assigned_collector_id for p in points if p.assigned_collector_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(collector_ids))).all()) if collector_ids else {}
    villages = dict(db.execute(select(Village.id, Village.name).where(Village.id.in_({p.village_id for p in points}))).all())
    precise = _precise(scope)
    out = []
    for p in points:
        lat, lng, precision = p.lat, p.lng, "exact"
        # Household-type points sit at homes: only field staff see exact coordinates.
        if not precise and p.point_type == "household" and lat is not None:
            lat, lng, precision = round(lat, 3), round(lng, 3), "approximate"
        d = devices.get(p.id)
        out.append(
            CollectionPointOut(
                id=p.id,
                code=p.code,
                qr_code=p.qr_code,
                name=p.name,
                point_type=p.point_type,
                village_id=p.village_id,
                village_name=villages.get(p.village_id),
                household_id=p.household_id if precise else None,
                lat=lat,
                lng=lng,
                location_precision=precision,
                assigned_collector_id=p.assigned_collector_id,
                assigned_collector_name=names.get(p.assigned_collector_id),
                pickup_days=p.pickup_days or [],
                pickup_window=p.pickup_window,
                bin_capacity_kg=p.bin_capacity_kg,
                fill_percent=float(p.fill_percent) if p.fill_percent is not None else None,
                fill_source=p.fill_source,
                fill_updated_at=p.fill_updated_at,
                last_collected_at=p.last_collected_at,
                priority=p.priority,
                emergency_flag=p.emergency_flag,
                status=p.status,
                version=p.version,
                is_sample=p.is_sample,
                stream_ids=[s.id for s in p.streams],
                device=DeviceBrief(
                    id=d.id,
                    device_id=d.device_id,
                    connection_status=d.connection_status,
                    last_seen_at=d.last_seen_at,
                    battery_percent=d.battery_percent,
                    is_simulated=d.is_simulated,
                )
                if d
                else None,
            )
        )
    return out


def brief(p: CollectionPointOut) -> CollectionPointBrief:
    return CollectionPointBrief(
        **p.model_dump(include=set(CollectionPointBrief.model_fields) - {"device_id"}),
        device_id=p.device.device_id if p.device else None,
    )


def _get_visible(db: Session, point_id: uuid.UUID, scope: AccessScope) -> CollectionPoint:
    cp = db.get(CollectionPoint, point_id)
    if cp is None or cp.deleted_at is not None:
        raise not_found("Collection point")
    if cp.village_id not in scope.household_village_ids:
        scope.ensure_village(cp.village_id, "Collection point")
    return cp


def _validate_collector(db: Session, village: Village, collector_id: uuid.UUID | None) -> None:
    if collector_id is None:
        return
    ok = db.scalar(
        select(UserMembership.id).where(
            UserMembership.user_id == collector_id,
            UserMembership.organization_id == village.organization_id,
            UserMembership.role_key == RoleKey.COLLECTOR,
            or_(UserMembership.village_id.is_(None), UserMembership.village_id == village.id),
        )
    )
    if not ok:
        raise bad_request("INVALID_COLLECTOR", "Assigned user is not a collector for this village")


def _streams(db: Session, ids: list[uuid.UUID]) -> list[WasteStream]:
    streams = db.scalars(select(WasteStream).where(WasteStream.id.in_(ids), WasteStream.active.is_(True))).all()
    if len(streams) != len(set(ids)):
        raise bad_request("UNKNOWN_STREAM", "One or more waste streams are unknown or inactive")
    return list(streams)


def new_qr_code() -> str:
    return "PL" + secrets.token_hex(5).upper()


@router.get("", response_model=Page[CollectionPointOut])
def list_points(
    db: DB,
    principal: CurrentUser,
    params: PageParams = Depends(),
    village_id: uuid.UUID | None = None,
    status: PointStatus | None = None,
    collector_id: uuid.UUID | None = None,
    stream_id: uuid.UUID | None = None,
    min_fill: float | None = Query(None, ge=0, le=100),
    q: str | None = Query(None, max_length=80),
):
    stmt = select(CollectionPoint).where(CollectionPoint.deleted_at.is_(None), visible_clause(principal.scope))
    if village_id:
        stmt = stmt.where(CollectionPoint.village_id == village_id)
    if status:
        stmt = stmt.where(CollectionPoint.status == status)
    if collector_id:
        stmt = stmt.where(CollectionPoint.assigned_collector_id == collector_id)
    if stream_id:
        stmt = stmt.where(CollectionPoint.streams.any(WasteStream.id == stream_id))
    if min_fill is not None:
        stmt = stmt.where(CollectionPoint.fill_percent >= min_fill)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(CollectionPoint.name).like(like), func.lower(CollectionPoint.code).like(like)))
    page = paginate(db, stmt, params, SORTS, "code")
    page["items"] = serialize_points(db, page["items"], principal.scope)
    return page


@router.get("/nearby", response_model=list[CollectionPointOut], summary="PostGIS radius search")
def nearby(
    db: DB,
    principal: CurrentUser,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_m: int = Query(1000, ge=10, le=50000),
):
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326).cast(Geography())
    stmt = (
        select(CollectionPoint)
        .where(
            CollectionPoint.deleted_at.is_(None),
            visible_clause(principal.scope),
            func.ST_DWithin(CollectionPoint.location, point, radius_m),
        )
        .order_by(func.ST_Distance(CollectionPoint.location, point))
        .limit(100)
    )
    return serialize_points(db, db.scalars(stmt).all(), principal.scope)


@router.get("/by-qr/{qr_code}", response_model=CollectionPointOut)
def by_qr(qr_code: str, db: DB, principal: CurrentUser):
    code = qr_code.removeprefix("plasticloop:cp:").strip().upper()
    cp = db.scalar(select(CollectionPoint).where(CollectionPoint.qr_code == code, CollectionPoint.deleted_at.is_(None)))
    if cp is None:
        raise not_found("Collection point")
    principal.scope.ensure_village(cp.village_id, "Collection point")
    return serialize_points(db, [cp], principal.scope)[0]


@router.get("/{point_id}")
def get_point(point_id: uuid.UUID, db: DB, principal: CurrentUser):
    cp = _get_visible(db, point_id, principal.scope)
    staff = principal.scope.sees_all or cp.village_id in principal.scope.village_ids
    events = db.scalars(
        select(CollectionEvent).where(CollectionEvent.collection_point_id == cp.id).order_by(CollectionEvent.collected_at.desc()).limit(15)
    ).all()
    requests = db.scalars(
        select(PickupRequest)
        .where(PickupRequest.collection_point_id == cp.id, PickupRequest.status.notin_([PickupStatus.COMPLETED, PickupStatus.CANCELLED]))
        .order_by(PickupRequest.created_at.desc())
    ).all()
    return {
        "point": serialize_points(db, [cp], principal.scope)[0],
        "qr_payload": f"plasticloop:cp:{cp.qr_code}",
        "recent_collections": serialize_events(db, events) if staff else [],
        "open_requests": [PickupRequestOut.model_validate(r) for r in requests] if staff else [],
    }


@router.post("", response_model=CollectionPointOut, status_code=201)
def create_point(body: CollectionPointIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    principal.scope.ensure_village(body.village_id, "Village")
    village = db.get(Village, body.village_id)
    _validate_collector(db, village, body.assigned_collector_id)
    if body.household_id:
        hh = db.get(Household, body.household_id)
        if hh is None or hh.village_id != village.id:
            raise bad_request("INVALID_HOUSEHOLD", "Household must belong to the same village")
    seq = (db.scalar(select(func.count()).where(CollectionPoint.village_id == village.id)) or 0) + 1
    data = body.model_dump(exclude={"stream_ids"})
    cp = CollectionPoint(**data, code=f"{village.code}-CP-{seq:03d}", qr_code=new_qr_code(), streams=_streams(db, body.stream_ids))
    db.add(cp)
    db.flush()
    audit(db, principal, "collection_point.created", "collection_point", cp.id, after={"code": cp.code, "qr_code": cp.qr_code})
    db.commit()
    db.refresh(cp)
    return serialize_points(db, [cp], principal.scope)[0]


@router.patch("/{point_id}", response_model=CollectionPointOut)
def update_point(point_id: uuid.UUID, body: CollectionPointPatch, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    cp = _get_visible(db, point_id, principal.scope)
    if body.version is not None and body.version != cp.version:
        raise conflict("VERSION_CONFLICT", "This point was changed by someone else. Reload and try again.")
    data = body.model_dump(exclude_unset=True, exclude={"version", "stream_ids"})
    if "assigned_collector_id" in data:
        _validate_collector(db, db.get(Village, cp.village_id), data["assigned_collector_id"])
    before = snapshot(cp, *data.keys())
    for k, v in data.items():
        setattr(cp, k, v)
    if body.stream_ids is not None:
        cp.streams = _streams(db, body.stream_ids)
        data["stream_ids"] = body.stream_ids
    audit(db, principal, "collection_point.updated", "collection_point", cp.id, before, data)
    db.commit()
    db.refresh(cp)
    return serialize_points(db, [cp], principal.scope)[0]


@router.post("/{point_id}/regenerate-qr", response_model=CollectionPointOut, summary="Rotate a lost or damaged QR label")
def regenerate_qr(point_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    cp = _get_visible(db, point_id, principal.scope)
    old = cp.qr_code
    cp.qr_code = new_qr_code()
    audit(db, principal, "collection_point.qr_rotated", "collection_point", cp.id, {"qr_code": old}, {"qr_code": cp.qr_code})
    db.commit()
    db.refresh(cp)
    return serialize_points(db, [cp], principal.scope)[0]
