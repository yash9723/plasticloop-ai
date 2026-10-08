import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import CollectionEvent, CollectionPoint, Facility, Route, RouteStop, User, Vehicle
from app.models.enums import RoleKey, RouteStatus, StopStatus
from app.schemas.common import Kg, KgIn, Page
from app.security.deps import DB, Principal, require
from app.security.tokens import utcnow
from app.services import route_planner
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.notifications import notify, village_admins

router = APIRouter()
VIEWERS = (RoleKey.GP_ADMIN, RoleKey.DRIVER, RoleKey.EVALUATOR)


class PlanIn(BaseModel):
    vehicle_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    planned_date: date
    village_ids: list[uuid.UUID] | None = None
    point_ids: list[uuid.UUID] | None = Field(None, max_length=200, description="Omit to auto-select due/full/requested points")
    emergency_point_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    facility_id: uuid.UUID | None = None
    shift_start: time = time(7, 0)
    max_shift_hours: float = Field(8, gt=0.5, le=14)
    time_limit_s: float = Field(3, ge=0.5, le=30)
    save: bool = False


class CandidateOut(BaseModel):
    collection_point_id: uuid.UUID
    code: str
    name: str
    lat: float
    lng: float
    expected_kg: Kg
    load_basis: str
    reasons: list[str]
    priority: int
    fill_percent: float | None


class StopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    collection_point_id: uuid.UUID
    planned_arrival_s: int
    expected_load_kg: Kg
    cumulative_load_kg: Kg
    leg_distance_m: int
    status: StopStatus
    completed_at: datetime | None
    skip_reason: str | None
    collection_event_id: uuid.UUID | None
    code: str = ""
    name: str = ""
    lat: float | None = None
    lng: float | None = None


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None
    facility_id: uuid.UUID | None
    planned_date: date
    mode: str
    status: RouteStatus
    distance_m: int
    duration_s: int
    load_kg: Kg
    distance_basis: str
    baseline_distance_m: int | None
    solver_status: str
    warnings: list[Any]
    inputs: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    actual_load_kg: Kg | None
    delay_reports: list[Any]
    notes: str | None
    version: int
    vehicle_name: str = ""
    registration_no: str = ""
    driver_name: str | None = None
    facility_name: str | None = None
    stops_total: int = 0
    stops_done: int = 0


class RouteDetail(RouteOut):
    stops: list[StopOut] = []
    depot: tuple[float, float] | None = None
    facility_location: tuple[float, float] | None = None


class StopActionIn(BaseModel):
    action: Literal["complete", "skip"]
    reason: str | None = Field(None, max_length=300)
    collection_event_id: uuid.UUID | None = None


class CompleteIn(BaseModel):
    actual_load_kg: KgIn | None = None
    notes: str | None = Field(None, max_length=1000)


class DelayIn(BaseModel):
    minutes: int = Field(ge=1, le=600)
    reason: str = Field(min_length=3, max_length=300)


def _visible(db: Session, route_id: uuid.UUID, principal: Principal) -> Route:
    r = db.get(Route, route_id)
    if r is None:
        raise not_found("Route")
    scope = principal.scope
    if not scope.sees_all and r.organization_id not in scope.org_ids:
        raise not_found("Route")
    if RoleKey.DRIVER in scope.roles and not scope.has(RoleKey.GP_ADMIN) and r.driver_id != principal.id:
        raise not_found("Route")
    return r


def _operate(db: Session, route_id: uuid.UUID, principal: Principal) -> Route:
    r = _visible(db, route_id, principal)
    if principal.scope.is_evaluator and not principal.scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    if not (principal.scope.has(RoleKey.GP_ADMIN) or r.driver_id == principal.id):
        raise forbidden("Only the assigned driver or a panchayat admin can update this route")
    return r


