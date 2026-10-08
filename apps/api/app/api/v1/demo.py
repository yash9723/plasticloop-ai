"""Demo-mode helpers. Every endpoint here returns 404 unless DEMO_MODE is on in a non-production environment."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.errors import AppError, bad_request
from app.models.enums import RoleKey
from app.security.deps import DB, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit
from app.services.telemetry import StatusIn, TelemetryIn, handle_status, ingest

router = APIRouter()


def ensure_demo() -> None:
    if not settings.demo_enabled:
        raise AppError(404, "DEMO_DISABLED", "Demo mode is not enabled on this deployment")


@router.get("/status", summary="Is this a demo deployment?")
def status():
    return {
        "demo_mode": settings.demo_enabled,
        "environment": settings.environment,
        "notice": "All demo records are synthetic. Simulated outcomes are not evidence of real-world recycling."
        if settings.demo_enabled
        else None,
    }


@router.get("/accounts", summary="Demo sign-in accounts (development/test only)")
def accounts():
    ensure_demo()
    from app.scripts.seed_demo import DEMO_ACCOUNTS, DEMO_PASSWORD

    return {"password": DEMO_PASSWORD, "accounts": [{"email": e, "role": r, "label": label} for e, r, label in DEMO_ACCOUNTS]}


class SimulateIn(BaseModel):
    weight_kg: float | None = Field(None, ge=-50, le=10000)
    fill_percent: float | None = Field(None, ge=0, le=100)
    battery_percent: int | None = Field(None, ge=0, le=100)
    sensor_status: str = Field("ok", max_length=40)
    go_offline: bool = Field(False, description="Simulate the broker's last-will 'offline' message instead of a reading")


@router.post("/devices/{device_pk}/simulate", summary="Inject SIMULATED telemetry through the real ingestion service")
def simulate(device_pk: uuid.UUID, body: SimulateIn, db: DB,
             principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.EVALUATOR))):
    ensure_demo()
    from app.api.v1.devices import ReadingOut, _get_visible

    device = _get_visible(db, device_pk, principal)
    if not device.is_simulated:
        raise bad_request("NOT_SIMULATED", "Only devices registered as simulated accept simulator input")
    if body.go_offline:
        handle_status(db, device, StatusIn(status="offline"))
        db.commit()
        return {"status": "offline", "device_id": device.device_id}
    data = TelemetryIn(device_id=device.device_id, reading_id=f"sim-{uuid.uuid4().hex[:16]}", timestamp=utcnow(),
                       weight_kg=body.weight_kg, fill_percent=body.fill_percent, battery_percent=body.battery_percent,
                       sensor_status=body.sensor_status, firmware_version="simulator", synthetic=True)
    reading, _ = ingest(db, device, data, transport="simulator")
    audit(db, principal, "demo.telemetry_simulated", "device", device.id, after={"reading_id": data.reading_id})
    db.commit()
    db.refresh(reading)
    return {"status": "accepted", "reading": ReadingOut.model_validate(reading)}


@router.get("/walkthrough", summary="Guided demo: the 12 steps and what each one produced")
def walkthrough(db: DB, principal: Principal = Depends(require(RoleKey.EVALUATOR, RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR))):
    ensure_demo()
    from app.services import demo_walkthrough

    return {"steps": demo_walkthrough.status(db),
            "notice": "Every step runs the real services as the matching demo account. All records it creates are synthetic."}


@router.post("/walkthrough/reset", summary="Forget walkthrough progress (created records stay, labelled synthetic)")
def walkthrough_reset(db: DB, principal: Principal = Depends(require(RoleKey.EVALUATOR, RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR))):
    ensure_demo()
    from app.services import demo_walkthrough

    demo_walkthrough.reset(db, principal.id)
    audit(db, principal, "demo.walkthrough_reset", "demo_walkthrough", None)
    db.commit()
    return {"steps": demo_walkthrough.status(db)}


@router.post("/walkthrough/{n}", summary="Run one guided-demo step")
def walkthrough_step(n: int, db: DB, principal: Principal = Depends(require(RoleKey.EVALUATOR, RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR))):
    ensure_demo()
    from app.services import demo_walkthrough

    out = demo_walkthrough.run_step(db, n, principal)
    db.commit()
    return out
