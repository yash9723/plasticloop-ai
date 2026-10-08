"""OR-Tools routing: pure solver fixtures on small synthetic matrices, then planner/route API tests."""

from datetime import date

import pytest

from app.routing.matrix import UNREACHABLE_M, build_matrix, haversine_m
from app.routing.solver import StopIn, VehicleIn, baseline_distance, solve
from tests import factories as f

# Depot at node 0, stops on a line every 1 km (node i is i km from the depot).
N = 7
DIST = [[abs(i - j) * 1000 for j in range(N)] for i in range(N)]
DUR = [[abs(i - j) * 120 for j in range(N)] for i in range(N)]  # 2 min per km
FAST = 0.5


def stops(*ids, demand=10.0, **kw):
    return [StopIn(id=f"s{i}", node=i, demand_kg=demand, service_s=60, **kw) for i in ids]


def test_haversine_and_estimate_basis():
    assert 1100 < haversine_m((17.0, 78.0), (17.01, 78.0)) < 1120
    dist, dur, basis, warnings = build_matrix([(17.0, 78.0), (17.01, 78.0)])
    assert basis == "haversine_estimate" and not warnings
    assert dist[0][1] == round(haversine_m((17.0, 78.0), (17.01, 78.0)) * 1.3) and dur[0][1] > 0


def test_empty_stop_list():
    plan = solve(DIST, DUR, [], [VehicleIn("v1", 0, 100)], time_limit_s=FAST)
    assert plan.status == "empty" and plan.distance_m == 0 and not plan.dropped


def test_no_vehicles():
    plan = solve(DIST, DUR, stops(1, 2), [], time_limit_s=FAST)
    assert plan.status == "no_vehicles" and set(plan.dropped) == {"s1", "s2"}


def test_single_vehicle_visits_all_in_order_and_returns():
    plan = solve(DIST, DUR, stops(3, 1, 2), [VehicleIn("v1", 0, 100)], time_limit_s=FAST)
    assert plan.visited_ids == ["s1", "s2", "s3"]
    assert plan.distance_m == 6000  # 0→1→2→3→0
    r = plan.routes[0]
    assert r.load_kg == 30 and [s.load_after_kg for s in r.stops] == [10, 20, 30]
    assert r.stops[0].arrival_s == 120 and r.stops[1].arrival_s == 120 + 60 + 120


def test_capacity_splits_across_two_vehicles():
    plan = solve(DIST, DUR, stops(1, 2, 3, 4, demand=30), [VehicleIn("v1", 0, 60), VehicleIn("v2", 0, 60)], time_limit_s=FAST)
    assert not plan.dropped and sorted(plan.visited_ids) == ["s1", "s2", "s3", "s4"]
    assert all(r.load_kg <= 60 for r in plan.routes)


def test_insufficient_capacity_drops_lowest_priority():
    s = [StopIn("low", 1, 40, priority=1), StopIn("high", 2, 40, priority=5)]
    plan = solve(DIST, DUR, s, [VehicleIn("v1", 0, 50)], time_limit_s=FAST)
    assert plan.visited_ids == ["high"] and plan.dropped == {"low": "insufficient_capacity_or_time"}


def test_stop_heavier_than_any_vehicle_is_reported():
    plan = solve(DIST, DUR, stops(1) + [StopIn("huge", 2, 500)], [VehicleIn("v1", 0, 100)], time_limit_s=FAST)
    assert plan.dropped == {"huge": "exceeds_vehicle_capacity"} and plan.visited_ids == ["s1"]


def test_unreachable_stop_is_dropped_not_routed():
    dist = [row[:] for row in DIST]
    for i in range(N):
        dist[i][5] = dist[5][i] = UNREACHABLE_M if i != 5 else 0
    plan = solve(dist, DUR, stops(1, 5), [VehicleIn("v1", 0, 100)], time_limit_s=FAST)
    assert plan.dropped == {"s5": "unreachable"} and plan.visited_ids == ["s1"]


def test_time_window_forces_order():
    # s3 must be served in the first 8 minutes; s1 only after 20 minutes.
    s = [StopIn("s1", 1, 5, service_s=60, window=(1200, 3600)), StopIn("s3", 3, 5, service_s=60, window=(0, 480))]
    plan = solve(DIST, DUR, s, [VehicleIn("v1", 0, 100)], time_limit_s=FAST)
    assert plan.visited_ids == ["s3", "s1"]
    arrivals = {p.stop_id: p.arrival_s for p in plan.routes[0].stops}
    assert arrivals["s3"] <= 480 and arrivals["s1"] >= 1200


def test_max_duration_drops_far_stop():
    plan = solve(DIST, DUR, stops(1, 6), [VehicleIn("v1", 0, 100, max_duration_s=900)], time_limit_s=FAST)
    assert plan.visited_ids == ["s1"] and "s6" in plan.dropped


def test_mandatory_emergency_stop_beats_priority():
    s = [StopIn("normal", 1, 40, priority=5), StopIn("emergency", 2, 40, priority=1, mandatory=True)]
    plan = solve(DIST, DUR, s, [VehicleIn("v1", 0, 50)], time_limit_s=FAST)
    assert plan.visited_ids == ["emergency"] and "normal" in plan.dropped


def test_unload_at_facility_end_node():
    plan = solve(DIST, DUR, stops(1, 2), [VehicleIn("v1", 0, 100)], end_node=6, time_limit_s=FAST)
    assert plan.distance_m == 6000  # 0→1→2→6