def _serialize(db: Session, routes: list[Route], detail: bool = False) -> list:
    if not routes:
        return []
    vehicles = {v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.id.in_({r.vehicle_id for r in routes})))}
    drivers = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({r.driver_id for r in routes if r.driver_id}))).all())
    facilities = {f.id: f for f in db.scalars(select(Facility).where(Facility.id.in_({r.facility_id for r in routes if r.facility_id})))}
    out = []
    for r in routes:
        o = (RouteDetail if detail else RouteOut).model_validate(r)
        v = vehicles[r.vehicle_id]
        o.vehicle_name, o.registration_no, o.driver_name = v.name, v.registration_no, drivers.get(r.driver_id)
        f = facilities.get(r.facility_id)
        o.facility_name = f.name if f else None
        o.stops_total = len(r.stops)
        o.stops_done = sum(1 for s in r.stops if s.status != StopStatus.PENDING)
        if detail:
            cps = {c.id: c for c in db.scalars(select(CollectionPoint).where(CollectionPoint.id.in_({s.collection_point_id for s in r.stops})))}
            stops = []
            for s in r.stops:
                so = StopOut.model_validate(s)
                c = cps[s.collection_point_id]
                so.code, so.name, so.lat, so.lng = c.code, c.name, c.lat, c.lng
                stops.append(so)
            o.stops = stops
            o.depot = (v.depot_lat, v.depot_lng)
            o.facility_location = (f.lat, f.lng) if f and f.lat is not None else None
        out.append(o)
    return out


@router.get("/candidates", response_model=list[CandidateOut], summary="Points due for collection (full, requested or scheduled)")
def list_candidates(db: DB, planned_date: date, village_id: uuid.UUID | None = None,
                    principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.EVALUATOR))):
    cands = route_planner.candidates(db, principal.scope, [village_id] if village_id else None, planned_date)
    return [CandidateOut(collection_point_id=c.point.id, code=c.point.code, name=c.point.name, lat=c.point.lat, lng=c.point.lng,
                         expected_kg=c.expected_kg, load_basis=c.load_basis, reasons=c.reasons, priority=c.priority,
                         fill_percent=float(c.point.fill_percent) if c.point.fill_percent is not None else None) for c in cands]


@router.post("/plan", summary="Optimise routes with OR-Tools; preview by default, `save: true` creates routes")
def plan(body: PlanIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.EVALUATOR))):
    if body.save and principal.scope.is_evaluator and not principal.scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    result = route_planner.plan_routes(
        db, principal.scope, principal.id, vehicle_ids=body.vehicle_ids, planned_date=body.planned_date,
        village_ids=body.village_ids, point_ids=body.point_ids, emergency_point_ids=body.emergency_point_ids,
        facility_id=body.facility_id, shift_start=body.shift_start, max_shift_hours=body.max_shift_hours,
        time_limit_s=body.time_limit_s, save=body.save)
    if body.save:
        if not result["saved_route_ids"]:
            raise bad_request("NOTHING_TO_SAVE", "No stops could be routed with the chosen vehicles")
        audit(db, principal, "routes.planned", "route_plan", result["plan_id"],
              after={"routes": len(result["saved_route_ids"]), "distance_m": result["totals"]["distance_m"]})
        for rid in result["saved_route_ids"]:
            r = db.get(Route, rid)
            if r.driver_id:
                notify(db, [r.driver_id], type="route_assigned", title=f"New route for {r.planned_date:%d %b}",
                       entity_type="route", entity_id=r.id, link=f"/routes/{r.id}")
        db.commit()
    return result


@router.get("", response_model=Page[RouteOut])
def list_routes(db: DB, params: PageParams = Depends(), status: RouteStatus | None = None, planned_date: date | None = None,
                mine: bool = False, principal: Principal = Depends(require(*VIEWERS))):
    scope = principal.scope
    stmt = select(Route).where(scope.org_clause(Route.organization_id))
    if mine or (RoleKey.DRIVER in scope.roles and not scope.has(RoleKey.GP_ADMIN) and not scope.sees_all):
        stmt = stmt.where(Route.driver_id == principal.id)
    if status:
        stmt = stmt.where(Route.status == status)
    if planned_date:
        stmt = stmt.where(Route.planned_date == planned_date)
    page = paginate(db, stmt, params, {"date": Route.planned_date, "distance": Route.distance_m, "status": Route.status}, "-date")
    page["items"] = _serialize(db, page["items"])
    return page


@router.get("/{route_id}", response_model=RouteDetail)
def get_route(route_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*VIEWERS))):
    return _serialize(db, [_visible(db, route_id, principal)], detail=True)[0]


