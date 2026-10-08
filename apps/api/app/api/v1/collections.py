import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.api.v1.collection_points import brief, serialize_points, visible_clause
from app.core.errors import AppError, bad_request, not_found
from app.models import (
    CollectionAssignment,
    CollectionEvent,
    CollectionPoint,
    PickupRequest,
    SyncReceipt,
    User,
    Village,
    WasteStream,
)
from app.models.enums import (
    AssignmentStatus,
    DataOrigin,
    PickupStatus,
    PointStatus,
    ReviewStatus,
    RoleKey,
    SyncReceiptStatus,
)
from app.schemas.collection import (
    AssignmentIn,
    AssignmentOut,
    CollectionCreateIn,
    CollectionEventOut,
    CollectionWriteOut,
    MyTasksOut,
    ReceiptOut,
    ReviewIn,
    SyncEventIn,
    TaskStop,
    WasteStreamOut,
)
from app.schemas.common import Page
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit
from app.services.collections import serialize_events
from app.services.listing import PageParams, paginate
from app.services.sync import process_event

router = APIRouter()
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FIELD_ROLES = (RoleKey.COLLECTOR, RoleKey.GP_ADMIN, RoleKey.DRIVER)


def _scoped_events(principal: Principal):
    scope = principal.scope
    stmt = select(CollectionEvent)
    if scope.sees_all or scope.village_ids:
        return stmt.where(scope.village_clause(CollectionEvent.village_id))
    # Households: only collections at their own points
    own_points = select(CollectionPoint.id).where(CollectionPoint.household_id.in_(scope.household_ids or {uuid.UUID(int=0)}))
    return stmt.where(CollectionEvent.collection_point_id.in_(own_points))


@router.get("/my-tasks", response_model=MyTasksOut, summary="Collector's stops + offline cache bundle")
def my_tasks(db: DB, principal: Principal = Depends(require(*FIELD_ROLES)), on: date | None = None):
    day = on or utcnow().date()
    weekday = WEEKDAYS[day.weekday()]
    points = db.scalars(
        select(CollectionPoint).where(
            CollectionPoint.deleted_at.is_(None), CollectionPoint.status == PointStatus.ACTIVE, visible_clause(principal.scope)
        )
    ).all()
    serialized = {p.id: p for p in serialize_points(db, points, principal.scope)}
    assignments = {
        a.collection_point_id: a
        for a in db.scalars(
            select(CollectionAssignment).where(
                CollectionAssignment.collector_id == principal.id,
                CollectionAssignment.scheduled_date == day,
                CollectionAssignment.status == AssignmentStatus.PENDING,
            )
        )
    }
    requests: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in db.scalars(
        select(PickupRequest).where(
            PickupRequest.status.in_([PickupStatus.SUBMITTED, PickupStatus.ASSIGNED, PickupStatus.IN_PROGRESS]),
            PickupRequest.collection_point_id.isnot(None),
            or_(PickupRequest.assigned_collector_id == principal.id, PickupRequest.assigned_collector_id.is_(None)),
            principal.scope.village_clause(PickupRequest.village_id),
        )
    ):
        requests.setdefault(r.collection_point_id, []).append(r.id)

    stops = []
    for p in points:
        reasons = []
        mine = p.assigned_collector_id == principal.id or RoleKey.COLLECTOR not in principal.scope.roles
        if mine and weekday in (p.pickup_days or []):
            reasons.append("scheduled")
        if p.id in assignments:
            reasons.append("assigned")
        if p.id in requests and mine:
            reasons.append("pickup_request")
        if p.emergency_flag:
            reasons.append("emergency")
        if mine and p.fill_percent is not None and float(p.fill_percent) >= 80:
            reasons.append("bin_full")
        if reasons:
            a = assignments.get(p.id)
            stops.append(
                TaskStop(point=brief(serialized[p.id]), due_reasons=reasons, assignment_id=a.id if a else None,
                         pickup_request_ids=requests.get(p.id, []))
            )
    stops.sort(key=lambda s: ("emergency" not in s.due_reasons, -s.point.priority, s.point.code))
    streams = db.scalars(select(WasteStream).where(WasteStream.active.is_(True)).order_by(WasteStream.sort_order)).all()
    return MyTasksOut(
        date=day,
        collector_id=principal.id,
        stops=stops,
        points=[brief(p) for p in serialized.values()],
        streams=[WasteStreamOut.model_validate(s) for s in streams],
        generated_at=utcnow(),
    )


@router.get("", response_model=Page[CollectionEventOut])
def list_collections(
    db: DB,
    principal: CurrentUser,
    params: PageParams = Depends(),
    village_id: uuid.UUID | None = None,
    collector_id: uuid.UUID | None = None,
    collection_point_id: uuid.UUID | None = None,
    waste_stream_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    data_origin: DataOrigin | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    mine: bool = False,
):
    stmt = _scoped_events(principal)
    for col, val in (
        (CollectionEvent.village_id, village_id),
        (CollectionEvent.collector_id, collector_id),
        (CollectionEvent.collection_point_id, collection_point_id),
        (CollectionEvent.waste_stream_id, waste_stream_id),
        (CollectionEvent.review_status, review_status),
        (CollectionEvent.data_origin, data_origin),
    ):
        if val is not None:
            stmt = stmt.where(col == val)
    if mine:
        stmt = stmt.where(CollectionEvent.collector_id == principal.id)
    if date_from:
        stmt = stmt.where(CollectionEvent.collected_at >= date_from)
    if date_to:
        stmt = stmt.where(CollectionEvent.collected_at <= date_to)
    page = paginate(db, stmt, params, {"collected_at": CollectionEvent.collected_at, "weight": CollectionEvent.weight_kg}, "-collected_at")
    page["items"] = serialize_events(db, page["items"])
    return page


