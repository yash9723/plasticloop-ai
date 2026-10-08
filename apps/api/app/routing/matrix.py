"""Distance/duration matrices.

With OSRM_URL set, road distances come from a self-hosted OSRM `/table` service. Otherwise distances are a
great-circle (haversine) estimate multiplied by a rural detour factor, and every route says so
(`distance_basis = "haversine_estimate"`). Estimates are never presented as road distances.
"""

import json
import math
import urllib.error
import urllib.request

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("app.routing")
EARTH_RADIUS_M = 6_371_000
DETOUR_FACTOR = 1.3  # ASSUMPTION: rural roads are ~30% longer than the straight line; tune per district.
UNREACHABLE_M = 10**9

Point = tuple[float, float]  # (lat, lng)


def haversine_m(a: Point, b: Point) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def distance_basis() -> str:
    return "osrm_road" if settings.osrm_url else "haversine_estimate"


def _estimate(points: list[Point], speed_kmph: float) -> tuple[list[list[int]], list[list[int]]]:
    speed_ms = speed_kmph * 1000 / 3600
    dist = [[round(haversine_m(a, b) * DETOUR_FACTOR) for b in points] for a in points]
    dur = [[round(d / speed_ms) for d in row] for row in dist]
    return dist, dur


def _osrm(points: list[Point]) -> tuple[list[list[int]], list[list[int]]]:
    coords = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    url = f"{settings.osrm_url.rstrip('/')}/table/v1/driving/{coords}?annotations=distance,duration"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - operator-configured URL
        body = json.loads(resp.read())
    if body.get("code") != "Ok":
        raise ValueError(f"OSRM error: {body.get('code')}")
    # OSRM returns null for unreachable pairs; keep them so the solver can drop those stops explicitly.
    dist = [[UNREACHABLE_M if v is None else round(v) for v in row] for row in body["distances"]]
    dur = [[UNREACHABLE_M if v is None else round(v) for v in row] for row in body["durations"]]
    return dist, dur


def build_matrix(points: list[Point], speed_kmph: float | None = None) -> tuple[list[list[int]], list[list[int]], str, list[str]]:
    """Returns (distance_m, duration_s, basis, warnings)."""
    speed = speed_kmph or settings.routing_avg_speed_kmph
    if settings.osrm_url and len(points) > 1:
        try:
            dist, dur = _osrm(points)
            return dist, dur, "osrm_road", []
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            log.warning("osrm_unavailable", extra={"fields": {"error": str(exc)[:200]}})
            dist, dur = _estimate(points, speed)
            return dist, dur, "haversine_estimate", ["OSRM unavailable; distances are straight-line estimates × 1.3"]
    dist, dur = _estimate(points, speed)
    return dist, dur, "haversine_estimate", []