@router.post("/{route_id}/start", response_model=RouteDetail)
def start_route(route_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.DRIVER))):
    r = _operate(db, route_id, principal)
    route_planner.route_status_transition(r, RouteStatus.IN_PROGRESS)
    r.started_at = utcnow()
    audit(db, principal, "route.started", "route", r.id)
    db.commit()
    return _serialize(db, [r], detail=True)[0]


@router.post("/{route_id}/stops/{stop_id}", response_model=RouteDetail, summary="Mark a stop collected or skipped (reason required)")
def stop_action(route_id: uuid.UUID, stop_id: uuid.UUID, body: StopActionIn, db: DB,
                principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.DRIVER))):
    r = _operate(db, route_id, principal)
    if r.status != RouteStatus.IN_PROGRESS:
        raise conflict("ROUTE_NOT_STARTED", "Start the route before updating stops")
    stop = db.get(RouteStop, stop_id)
    if stop is None or stop.route_id != r.id:
        raise not_found("Stop")
    if stop.status != StopStatus.PENDING:
        raise conflict("STOP_ALREADY_DONE", "This stop was already updated")
    if body.action == "skip":
        if not body.reason or len(body.reason.strip()) < 3:
            raise bad_request("REASON_REQUIRED", "Say why the stop was skipped")
        stop.status, stop.skip_reason = StopStatus.SKIPPED, body.reason.strip()
        cp = db.get(CollectionPoint, stop.collection_point_id)
        notify(db, village_admins(db, cp.village_id), type="stop_skipped", title=f"{cp.code} skipped on route",
               body=body.reason.strip(), entity_type="route", entity_id=r.id, link=f"/routes/{r.id}")
    else:
        if body.collection_event_id:
            ev = db.get(CollectionEvent, body.collection_event_id)
            if ev is None or ev.collection_point_id != stop.collection_point_id:
                raise bad_request("EVENT_MISMATCH", "That collection was not recorded at this stop")
            stop.collection_event_id = ev.id
        stop.status = StopStatus.COMPLETED
    stop.completed_at = utcnow()
    r.updated_at = utcnow()  # bumps the route version so concurrent editors notice
    audit(db, principal, f"route.stop_{body.action}", "route", r.id, after={"stop": str(stop.id)})
    db.commit()
    return _serialize(db, [r], detail=True)[0]


@router.post("/{route_id}/complete", response_model=RouteDetail)
def complete_route(route_id: uuid.UUID, body: CompleteIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.DRIVER))):
    r = _operate(db, route_id, principal)
    route_planner.route_status_transition(r, RouteStatus.COMPLETED)
    for s in r.stops:
        if s.status == StopStatus.PENDING:
            s.status, s.skip_reason, s.completed_at = StopStatus.SKIPPED, "Not reached before the route was closed", utcnow()
    r.completed_at, r.actual_load_kg = utcnow(), body.actual_load_kg
    if body.notes:
        r.notes = body.notes
    audit(db, principal, "route.completed", "route", r.id, after={"actual_load_kg": str(body.actual_load_kg)})
    db.commit()
    return _serialize(db, [r], detail=True)[0]


@router.post("/{route_id}/delay", response_model=RouteDetail)
def report_delay(route_id: uuid.UUID, body: DelayIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.DRIVER))):
    r = _operate(db, route_id, principal)
    if r.status not in (RouteStatus.PLANNED, RouteStatus.IN_PROGRESS):
        raise conflict("ROUTE_CLOSED", "This route is already closed")
    r.delay_reports = [*r.delay_reports, {"at": utcnow().isoformat(), "minutes": body.minutes, "reason": body.reason,
                                          "by": str(principal.id)}]
    vehicle = db.get(Vehicle, r.vehicle_id)
    admins = {u for s in r.stops for u in village_admins(db, db.get(CollectionPoint, s.collection_point_id).village_id)}
    notify(db, admins, type="route_delayed", title=f"{vehicle.name} delayed {body.minutes} min", body=body.reason,
           entity_type="route", entity_id=r.id, link=f"/routes/{r.id}")
    db.commit()
    return _serialize(db, [r], detail=True)[0]


@router.post("/{route_id}/cancel", response_model=RouteDetail)
def cancel_route(route_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    r = _operate(db, route_id, principal)
    route_planner.route_status_transition(r, RouteStatus.CANCELLED)
    audit(db, principal, "route.cancelled", "route", r.id)
    db.commit()
    return _serialize(db, [r], detail=True)[0]

