"""Capacitated vehicle routing with time windows, priorities and mandatory (emergency) stops — Google OR-Tools.

Pure functions over a precomputed matrix so they are unit-testable without a database.
Units: distance metres, time seconds from shift start, demand kg (solved in 0.1 kg steps).
"""

from dataclasses import dataclass, field

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.routing.matrix import UNREACHABLE_M

DEMAND_SCALE = 10  # 0.1 kg resolution
DROP_PENALTY_PER_PRIORITY = 100_000  # metres-equivalent: dropping a priority-3 stop "costs" 300 km
MANDATORY_FALLBACK_PENALTY = 10**9


@dataclass
class StopIn:
    id: str
    node: int  # index into the matrix
    demand_kg: float
    service_s: int = 300
    window: tuple[int, int] | None = None
    priority: int = 3  # 1 (low) .. 5 (high)
    mandatory: bool = False


@dataclass
class VehicleIn:
    id: str
    start_node: int
    capacity_kg: float
    max_duration_s: int = 8 * 3600


@dataclass
class PlannedStop:
    stop_id: str
    arrival_s: int
    load_after_kg: float
    leg_m: int


@dataclass
class VehicleRoute:
    vehicle_id: str
    stops: list[PlannedStop] = field(default_factory=list)
    distance_m: int = 0
    duration_s: int = 0
    load_kg: float = 0.0


@dataclass
class Plan:
    status: str
    routes: list[VehicleRoute]
    dropped: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    @property
    def distance_m(self) -> int:
        return sum(r.distance_m for r in self.routes)

    @property
    def visited_ids(self) -> list[str]:
        return [s.stop_id for r in self.routes for s in r.stops]


def _status_name(code: int) -> str:
    try:
        return routing_enums_pb2.RoutingSearchStatus.Value.Name(code).removeprefix("ROUTING_").lower()
    except (AttributeError, ValueError):
        return str(code)