@router.post("", response_model=CollectionWriteOut, status_code=201, summary="Record a collection while online (idempotent)")
def create_collection(
    body: CollectionCreateIn,
    db: DB,
    principal: Principal = Depends(require(*FIELD_ROLES)),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    event_id = body.event_id
    if event_id is None and idempotency_key:
        try:
            event_id = uuid.UUID(idempotency_key)
        except ValueError as exc:
            raise bad_request("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must be a UUID") from exc
    event_id = event_id or uuid.uuid4()
    payload = body.model_dump(mode="json", exclude={"event_id"})
    result = process_event(db, principal, SyncEventIn(event_id=event_id, payload=payload), client_id="web", offline=False)
    db.commit()
    if result.status == SyncReceiptStatus.REJECTED:
        raise AppError(422, result.code or "REJECTED", result.message or "Rejected", result.details)
    if result.status == SyncReceiptStatus.CONFLICT:
        raise AppError(409, result.code or "CONFLICT", result.message or "Conflict")
    event = db.get(CollectionEvent, result.server_id)
    out = CollectionWriteOut(status=result.status, event=serialize_events(db, [event])[0], code=result.code, message=result.message)
    return JSONResponse(out.model_dump(mode="json"), status_code=201 if result.status == SyncReceiptStatus.ACCEPTED else 200)


def _visible_event(db, event_id: uuid.UUID, principal: Principal) -> CollectionEvent:
    event = db.scalar(_scoped_events(principal).where(CollectionEvent.id == event_id))
    if event is None:
        raise not_found("Collection")
    return event


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(db: DB, principal: CurrentUser, on: date | None = None, collector_id: uuid.UUID | None = None):
    stmt = (
        select(CollectionAssignment)
        .join(CollectionPoint, CollectionPoint.id == CollectionAssignment.collection_point_id)
        .where(principal.scope.village_clause(CollectionPoint.village_id))
        .order_by(CollectionAssignment.scheduled_date.desc())
        .limit(500)
    )
    if on:
        stmt = stmt.where(CollectionAssignment.scheduled_date == on)
    if collector_id:
        stmt = stmt.where(CollectionAssignment.collector_id == collector_id)
    return db.scalars(stmt).all()


@router.post("/assignments", response_model=list[AssignmentOut], status_code=201)
def create_assignments(body: AssignmentIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    created = []
    for cp_id in dict.fromkeys(body.collection_point_ids):
        cp = db.get(CollectionPoint, cp_id)
        if cp is None:
            raise not_found("Collection point")
        principal.scope.ensure_village(cp.village_id, "Collection point")
        exists = db.scalar(
            select(CollectionAssignment).where(
                CollectionAssignment.collector_id == body.collector_id,
                CollectionAssignment.collection_point_id == cp_id,
                CollectionAssignment.scheduled_date == body.scheduled_date,
            )
        )
        if exists:
            created.append(exists)
            continue
        a = CollectionAssignment(collector_id=body.collector_id, collection_point_id=cp_id,
                                 scheduled_date=body.scheduled_date, created_by=principal.id)
        db.add(a)
        created.append(a)
    db.flush()
    audit(db, principal, "assignments.created", "collector", body.collector_id,
          after={"date": body.scheduled_date, "points": [str(i) for i in body.collection_point_ids]})
    db.commit()
    return created


@router.get("/{event_id}", response_model=CollectionEventOut)
def get_collection(event_id: uuid.UUID, db: DB, principal: CurrentUser):
    return serialize_events(db, [_visible_event(db, event_id, principal)])[0]


@router.get("/{event_id}/receipt", response_model=ReceiptOut)
def receipt(event_id: uuid.UUID, db: DB, principal: CurrentUser):
    e = _visible_event(db, event_id, principal)
    cp = db.get(CollectionPoint, e.collection_point_id)
    village = db.get(Village, e.village_id)
    stream = db.get(WasteStream, e.waste_stream_id)
    collector = db.get(User, e.collector_id)
    ack = db.get(SyncReceipt, e.id)
    return ReceiptOut(
        receipt_no=f"PL-{str(e.id)[:8].upper()}",
        event_id=e.id,
        collection_point_code=cp.code,
        collection_point_name=cp.name,
        village_name=village.name if village else None,
        stream_label=stream.label,
        weight_kg=e.weight_kg,
        measurement_source=e.measurement_source,
        collected_at=e.collected_at,
        acknowledged_at=ack.received_at if ack else e.created_at,
        collector_name=collector.full_name.split()[0] if collector else None,
        data_origin=e.data_origin,
        review_status=e.review_status,
    )


@router.patch("/{event_id}/review", response_model=CollectionEventOut)
def review_collection(event_id: uuid.UUID, body: ReviewIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    e = _visible_event(db, event_id, principal)
    before = {"review_status": e.review_status, "review_reason": e.review_reason}
    e.review_status = ReviewStatus(body.review_status)
    e.review_reason = f"{e.review_reason or ''} | Review: {body.note}".strip(" |")
    audit(db, principal, "collection.reviewed", "collection_event", e.id, before, body.model_dump())
    db.commit()
    return serialize_events(db, [e])[0]