def test_baseline_uses_same_matrix_and_is_not_better():
    order = stops(3, 1, 4, 2)  # deliberately poor input order
    vehicles = [VehicleIn("v1", 0, 100)]
    plan = solve(DIST, DUR, order, vehicles, time_limit_s=FAST)
    base = baseline_distance(DIST, order, vehicles)
    assert base == 3000 + 2000 + 3000 + 2000 + 2000
    assert plan.distance_m <= base
    assert baseline_distance(DIST, stops(1, 2, demand=80), vehicles) is None  # fixed order cannot carry it


# ---------- planner + routes API (database) ----------
API = "/api/v1"


@pytest.fixture
def fleet(db, client):
    gp = f.org(db)
    v = f.village(db, gp, lat=17.90, lng=78.90)
    admin = f.user(db, "gp_admin", gp)
    driver = f.user(db, "driver", gp)
    s = f.stream(db)
    pts = [f.point(db, v, [s], lat=17.90 + 0.004 * i, lng=78.90 + 0.003 * (i % 3), fill_percent=85, bin_capacity_kg=100) for i in range(1, 6)]
    r = client.post(f"{API}/vehicles", headers=f.headers(admin), json={
        "registration_no": "TS09AB1234", "name": "E-cart 1", "vehicle_type": "e_cart", "capacity_kg": "300",
        "depot_lat": 17.90, "depot_lng": 78.90, "driver_id": str(driver.id)})
    assert r.status_code == 201, r.text
    return {"gp": gp, "village": v, "admin": admin, "driver": driver, "points": pts, "vehicle": r.json()}


def plan_body(w, **kw):
    return {"vehicle_ids": [w["vehicle"]["id"]], "planned_date": date.today().isoformat(), "time_limit_s": 0.5, **kw}


def test_plan_preview_reports_basis_estimates_and_capacity(fleet, client):
    r = client.post(f"{API}/routes/plan", headers=f.headers(fleet["admin"]), json=plan_body(fleet))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["distance_basis"] == "haversine_estimate" and p["plan_id"] is None
    # 5 bins × 85 kg expected (85% of 100 kg) = 425 kg > 300 kg capacity → some stops must be dropped, with a reason.
    assert p["totals"]["stops_planned"] == 3 and p["totals"]["stops_dropped"] == 2
    assert {d["reason"] for d in p["dropped"]} == {"insufficient_capacity_or_time"}
    route = p["routes"][0]
    assert route["load_kg"] <= 300 and all(s["load_basis"] == "fill_level_estimate" for s in route["stops"])
    if p["totals"]["baseline_distance_m"]:
        assert p["totals"]["distance_m"] <= p["totals"]["baseline_distance_m"]


def test_emergency_stop_is_always_included(fleet, client):
    target = fleet["points"][-1]
    r = client.post(f"{API}/routes/plan", headers=f.headers(fleet["admin"]),
                    json=plan_body(fleet, emergency_point_ids=[str(target.id)]))
    planned = [s["collection_point_id"] for s in r.json()["routes"][0]["stops"]]
    assert str(target.id) in planned


def test_save_then_driver_runs_route(fleet, client, db):
    saved = client.post(f"{API}/routes/plan", headers=f.headers(fleet["admin"]), json=plan_body(fleet, save=True)).json()
    assert len(saved["saved_route_ids"]) == 1
    rid = saved["saved_route_ids"][0]
    dh = f.headers(fleet["driver"])
    mine = client.get(f"{API}/routes", headers=dh).json()
    assert [x["id"] for x in mine["items"]] == [rid]
    detail = client.get(f"{API}/routes/{rid}", headers=dh).json()
    assert detail["distance_basis"] == "haversine_estimate" and len(detail["stops"]) == 3
    assert client.post(f"{API}/routes/{rid}/stops/{detail['stops'][0]['id']}", headers=dh, json={"action": "complete"}).status_code == 409
    assert client.post(f"{API}/routes/{rid}/start", headers=dh).json()["status"] == "in_progress"
    s0, s1 = detail["stops"][0]["id"], detail["stops"][1]["id"]
    assert client.post(f"{API}/routes/{rid}/stops/{s0}", headers=dh, json={"action": "complete"}).status_code == 200
    assert client.post(f"{API}/routes/{rid}/stops/{s1}", headers=dh, json={"action": "skip"}).status_code == 400
    assert client.post(f"{API}/routes/{rid}/stops/{s1}", headers=dh, json={"action": "skip", "reason": "Road flooded"}).status_code == 200
    done = client.post(f"{API}/routes/{rid}/complete", headers=dh, json={"actual_load_kg": "150.5"}).json()
    assert done["status"] == "completed" and [s["status"] for s in done["stops"]] == ["completed", "skipped", "skipped"]


def test_routes_and_vehicles_are_tenant_scoped(fleet, client, db):
    other_admin = f.user(db, "gp_admin", f.org(db))
    r = client.post(f"{API}/routes/plan", headers=f.headers(other_admin), json=plan_body(fleet))
    assert r.status_code == 404
    assert client.get(f"{API}/vehicles", headers=f.headers(other_admin)).json() == []
    collector = f.user(db, "collector", fleet["gp"])
    assert client.post(f"{API}/routes/plan", headers=f.headers(collector), json=plan_body(fleet)).status_code == 403