def solve(dist: list[list[int]], dur: list[list[int]], stops: list[StopIn], vehicles: list[VehicleIn],
          end_node: int | None = None, time_limit_s: float = 5.0) -> Plan:
    """end_node: unloading facility shared by all vehicles; None = each vehicle returns to its depot."""
    if not vehicles:
        return Plan("no_vehicles", [], {s.id: "no_vehicle_available" for s in stops})
    empty_routes = [VehicleRoute(v.id) for v in vehicles]
    dropped: dict[str, str] = {}
    max_cap = max(v.capacity_kg for v in vehicles)
    usable: list[StopIn] = []
    for s in stops:
        reachable = any(dist[v.start_node][s.node] < UNREACHABLE_M for v in vehicles) and (
            end_node is None or dist[s.node][end_node] < UNREACHABLE_M)
        if s.demand_kg > max_cap:
            dropped[s.id] = "exceeds_vehicle_capacity"
        elif not reachable:
            dropped[s.id] = "unreachable"
        else:
            usable.append(s)
    if not usable:
        return Plan("empty" if not stops else "nothing_feasible", empty_routes, dropped)

    # Local node list: vehicle depots, optional shared end, then stops.
    local: list[int] = [v.start_node for v in vehicles]
    end_local = None
    if end_node is not None:
        end_local = len(local)
        local.append(end_node)
    stop_local0 = len(local)
    local += [s.node for s in usable]
    starts = list(range(len(vehicles)))
    ends = [end_local] * len(vehicles) if end_local is not None else starts
    by_local = {stop_local0 + i: s for i, s in enumerate(usable)}

    def build(mandatory_soft: bool):
        manager = pywrapcp.RoutingIndexManager(len(local), len(vehicles), starts, ends)
        routing = pywrapcp.RoutingModel(manager)

        def dist_cb(i, j):
            return dist[local[manager.IndexToNode(i)]][local[manager.IndexToNode(j)]]

        def time_cb(i, j):
            a = manager.IndexToNode(i)
            service = by_local[a].service_s if a in by_local else 0
            return dur[local[a]][local[manager.IndexToNode(j)]] + service

        def demand_cb(i):
            s = by_local.get(manager.IndexToNode(i))
            return round(s.demand_kg * DEMAND_SCALE) if s else 0

        dist_idx = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(dist_idx)
        routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(demand_cb), 0,
                                                [round(v.capacity_kg * DEMAND_SCALE) for v in vehicles], True, "Load")
        horizon = max(v.max_duration_s for v in vehicles)
        routing.AddDimension(routing.RegisterTransitCallback(time_cb), horizon, horizon, True, "Time")
        time_dim = routing.GetDimensionOrDie("Time")
        for vi, v in enumerate(vehicles):
            time_dim.CumulVar(routing.End(vi)).SetMax(v.max_duration_s)
        for loc, s in by_local.items():
            index = manager.NodeToIndex(loc)
            if s.window:
                time_dim.CumulVar(index).SetRange(max(0, s.window[0]), min(horizon, s.window[1]))
            if not s.mandatory:
                routing.AddDisjunction([index], DROP_PENALTY_PER_PRIORITY * max(1, min(5, s.priority)))
            elif mandatory_soft:
                routing.AddDisjunction([index], MANDATORY_FALLBACK_PENALTY)
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromMilliseconds(max(200, int(time_limit_s * 1000)))
        return manager, routing, time_dim, routing.SolveWithParameters(params)

    warnings: list[str] = []
    manager, routing, time_dim, solution = build(mandatory_soft=False)
    if solution is None and any(s.mandatory for s in usable):
        manager, routing, time_dim, solution = build(mandatory_soft=True)
        warnings.append("Not every emergency stop fits within capacity/time; see dropped stops.")
    if solution is None:
        dropped.update({s.id: "infeasible" for s in usable})
        return Plan("infeasible", empty_routes, dropped, warnings)

    load_dim = routing.GetDimensionOrDie("Load")
    routes: list[VehicleRoute] = []
    visited: set[str] = set()
    for vi, v in enumerate(vehicles):
        r = VehicleRoute(v.id)
        index = routing.Start(vi)
        prev = local[manager.IndexToNode(index)]
        index = solution.Value(routing.NextVar(index))
        while not routing.IsEnd(index):
            loc = manager.IndexToNode(index)
            s = by_local[loc]
            leg = dist[prev][s.node]
            r.stops.append(PlannedStop(s.id, solution.Min(time_dim.CumulVar(index)),
                                       (solution.Value(load_dim.CumulVar(index)) + round(s.demand_kg * DEMAND_SCALE)) / DEMAND_SCALE,
                                       leg))
            r.distance_m += leg
            visited.add(s.id)
            prev = s.node
            index = solution.Value(routing.NextVar(index))
        if r.stops:
            r.distance_m += dist[prev][local[manager.IndexToNode(index)]]
            r.duration_s = solution.Min(time_dim.CumulVar(index))
            r.load_kg = r.stops[-1].load_after_kg
        routes.append(r)
    for s in usable:
        if s.id not in visited:
            dropped[s.id] = "mandatory_unscheduled" if s.mandatory else "insufficient_capacity_or_time"
    return Plan(_status_name(routing.status()), routes, dropped, warnings)


def baseline_distance(dist: list[list[int]], stops: list[StopIn], vehicles: list[VehicleIn], end_node: int | None = None) -> int | None:
    """Unoptimised reference on the SAME matrix and SAME stop set: visit stops in the given (e.g. code) order,
    filling vehicles one after another. None when the fixed order cannot carry every stop."""
    total, vi, load = 0, 0, 0.0
    if not stops:
        return 0
    if not vehicles:
        return None
    pos = vehicles[0].start_node
    for s in stops:
        if load + s.demand_kg > vehicles[vi].capacity_kg:
            total += dist[pos][end_node if end_node is not None else vehicles[vi].start_node]
            vi += 1
            if vi >= len(vehicles):
                return None
            pos, load = vehicles[vi].start_node, 0.0
        total += dist[pos][s.node]
        pos, load = s.node, load + s.demand_kg
    total += dist[pos][end_node if end_node is not None else vehicles[vi].start_node]
    return total
