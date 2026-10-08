"""Builds routing problems from live data, solves them, compares with a fixed-order baseline and (optionally) saves routes.

Expected loads are estimates and say how they were estimated (`load_basis`). Savings are only reported when the
optimised plan and the baseline serve exactly the same stops on the same distance matrix.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, not_found
from app.models import CollectionEvent, CollectionPoint, Facility, PickupRequest, Route, RouteStop, Vehicle, Village
from app.models.enums import PickupStatus, PointStatus, RouteStatus
from app.routing.matrix import build_matrix
from app.routing.solver import StopIn, VehicleIn, baseline_distance, solve
from app.security.scope import AccessScope
from app.services import system_settings

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_STOP_KG = Decimal("5")


@dataclass
class Candidate:
    point: CollectionPoint
    expected_kg: Decimal
    load_basis: str
    reasons: list[str]
    priority: int
    window: tuple[int, int] | None = None


def _window(pickup_window: str | None, shift_start: time) -> tuple[int, int] | None:
    try:
        a, b = (time.fromisoformat(x.strip()) for x in (pickup_window or "").split("-"))
    except ValueError:
        return None
    base = datetime.combine(date.today(), shift_start)
    start = int((datetime.combine(date.today(), a) - base).total_seconds())
    end = int((datetime.combine(date.today(), b) - base).total_seconds())
    return (max(0, start), end) if end > 0 else None


def candidates(db: Session, scope: AccessScope, village_ids: list[uuid.UUID] | None, planned_date: date,
               point_ids: list[uuid.UUID] | None = None, shift_start: time = time(7, 0)) -> list[Candidate]:
    stmt = select(CollectionPoint).where(CollectionPoint.deleted_at.is_(None), CollectionPoint.status == PointStatus.ACTIVE,
                                         CollectionPoint.lat.is_not(None), scope.village_clause(CollectionPoint.village_id))
    if village_ids:
        stmt = stmt.where(CollectionPoint.village_id.in_(village_ids))
    if point_ids is not None:
        stmt = stmt.where(CollectionPoint.id.in_(point_ids or [uuid.UUID(int=0)]))
    points = list(db.scalars(stmt.order_by(CollectionPoint.code)))
    if not points:
        return []
    ids = [p.id for p in points]
    open_requests: dict[uuid.UUID, list[PickupRequest]] = {}
    for pr in db.scalars(select(PickupRequest).where(PickupRequest.collection_point_id.in_(ids),
                                                     PickupRequest.status.in_([PickupStatus.SUBMITTED, PickupStatus.ASSIGNED]))):
        open_requests.setdefault(pr.collection_point_id, []).append(pr)
    recent = select(CollectionEvent.collection_point_id, CollectionEvent.weight_kg,
                    func.row_number().over(partition_by=CollectionEvent.collection_point_id,
                                           order_by=CollectionEvent.collected_at.desc()).label("rn")).where(
        CollectionEvent.collection_point_id.in_(ids)).subquery()
    history = dict(db.execute(select(recent.c.collection_point_id, func.avg(recent.c.weight_kg)).where(recent.c.rn <= 5)
                              .group_by(recent.c.collection_point_id)).all())
    fill_alert = Decimal(str(system_settings.get_value(db, "fill_alert_percent")))
    overdue_cutoff = datetime.now().astimezone() - timedelta(hours=int(system_settings.get_value(db, "pickup_overdue_hours")))
    weekday = WEEKDAYS[planned_date.weekday()]
    out = []
    for p in points:
        reasons, priority = [], p.priority
        requests = open_requests.get(p.id, [])
        if p.fill_percent is not None and p.fill_percent >= fill_alert:
            reasons.append("fill_alert")
            if p.fill_percent >= 90:
                priority += 1
        if requests:
            reasons.append("pickup_request")
            if any(r.created_at < overdue_cutoff for r in requests):
                reasons.append("overdue_request")
                priority += 1
        if weekday in (p.pickup_days or []):
            reasons.append("scheduled")
        if not reasons and point_ids is None:
            continue
        if p.fill_percent is not None and p.bin_capacity_kg:
            expected, basis = Decimal(str(p.fill_percent)) / 100 * Decimal(str(p.bin_capacity_kg)), "fill_level_estimate"
        elif history.get(p.id):
            expected, basis = Decimal(str(history[p.id])), "history_average"
        else:
            expected, basis = DEFAULT_STOP_KG, "default_assumption"
        extra = sum((Decimal(str(r.estimated_weight_kg)) for r in requests if r.estimated_weight_kg), Decimal("0"))
        if extra:
            expected, basis = expected + extra, basis + "+pickup_request_estimate"
        out.append(Candidate(p, expected.quantize(Decimal("0.1")), basis, reasons or ["manually_selected"], min(5, priority),
                             _window(p.pickup_window, shift_start)))
    return out


def plan_routes(db: Session, scope: AccessScope, actor_id, *, vehicle_ids: list[uuid.UUID], planned_date: date,
                village_ids: list[uuid.UUID] | None = None, point_ids: list[uuid.UUID] | None = None,
                emergency_point_ids: list[uuid.UUID] | None = None, facility_id: uuid.UUID | None = None,
                shift_start: time = time(7, 0), max_shift_hours: float = 8, time_limit_s: float | None = None,
                save: bool = False) -> dict:
    vehicles = [db.get(Vehicle, v) for v in dict.fromkeys(vehicle_ids)]
    if not vehicles or any(v is None or v.deleted_at is not None or not v.active for v in vehicles):
        raise not_found("Vehicle")
    for v in vehicles:
        scope.ensure_org(v.organization_id, "Vehicle")
    facility = None
    if facility_id:
        facility = db.get(Facility, facility_id)
        if facility is None or facility.lat is None:
            raise bad_request("FACILITY_LOCATION_REQUIRED", "The unloading facility needs a location")
    emergency = set(emergency_point_ids or [])
    selected = None if point_ids is None else list({*point_ids, *emergency})
    cands = candidates(db, scope, village_ids, planned_date, selected, shift_start)
    if emergency - {c.point.id for c in cands}:
        raise not_found("Emergency collection point")

    points = [(v.depot_lat, v.depot_lng) for v in vehicles]
    end_node = None
    if facility:
        end_node = len(points)
        points.append((facility.lat, facility.lng))
    first_stop = len(points)
    points += [(c.point.lat, c.point.lng) for c in cands]
    speed = float(system_settings.get_value(db, "routing_avg_speed_kmph"))
    dist, dur, basis, warnings = build_matrix(points, speed)
    service_s = int(system_settings.get_value(db, "service_time_per_stop_min")) * 60
    stops = [StopIn(id=str(c.point.id), node=first_stop + i, demand_kg=float(c.expected_kg), service_s=service_s, window=c.window,
                    priority=c.priority, mandatory=c.point.id in emergency) for i, c in enumerate(cands)]
    vins = [VehicleIn(id=str(v.id), start_node=i, capacity_kg=float(v.capacity_kg), max_duration_s=int(max_shift_hours * 3600))
            for i, v in enumerate(vehicles)]
    plan = solve(dist, dur, stops, vins, end_node=end_node, time_limit_s=time_limit_s or settings.routing_time_limit_s)

    visited = set(plan.visited_ids)
    base = baseline_distance(dist, [s for s in stops if s.id in visited], vins, end_node) if visited else None
    savings = round(100 * (base - plan.distance_m) / base, 1) if base else None
    by_id = {str(c.point.id): c for c in cands}
    cost_per_km = int(system_settings.get_value(db, "route_cost_per_km_paise"))
    vehicle_by_id = {str(v.id): v for v in vehicles}
    shift_dt = datetime.combine(planned_date, shift_start)
    plan_id = uuid.uuid4()
    routes_out, saved_ids = [], []
    for r in plan.routes:
        v = vehicle_by_id[r.vehicle_id]
        stops_out = []
        for seq, s in enumerate(r.stops, start=1):
            c = by_id[s.stop_id]
            stops_out.append({
                "sequence": seq, "collection_point_id": c.point.id, "code": c.point.code, "name": c.point.name,
                "lat": c.point.lat, "lng": c.point.lng, "arrival_s": s.arrival_s,
                "eta": (shift_dt + timedelta(seconds=s.arrival_s)).strftime("%H:%M"), "expected_kg": c.expected_kg,
                "load_after_kg": s.load_after_kg, "leg_m": s.leg_m, "load_basis": c.load_basis, "reasons": c.reasons,
                "emergency": c.point.id in emergency, "window": c.window,
            })
        path = [(v.depot_lat, v.depot_lng), *[(s["lat"], s["lng"]) for s in stops_out]]
        if r.stops:
            path.append((facility.lat, facility.lng) if facility else (v.depot_lat, v.depot_lng))
        route_cost = cost_per_km_for(v, cost_per_km) * r.distance_m // 1000
        routes_out.append({
            "vehicle_id": v.id, "vehicle_name": v.name, "registration_no": v.registration_no, "capacity_kg": v.capacity_kg,
            "driver_id": v.driver_id, "distance_m": r.distance_m, "duration_s": r.duration_s, "load_kg": r.load_kg,
            "utilization_pct": round(100 * r.load_kg / float(v.capacity_kg), 1) if r.stops else 0,
            "cost_estimate_paise": route_cost, "stops": stops_out, "path": path,
        })
        if save and r.stops:
            route = Route(plan_id=plan_id, organization_id=v.organization_id, vehicle_id=v.id, driver_id=v.driver_id,
                          facility_id=facility.id if facility else None, planned_date=planned_date, mode="optimized",
                          distance_m=r.distance_m, duration_s=r.duration_s, load_kg=Decimal(str(r.load_kg)), distance_basis=basis,
                          baseline_distance_m=base, solver_status=plan.status, warnings=warnings + plan.warnings,
                          inputs={"shift_start": shift_start.isoformat(), "vehicle_ids": [str(x) for x in vehicle_ids],
                                  "stop_count": len(stops), "emergency": [str(e) for e in emergency],
                                  "speed_kmph": speed, "service_time_s": service_s, "time_limit_s": time_limit_s},
                          created_by=actor_id)
            db.add(route)
            db.flush()
            for s in stops_out:
                db.add(RouteStop(route_id=route.id, sequence=s["sequence"], collection_point_id=s["collection_point_id"],
                                 planned_arrival_s=s["arrival_s"], expected_load_kg=s["expected_kg"],
                                 cumulative_load_kg=Decimal(str(s["load_after_kg"])), leg_distance_m=s["leg_m"]))
            saved_ids.append(route.id)
    dropped = [{"collection_point_id": by_id[sid].point.id, "code": by_id[sid].point.code, "name": by_id[sid].point.name,
                "reason": reason, "expected_kg": by_id[sid].expected_kg} for sid, reason in plan.dropped.items()]
    village_names = dict(db.execute(select(Village.id, Village.name).where(Village.id.in_({c.point.village_id for c in cands}))).all()) if cands else {}
    return {
        "plan_id": plan_id if save else None,
        "planned_date": planned_date,
        "distance_basis": basis,
        "solver": "OR-Tools routing (guided local search, time-limited)",
        "solver_status": plan.status,
        "warnings": warnings + plan.warnings,
        "routes": routes_out,
        "dropped": dropped,
        "facility": {"id": facility.id, "name": facility.name, "lat": facility.lat, "lng": facility.lng} if facility else None,
        "villages": sorted(village_names.values()),
        "totals": {
            "candidates": len(cands), "stops_planned": len(visited), "stops_dropped": len(dropped),
            "distance_m": plan.distance_m, "baseline_distance_m": base, "savings_pct": savings,
            "expected_load_kg": round(sum(r["load_kg"] for r in routes_out), 1),
        },
        "saved_route_ids": saved_ids,
        "assumptions": {"avg_speed_kmph": speed, "service_time_min": service_s // 60, "cost_per_km_paise": cost_per_km,
                        "baseline": "same stops visited in code order, vehicles filled one after another, same distance matrix"},
    }


def cost_per_km_for(vehicle: Vehicle, default: int) -> int:
    return vehicle.cost_per_km_paise or default


def route_status_transition(route: Route, target: RouteStatus) -> None:
    allowed = {RouteStatus.PLANNED: {RouteStatus.IN_PROGRESS, RouteStatus.CANCELLED},
               RouteStatus.IN_PROGRESS: {RouteStatus.COMPLETED, RouteStatus.CANCELLED}}
    if target not in allowed.get(route.status, set()):
        raise bad_request("INVALID_TRANSITION", f"A {route.status.replace('_', ' ')} route cannot become {target.replace('_', ' ')}")
    route.status = target
