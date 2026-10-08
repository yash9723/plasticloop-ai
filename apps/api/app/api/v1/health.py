import importlib

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.security.deps import DB

router = APIRouter()


@router.get("/live", summary="Process is up")
def live():
    return {"status": "ok"}


@router.get("/ready", summary="Database (with PostGIS) reachable")
def ready(db: DB):
    try:
        postgis = db.scalar(text("SELECT postgis_lib_version()"))
    except Exception as exc:  # noqa: BLE001 - report any DB failure as not-ready
        return JSONResponse({"status": "unavailable", "database": "error", "detail": type(exc).__name__}, status_code=503)
    return {"status": "ok", "database": "ok", "postgis": postgis}


def _component(module: str, fn: str):
    try:
        return getattr(importlib.import_module(module), fn)()
    except Exception as exc:  # noqa: BLE001 - report, never crash the health endpoint
        return {"status": "unavailable", "detail": type(exc).__name__}


@router.get("", summary="Component status (honest capability report)")
def health(db: DB):
    try:  # noqa: SIM105
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "error"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "environment": settings.environment,
        "demo_mode": settings.demo_enabled,
        "database": database,
        "vision": _component("app.ai.adapters", "active_adapter_info"),
        "routing_distance_basis": _component("app.routing.matrix", "distance_basis"),
        "mqtt_credentials_file": settings.mqtt_passwd_file.exists(),
    }
