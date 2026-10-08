"""12-step guided demo. Each step calls the same services the UI uses, acting as the matching demo account, inside one
transaction. Everything it creates is synthetic and labelled (simulated / demo_seed); nothing is evidence of real outcomes.

Progress lives in system_settings["demo_walkthrough"]; "reset" forgets progress (created records stay, still labelled).
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.adapters import get_adapter
from app.core.errors import bad_request, conflict
from app.models import (
    CollectionPoint,
    Device,
    Facility,
    Household,
    MaterialCategory,
    PickupRequest,
    ProcessingPartner,
    SystemSetting,
    User,
    Vehicle,
    VisionPrediction,
    VisionReview,
)
from app.models.enums import DataOrigin, MediaPurpose, OutcomeType
from app.schemas.collection import SyncBatchIn
from app.security.deps import Principal
from app.security.scope import build_scope
from app.security.tokens import utcnow
from app.services import inventory, recovery, route_planner, sync, system_settings
from app.services.audit import audit
from app.services.media import store_bytes
from app.services.notifications import notify, village_admins
from app.services.telemetry import TelemetryIn, ingest

KEY = "demo_walkthrough"
DOMAIN = "plasticloop.example"
STEPS = [
    ("request_pickup", "household"),
    ("bin_full", "device"),
    ("plan_route", "gp.vanapuram"),
    ("offline_collection", "collector1"),
    ("facility_intake", "mrf.operator"),
    ("sorting", "mrf.operator"),
    ("vision_review", "mrf.operator"),
    ("mlp_verification", "mrf.operator"),
    ("dispatch", "mrf.operator"),
    ("receive_accept", "processor"),
    ("outcome_evidence", "processor"),
    ("impact_report", "evaluator"),
]


def _state(db: Session) -> dict:
    row = db.get(SystemSetting, KEY)
    return row.value if row and isinstance(row.value, dict) else {"steps": {}, "ids": {}}


def _save(db: Session, state: dict, actor_id=None) -> None:
    row = db.get(SystemSetting, KEY)
    if row is None:
        db.add(SystemSetting(key=KEY, value=state, description="Guided demo progress (demo mode only)", updated_by=actor_id))
    else:
        row.value = dict(state)  # new object so SQLAlchemy sees the JSONB change
        row.updated_by = actor_id


def status(db: Session) -> list[dict]:
    st = _state(db)
    return [{"n": i + 1, "key": key, "actor": who, "done": str(i + 1) in st["steps"], **st["steps"].get(str(i + 1), {})}
            for i, (key, who) in enumerate(STEPS)]


def reset(db: Session, actor_id) -> None:
    _save(db, {"steps": {}, "ids": {}}, actor_id)


def _principal(db: Session, local: str) -> Principal:
    user = db.scalar(select(User).where(User.email == f"{local}@{DOMAIN}"))
    if user is None:
        raise conflict("DEMO_DATA_MISSING", "Demo accounts are missing; reset the demo data first (python -m app.scripts.seed_demo --reset)")
    return Principal(user=user, scope=build_scope(db, user))


def _pdf(title: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "SYNTHETIC SAMPLE EVIDENCE - NOT A REAL DOCUMENT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, f"{title}\nCreated by the PlasticLoop AI guided demo.")
    return bytes(pdf.output())


def _packet_image() -> bytes:
    """Synthetic 'foil packet' picture: saturated print with bright glints (no real photo is shipped)."""
    rng = np.random.default_rng(7)
    img = np.zeros((240, 320, 3), np.uint8)
    img[:] = (30, 30, 200)
    cv2.rectangle(img, (40, 40), (280, 200), (0, 200, 255), -1)
    for _ in range(60):
        x, y = int(rng.integers(40, 280)), int(rng.integers(40, 200))
        cv2.circle(img, (x, y), int(rng.integers(2, 6)), (255, 255, 255), -1)
    cv2.putText(img, "SYNTHETIC", (70, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 20), 3)
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def run_step(db: Session, n: int, requested_by: Principal) -> dict:
    if not 1 <= n <= len(STEPS):
        raise bad_request("UNKNOWN_STEP", "There are 12 steps")
    st = _state(db)
    if str(n) in st["steps"]:
        raise conflict("STEP_DONE", "This step already ran. Reset the walkthrough to run it again.")
    if n > 1 and str(n - 1) not in st["steps"]:
        raise conflict("PREVIOUS_STEP_PENDING", f"Run step {n - 1} first")
    ids = st["ids"]
    now = utcnow()
    result: dict = {}
    links: list[dict] = []
    mrf = db.scalar(select(Facility).where(Facility.code == "MRF-VNP"))

    if n == 1:
        p = _principal(db, "household")
        hh = db.scalar(select(Household).where(Household.user_id == p.id))
        cp = db.scalar(select(CollectionPoint).where(CollectionPoint.household_id == hh.id))
        pr = PickupRequest(village_id=hh.village_id, household_id=hh.id, collection_point_id=cp.id, requested_by=p.id,
                           estimated_weight_kg=Decimal("6"), notes="Guided demo request (synthetic)", data_origin=DataOrigin.SIMULATED)
        db.add(pr)
        db.flush()
        notify(db, village_admins(db, hh.village_id), type="pickup_requested", title=f"Pickup requested at {cp.code} (SIMULATED)",
               entity_type="pickup_request", entity_id=pr.id, link="/pickup-requests")
        ids.update(pickup_id=str(pr.id), point_id=str(cp.id), village_id=str(hh.village_id))
        result = {"point": cp.code, "estimated_kg": 6}
        links = [{"label": "pickup_requests", "href": "/pickup-requests"}]
    elif n == 2:
        device = db.scalar(select(Device).where(Device.device_id == "DEV-ESP32-001"))
        data = TelemetryIn(device_id=device.device_id, reading_id=f"demo-{uuid.uuid4().hex[:12]}", timestamp=now, weight_kg=31.5,
                           fill_percent=92, battery_percent=74, sensor_status="ok", firmware_version="simulator", synthetic=True)
        reading, _ = ingest(db, device, data, transport="simulator")
        result = {"device": device.device_id, "fill_percent": 92, "quality": str(reading.quality)}
        links = [{"label": "device", "href": f"/devices/{device.id}"}]
    elif n == 3:
        p = _principal(db, "gp.vanapuram")
        vehicles = [v.id for v in db.scalars(select(Vehicle).where(Vehicle.organization_id.in_(p.scope.org_ids), Vehicle.active.is_(True)))]
        plan = route_planner.plan_routes(db, p.scope, p.id, vehicle_ids=vehicles, planned_date=now.date() + timedelta(days=1),
                                         village_ids=[uuid.UUID(ids["village_id"])], facility_id=mrf.id if mrf else None,
                                         emergency_point_ids=[uuid.UUID(ids["point_id"])], time_limit_s=2, save=True)
        ids["route_ids"] = [str(r) for r in plan["saved_route_ids"]]
        result = {k: plan["totals"][k] for k in ("stops_planned", "distance_m", "baseline_distance_m", "savings_pct")}
        result["distance_basis"] = plan["distance_basis"]
        links = [{"label": "route", "href": f"/routes/{ids['route_ids'][0]}"}] if ids["route_ids"] else []
    elif n == 4:
        p = _principal(db, "collector1")
        cp = db.get(CollectionPoint, uuid.UUID(ids["point_id"]))
        stream = cp.streams[0]
        event_id = uuid.uuid4()
        payload = {"collection_point_id": str(cp.id), "waste_stream_id": str(stream.id), "weight_kg": "5.4", "measurement_source": "manual_entry",
                   "collected_at": (now - timedelta(minutes=40)).isoformat(), "pickup_request_id": ids["pickup_id"]}
        batch = SyncBatchIn(client_id="guided-demo-phone", events=[{"event_id": event_id, "payload": payload, "client_created_at": now - timedelta(minutes=40)}])
        first = sync.process_batch(db, p, batch)[0]
        again = sync.process_batch(db, p, batch)[0]  # the phone retries after a flaky connection
        ids["event_id"] = str(event_id)
        result = {"first_sync": str(first.status), "retry": str(again.status), "weight_kg": 5.4}
        links = [{"label": "collection", "href": f"/collections/{event_id}"}]
    elif n == 5:
        p = _principal(db, "mrf.operator")
        intake = inventory.record_intake(db, mrf, p.id, gross_kg=Decimal("58.4"), tare_kg=Decimal("6.2"), received_at=now,
                                         origin_village_id=uuid.UUID(ids["village_id"]), declared_collected_kg=Decimal("54.0"),
                                         storage_location="Bay A", notes="Guided demo delivery", origin=DataOrigin.SIMULATED)
        ids.update(intake_id=str(intake.id), unsorted_batch_id=str(intake.batch_id))
        result = {"net_kg": float(intake.net_kg), "declared_kg": 54.0}
        links = [{"label": "batch", "href": f"/inventory/{intake.batch_id}"}]
    elif n == 6:
        p = _principal(db, "mrf.operator")
        cats = {c.code: c.id for c in db.scalars(select(MaterialCategory))}
        outputs = [{"category_id": cats[c], "weight_kg": Decimal(w)} for c, w in
                   (("rigid_plastic", "18.5"), ("flexible_plastic", "12.3"), ("suspected_mlp", "11.8"), ("paper_cardboard", "5.1"), ("contamination_rejects", "4.0"))]
        op, children = inventory.sort_batch(db, uuid.UUID(ids["unsorted_batch_id"]), outputs, p.id, notes="Guided demo sorting")
        mlp = next(b for b in children if b.category_id == cats["suspected_mlp"])
        ids["mlp_batch_id"] = str(mlp.id)
        result = {"input_kg": float(op.input_kg), "output_kg": float(op.output_kg), "difference_kg": float(op.difference_kg),
                  "mlp_status": str(mlp.verification_status)}
        links = [{"label": "batch", "href": f"/inventory/{mlp.id}"}]
    elif n == 7:
        p = _principal(db, "mrf.operator")
        image = _packet_image()
        media = store_bytes(db, image, MediaPurpose.VISION_SAMPLE, p.id, "synthetic-packet.png", DataOrigin.SIMULATED)
        adapter = get_adapter()
        pred = adapter.predict(image)
        threshold = float(system_settings.get_value(db, "vision_confidence_threshold"))
        top = pred.top
        vp = VisionPrediction(media_id=media.id, requested_by=p.id, facility_id=mrf.id, batch_id=uuid.UUID(ids["mlp_batch_id"]), adapter=adapter.kind,
                              model_name=adapter.name, model_version=adapter.version, candidates=pred.candidates,
                              top_label=top["label"] if top else None, top_score=top["score"] if top else None, threshold=threshold,
                              low_confidence=top is None or top["score"] < threshold, inference_ms=round(pred.inference_ms, 2),
                              meta=pred.meta, data_origin=DataOrigin.SIMULATED)
        db.add(vp)
        db.flush()
        db.add(VisionReview(prediction_id=vp.id, reviewer_id=p.id, final_label="suspected_multilayer_packaging",
                            agrees_with_model=(vp.top_label == "suspected_multilayer_packaging") if vp.top_label else None,
                            notes="Guided demo review: foil-lined chip packet"))
        result = {"adapter": str(adapter.kind), "suggestion": vp.top_label, "score": vp.top_score, "low_confidence": vp.low_confidence,
                  "final_label": "suspected_multilayer_packaging"}
        links = [{"label": "review", "href": "/waste-classification/review"}]
    elif n == 8:
        p = _principal(db, "mrf.operator")
        media = store_bytes(db, _pdf("Burn/peel test record for MLP batch"), MediaPurpose.VERIFICATION_EVIDENCE, p.id, "synthetic-test.pdf",
                            DataOrigin.SIMULATED)
        batch = inventory.review_mlp(db, uuid.UUID(ids["mlp_batch_id"]), "verify", media.id,
                                     "Synthetic test record shows aluminium + polymer layers (guided demo)", p.id)
        result = {"verification_status": str(batch.verification_status)}
        links = [{"label": "batch", "href": f"/inventory/{batch.id}"}]
    elif n == 9:
        p = _principal(db, "mrf.operator")
        partner = db.scalar(select(ProcessingPartner).where(ProcessingPartner.organization_id.in_(_principal(db, "processor").scope.org_ids)))
        batch = inventory.lock_batch(db, uuid.UUID(ids["mlp_batch_id"]))
        t, warnings = recovery.allocate(db, batch.id, partner.id, batch.current_weight_kg, p.id, transporter_name="Demo transporter (fictional)")
        recovery.dispatch(db, t.id, p.id)
        ids["transfer_id"] = str(t.id)
        result = {"transfer": t.code, "kg": float(t.allocated_kg), "counted_as_recycled": False, "warnings": warnings}
        links = [{"label": "transfer", "href": f"/processing-transfers/{t.id}"}]
    elif n == 10:
        p = _principal(db, "processor")
        t = recovery.lock_transfer(db, uuid.UUID(ids["transfer_id"]))
        received = t.allocated_kg - Decimal("0.3")
        recovery.receive(db, t.id, received, p.id, receipt_reference="DEMO-GRN")
        recovery.decide(db, t.id, received, Decimal("0"), p.id)
        result = {"received_kg": float(received), "discrepancy_kg": 0.3, "accepted_kg": float(received)}
        links = [{"label": "transfer", "href": f"/processing-transfers/{t.id}"}]
    elif n == 11:
        p = _principal(db, "processor")
        reviewer = _principal(db, "mrf.operator")
        t = recovery.lock_transfer(db, uuid.UUID(ids["transfer_id"]))
        media = store_bytes(db, _pdf(f"Co-processing record for {t.code}"), MediaPurpose.OUTCOME_EVIDENCE, p.id, "synthetic-outcome.pdf",
                            DataOrigin.SIMULATED)
        o = recovery.record_outcome(db, t.id, p.id, outcome_type=OutcomeType.RECOVERED_DOCUMENTED_PROCESS, input_kg=t.accepted_kg,
                                    output_kg=t.accepted_kg, process_date=date.today(), attested_by_name="Demo plant manager (fictional)",
                                    evidence_media_id=media.id, process_description="Co-processed (guided demo, synthetic)")
        submitted = str(o.evidence_status)
        recovery.review_outcome(db, o.id, "accept", "Guided demo review of a synthetic document", reviewer.id)
        result = {"evidence_status_before_review": submitted, "evidence_status": str(o.evidence_status), "output_kg": float(o.output_kg)}
        links = [{"label": "recovery", "href": "/recovery"}]
    else:
        from app.api.v1.analytics import operations

        ops = operations(db, requested_by, now - timedelta(days=1), now + timedelta(minutes=1))
        result = {"funnel_last_24h": ops["funnel"]}
        links = [{"label": "analytics", "href": "/analytics"}, {"label": "reports", "href": "/reports"}]

    key, who = STEPS[n - 1]
    st["steps"][str(n)] = {"done_at": now.isoformat(), "result": result, "links": links}
    st["ids"] = ids
    _save(db, st, requested_by.id)
    audit(db, requested_by, f"demo.step_{n}.{key}", "demo_walkthrough", None, after={"as": who, **{k: str(v) for k, v in result.items()}})
    db.flush()
    return {"n": n, "key": key, "actor": who, "done": True, **st["steps"][str(n)]}
