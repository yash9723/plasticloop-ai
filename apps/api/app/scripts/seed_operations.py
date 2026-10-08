"""Synthetic demo data for devices, logistics, MRF inventory, recovery and finance.

Called by seed_demo.Seeder.run() after identity/collection data exists. Each section uses the same services as the
API, so ledger and inventory invariants hold for demo data exactly as for live data.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update

from app.iot.mqtt_auth import demo_device_key, provision_credentials
from app.models import (
    CollectionEvent,
    Device,
    Expense,
    Facility,
    MaterialBatch,
    MaterialCategory,
    MaterialListing,
    MaterialOffer,
    Payment,
    ProcessingPartner,
    Route,
    Sale,
    Vehicle,
)
from app.models.enums import (
    BatchStatus,
    ConnectionStatus,
    DataOrigin,
    DeviceType,
    DocumentationStatus,
    ExpenseCategory,
    FacilityType,
    ListingStatus,
    MediaPurpose,
    MovementType,
    OfferStatus,
    OutcomeType,
    PaymentStatus,
    RoleKey,
    RouteStatus,
    StopStatus,
    VehicleType,
)
from app.security.scope import AccessScope
from app.services import inventory, recovery, route_planner
from app.services.media import store_bytes
from app.services.telemetry import TelemetryIn, ingest, record_calibration

# device_id, village, community-bin index, type, hours since last report, battery at end, calibrated
DEVICES = [
    ("DEV-ESP32-001", "VNP", -1, DeviceType.COMBO_NODE, 0, 78, True),
    ("DEV-ESP32-002", "VNP", -2, DeviceType.FILL_SENSOR, 0, 17, True),
    ("DEV-ESP32-003", "PCP", -1, DeviceType.WEIGHING_SCALE, 0, 64, False),
    ("DEV-ESP32-004", "NGT", -1, DeviceType.COMBO_NODE, 3, 41, True),
]


def devices(seeder) -> int:
    db, now, rng = seeder.db, seeder.now, seeder.rng
    n = 0
    for device_id, village, idx, dtype, silent_h, battery_end, calibrated in DEVICES:
        cp = [p for p in seeder.points[village] if p.point_type == "community_bin"][idx]
        d = Device(device_id=device_id, device_type=dtype, organization_id=seeder.villages[village].organization_id,
                   collection_point_id=cp.id, is_simulated=True, firmware_version="sim-1.0.0",
                   weight_max_kg=Decimal("150"), bin_depth_cm=90.0, telemetry_interval_s=1800,
                   notes="SIMULATED demo device (no physical hardware).")
        db.add(d)
        db.flush()
        provision_credentials(db, d, key=demo_device_key(device_id))
        if calibrated:
            record_calibration(db, d, method="known_mass", result="pass", reference_mass_kg=10, scale_factor=21.7,
                               offset=-0.12, source="manual", notes="Synthetic calibration record")
        # Half-hourly readings over the last 24 h; the bin fills steadily and the battery drains.
        steps = 48 - silent_h * 2
        fill, weight = rng.uniform(20, 40), rng.uniform(8, 20)
        for i in range(steps):
            fill = min(100.0, fill + rng.uniform(0.4, 1.6))
            weight += rng.uniform(0.1, 0.9)
            sensor = "load_cell_error" if device_id == "DEV-ESP32-003" and i == steps - 5 else "ok"
            data = TelemetryIn(
                device_id=device_id, reading_id=f"seed-{device_id}-{i:03d}", timestamp=now - timedelta(minutes=30 * (48 - i)),
                weight_kg=None if dtype == DeviceType.FILL_SENSOR else round(weight, 3),
                fill_percent=None if dtype == DeviceType.WEIGHING_SCALE else round(fill, 1),
                battery_percent=round(100 - (100 - battery_end) * (i + 1) / steps), sensor_status=sensor,
                firmware_version="sim-1.0.0", synthetic=True,
            )
            ingest(db, d, data, transport="simulator")
            n += 1
        d.last_seen_at = now - timedelta(hours=silent_h, minutes=30)
        d.connection_status = ConnectionStatus.OFFLINE if silent_h else ConnectionStatus.ONLINE
    db.flush()
    return n


def facilities_and_partners(seeder) -> None:
    from app.scripts.seed_demo import DOMAIN

    db, op = seeder.db, seeder.orgs["operator"]
    mrf = Facility(organization_id=op.id, name="Cluster MRF, Vanapuram (synthetic)", code="MRF-VNP", facility_type=FacilityType.MRF,
                   lat=17.9450, lng=78.8700, address="Synthetic location for demonstration", capacity_kg_per_day=Decimal("1500"),
                   storage_locations=["Bay A", "Bay B", "Bale yard"], is_sample=True)
    pwmu = Facility(organization_id=op.id, name="Block PWMU, Neelagiri (synthetic)", code="PWMU-NGT", facility_type=FacilityType.PWMU,
                    lat=17.9900, lng=78.9300, address="Synthetic location for demonstration", capacity_kg_per_day=Decimal("800"),
                    storage_locations=["Shed 1", "Shed 2"], is_sample=True)
    db.add_all([mrf, pwmu])
    db.flush()
    seeder.facilities = {"VNP": mrf, "PCP": mrf, "NGT": pwmu}
    for code, fac in seeder.facilities.items():
        seeder.villages[code].facility_id = fac.id
    seeder.user(f"mrf.operator@{DOMAIN}", "Kiran Kumar (MRF supervisor, demo)", RoleKey.MRF_OPERATOR, op)
    seeder.user(f"processor@{DOMAIN}", "Processing desk (fictional sample)", RoleKey.PROCESSOR, seeder.orgs["proc1"])
    seeder.partners = {
        "proc1": ProcessingPartner(
            organization_id=seeder.orgs["proc1"].id, display_name=seeder.orgs["proc1"].name, is_sample=True,
            supported_category_codes=["rigid_plastic", "flexible_plastic", "suspected_mlp"],
            capabilities="FICTIONAL SAMPLE PARTNER: mechanical recycling of rigid and flexible plastics.",
            acceptance_criteria="Dry, baled, contamination below 5% (sample criteria).", lat=17.8800, lng=78.9900,
            contact_name="Sample contact", documentation_status=DocumentationStatus.NOT_SUBMITTED),
        "proc2": ProcessingPartner(
            organization_id=seeder.orgs["proc2"].id, display_name=seeder.orgs["proc2"].name, is_sample=True,
            supported_category_codes=["suspected_mlp", "nonrecoverable"],
            capabilities="FICTIONAL SAMPLE PARTNER: co-processing of non-recyclable and multilayer plastic.",
            acceptance_criteria="Shredded, moisture below 10% (sample criteria).", lat=17.8200, lng=78.8600,
            contact_name="Sample contact", documentation_status=DocumentationStatus.SUBMITTED),
    }
    db.add_all(seeder.partners.values())
    db.flush()


# name, registration, village, type, capacity kg, driver key
VEHICLES = [
    ("E-cart VNP-1 (demo)", "DEMO-VNP-01", "VNP", VehicleType.E_CART, 350, "driver.vanapuram"),
    ("Auto VNP-2 (demo)", "DEMO-VNP-02", "VNP", VehicleType.AUTO_RICKSHAW, 500, None),
    ("Tractor PCP-1 (demo)", "DEMO-PCP-01", "PCP", VehicleType.TRACTOR_TROLLEY, 1200, "driver.pachchapalli"),
    ("Mini truck NGT-1 (demo)", "DEMO-NGT-01", "NGT", VehicleType.MINI_TRUCK, 1500, None),
]


def vehicles_and_routes(seeder) -> int:
    db, now = seeder.db, seeder.now
    seeder.vehicles = {}
    for name, reg, village, vtype, cap, driver in VEHICLES:
        v = seeder.villages[village]
        veh = Vehicle(organization_id=v.organization_id, registration_no=reg, name=name, vehicle_type=vtype, capacity_kg=Decimal(cap),
                      depot_name=f"Panchayat yard, {v.name}", depot_lat=v.lat, depot_lng=v.lng, cost_per_km_paise=1200 if cap < 600 else 2200,
                      driver_id=seeder.users[driver].id if driver else None, is_sample=True)
        db.add(veh)
        seeder.vehicles.setdefault(village, []).append(veh)
    db.flush()
    scope = AccessScope(user_id=seeder.gp_admin("VNP").id, roles=frozenset(), is_super=True)
    n = 0
    # Today's optimised plan for Vanapuram and yesterday's (completed) plan for Pachchapalli — same planner as the UI.
    for village, day, finish in (("VNP", now.date(), False), ("PCP", (now - timedelta(days=1)).date(), True)):
        result = route_planner.plan_routes(
            db, scope, seeder.gp_admin(village).id, vehicle_ids=[x.id for x in seeder.vehicles[village]], planned_date=day,
            village_ids=[seeder.villages[village].id], facility_id=seeder.facilities[village].id, time_limit_s=1, save=True)
        for rid in result["saved_route_ids"]:
            n += 1
            if finish:
                route = db.get(Route, rid)
                db.refresh(route)
                route.status, route.started_at = RouteStatus.COMPLETED, datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=2)
                route.completed_at = route.started_at + timedelta(seconds=route.duration_s + 1800)
                for i, stop in enumerate(route.stops):
                    skipped = i == 2
                    stop.status = StopStatus.SKIPPED if skipped else StopStatus.COMPLETED
                    stop.skip_reason = "Gate locked at institution (synthetic example)" if skipped else None
                    stop.completed_at = route.started_at + timedelta(seconds=stop.planned_arrival_s)
                route.actual_load_kg = (route.load_kg * Decimal("0.88")).quantize(Decimal("0.001"))
    db.flush()
    return n


SORT_SHARES = [("rigid_plastic", 0.30, 0.38), ("flexible_plastic", 0.18, 0.25), ("suspected_mlp", 0.15, 0.22),
               ("paper_cardboard", 0.05, 0.08), ("metal", 0.01, 0.03), ("contamination_rejects", 0.08, 0.12)]


def intakes_and_inventory(seeder, days: int = 46) -> dict:
    db, rng, now = seeder.db, seeder.rng, seeder.now
    operator = seeder.users["mrf.operator"]
    cats = {c.code: c for c in db.scalars(select(MaterialCategory))}
    start = now - timedelta(days=days)
    day_col = func.date_trunc("day", CollectionEvent.collected_at)
    rows = db.execute(select(CollectionEvent.village_id, day_col, func.sum(CollectionEvent.weight_kg))
                      .where(CollectionEvent.collected_at >= start).group_by(CollectionEvent.village_id, day_col)
                      .order_by(day_col)).all()
    code_by_village = {v.id: code for code, v in seeder.villages.items()}
    stats = {"intakes": 0, "sorted": 0}
    for village_id, day, declared in rows:
        code = code_by_village[village_id]
        fac = seeder.facilities[code]
        received = day + timedelta(hours=13)
        net = (Decimal(str(declared)) * Decimal(str(round(rng.uniform(0.93, 1.0), 3)))).quantize(Decimal("0.1"))
        tare = Decimal(str(round(rng.uniform(15, 40), 1)))
        vehicle = seeder.vehicles[code][0]
        intake = inventory.record_intake(db, fac, operator.id, gross_kg=net + tare, tare_kg=tare, received_at=received,
                                         origin_village_id=village_id, vehicle_id=vehicle.id, transporter_name=vehicle.name,
                                         declared_collected_kg=declared, storage_location=fac.storage_locations[0],
                                         notes="Synthetic demo delivery", origin=DataOrigin.DEMO_SEED)
        db.execute(update(CollectionEvent).where(CollectionEvent.village_id == village_id, CollectionEvent.collected_at >= day,
                                                 CollectionEvent.collected_at < day + timedelta(days=1))
                   .values(facility_intake_id=intake.id))
        stats["intakes"] += 1
        if received < now - timedelta(days=2):
            sorted_share = Decimal(str(round(rng.uniform(0.975, 0.997), 3)))  # small, visible sorting differences
            shares = [(c, rng.uniform(lo, hi)) for c, lo, hi in SORT_SHARES]
            total = sum(s for _, s in shares)
            outputs = [{"category_id": cats[c].id, "weight_kg": (net * sorted_share * Decimal(str(s / total))).quantize(Decimal("0.01")),
                        "storage_location": fac.storage_locations[-1]} for c, s in shares]
            outputs = [o for o in outputs if o["weight_kg"] > 0]
            inventory.sort_batch(db, intake.batch_id, outputs, operator.id, at=received + timedelta(hours=20),
                                 notes="Hand-sorted on picking table (synthetic)")
            stats["sorted"] += 1
    db.flush()
    flexible = db.scalar(select(MaterialBatch).join(MaterialCategory).where(MaterialCategory.code == "flexible_plastic",
                                                                            MaterialBatch.status == BatchStatus.ACTIVE).limit(1))
    if flexible:
        inventory.adjust_batch(db, flexible.id, MovementType.LOSS, Decimal("0.8"), "Moisture loss after sun-drying (synthetic)",
                               operator.id, at=now - timedelta(days=1))
    return stats


def _synthetic_evidence_pdf(seeder, title: str):
    """A clearly labelled placeholder document so the evidence-review workflow can be demonstrated."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "SYNTHETIC SAMPLE EVIDENCE - NOT A REAL DOCUMENT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, f"{title}\nGenerated by the PlasticLoop AI demo seed. It demonstrates the evidence-review workflow only.")
    return store_bytes(seeder.db, bytes(pdf.output()), MediaPurpose.OUTCOME_EVIDENCE, seeder.users["processor"].id,
                       "synthetic-evidence.pdf", DataOrigin.DEMO_SEED)


def recovery_market_finance(seeder) -> dict:
    db, now = seeder.db, seeder.now
    operator, processor = seeder.users["mrf.operator"], seeder.users["processor"]
    mrf = seeder.facilities["VNP"]
    proc1 = seeder.partners["proc1"]
    proc1.supported_category_codes = ["rigid_plastic", "flexible_plastic", "suspected_mlp", "paper_cardboard"]
    db.flush()
    stats = {"transfers": 0, "outcomes": 0, "sales": 0, "expenses": 0}

    def old_batches(code: str, older_than_days: int) -> list:
        return list(db.scalars(select(MaterialBatch).join(MaterialCategory).where(
            MaterialBatch.facility_id == mrf.id, MaterialCategory.code == code, MaterialBatch.status == BatchStatus.ACTIVE,
            MaterialBatch.created_at < now - timedelta(days=older_than_days)).order_by(MaterialBatch.created_at)))

    # 1) Suspected MLP → partner (the demo processor account belongs to proc1): dispatched, received, decided, outcome with (synthetic) evidence, reviewed.
    mlp = old_batches("suspected_mlp", 12)
    if len(mlp) >= 2:
        _, merged = inventory.merge_batches(db, [b.id for b in mlp], operator.id, notes="Baled for dispatch (synthetic)")
        kg = (merged.current_weight_kg * Decimal("0.9")).quantize(Decimal("0.1"))
        t, _ = recovery.allocate(db, merged.id, proc1.id, kg, operator.id, transporter_name="Sample Transport Co. (fictional)", vehicle_no="DEMO-TR-01")
        recovery.dispatch(db, t.id, operator.id, at=now - timedelta(days=9))
        recovery.receive(db, t.id, kg - Decimal("1.2"), processor.id, receipt_reference="GRN-DEMO-0001", at=now - timedelta(days=8))
        accepted = (kg - Decimal("1.2") - Decimal("3.0")).quantize(Decimal("0.1"))
        recovery.decide(db, t.id, accepted, Decimal("3.0"), processor.id, rejection_reason="Wet, mixed with organic waste (synthetic)",
                        at=now - timedelta(days=8))
        media = _synthetic_evidence_pdf(seeder, f"Co-processing record for {t.code}")
        o = recovery.record_outcome(db, t.id, processor.id, outcome_type=OutcomeType.RECOVERED_DOCUMENTED_PROCESS, input_kg=accepted,
                                    output_kg=accepted, process_date=(now - timedelta(days=5)).date(),
                                    attested_by_name="Plant manager (fictional)", evidence_media_id=media.id,
                                    process_description="Co-processed as alternative fuel (fictional sample partner)", at=now - timedelta(days=5))
        recovery.review_outcome(db, o.id, "accept", "Synthetic demo review of a synthetic document", operator.id)
        stats["transfers"] += 1
        stats["outcomes"] += 1

    # 2) Rigid plastic → recycler: received, awaiting the processor's accept/reject decision.
    rigid = old_batches("rigid_plastic", 10)
    if len(rigid) >= 2:
        _, merged = inventory.merge_batches(db, [b.id for b in rigid], operator.id, notes="Baled (synthetic)")
        t, _ = recovery.allocate(db, merged.id, proc1.id, merged.current_weight_kg, operator.id, transporter_name="Sample Transport Co. (fictional)")
        recovery.dispatch(db, t.id, operator.id, at=now - timedelta(days=3))
        recovery.receive(db, t.id, merged.initial_weight_kg - Decimal("0.4"), processor.id, at=now - timedelta(days=2))
        stats["transfers"] += 1

    # 3) Flexible film: allocated, waiting to be dispatched.
    film = old_batches("flexible_plastic", 7)
    if film:
        recovery.allocate(db, film[0].id, proc1.id, film[0].current_weight_kg, operator.id)
        stats["transfers"] += 1

    # 4) Marketplace: paper sold (part-paid), metal listed with a quote request. Prices are hypothetical samples.
    buyer = seeder.orgs["proc1"]
    paper = old_batches("paper_cardboard", 5)
    if len(paper) >= 2:
        _, merged = inventory.merge_batches(db, [b.id for b in paper], operator.id)
        listing = MaterialListing(facility_id=mrf.id, batch_id=merged.id, category_id=merged.category_id, quantity_kg=merged.current_weight_kg,
                                  asking_price_paise_per_kg=800, price_is_hypothetical=True, quality_notes="Dry, baled (synthetic)",
                                  status=ListingStatus.SOLD, created_by=operator.id, data_origin=DataOrigin.DEMO_SEED)
        db.add(listing)
        db.flush()
        offer = MaterialOffer(listing_id=listing.id, buyer_org_id=buyer.id, kind="offer", quantity_kg=merged.current_weight_kg,
                              price_paise_per_kg=750, status=OfferStatus.ACCEPTED, created_by=processor.id, responded_by=operator.id,
                              data_origin=DataOrigin.DEMO_SEED)
        db.add(offer)
        db.flush()
        qty = merged.current_weight_kg
        sale = Sale(listing_id=listing.id, offer_id=offer.id, batch_id=merged.id, facility_id=mrf.id, buyer_org_id=buyer.id, quantity_kg=qty,
                    unit_price_paise=750, total_paise=int(qty * 750), sold_on=(now - timedelta(days=4)).date(), invoice_number="DEMO-INV-001",
                    payment_status=PaymentStatus.PARTIALLY_PAID, created_by=operator.id, data_origin=DataOrigin.DEMO_SEED)
        db.add(sale)
        db.flush()
        inventory._move(db, merged, MovementType.TRANSFER_OUT, -qty, operator.id, reference_type="sale", reference_id=sale.id,
                        reason="Sold (synthetic)", at=now - timedelta(days=4))
        db.add(Payment(sale_id=sale.id, amount_paise=sale.total_paise // 2, paid_on=(now - timedelta(days=2)).date(), method="bank_transfer",
                       reference="DEMO-UTR-001", recorded_by=operator.id, data_origin=DataOrigin.DEMO_SEED))
        stats["sales"] += 1
    metal = old_batches("metal", 3)
    if metal:
        listing = MaterialListing(facility_id=mrf.id, batch_id=metal[0].id, category_id=metal[0].category_id,
                                  quantity_kg=metal[0].current_weight_kg, asking_price_paise_per_kg=2500, price_is_hypothetical=True,
                                  created_by=operator.id, data_origin=DataOrigin.DEMO_SEED)
        db.add(listing)
        db.flush()
        db.add(MaterialOffer(listing_id=listing.id, buyer_org_id=buyer.id, kind="quote_request", quantity_kg=metal[0].current_weight_kg,
                             status=OfferStatus.QUOTE_REQUESTED, message="Please share a price for the full lot (synthetic)",
                             created_by=processor.id, data_origin=DataOrigin.DEMO_SEED))

    # 5) Expenses: recorded monthly costs plus one clearly marked estimate.
    for code in ("VNP", "PCP", "NGT"):
        org_id = seeder.villages[code].organization_id
        for back, cat, amount in ((40, ExpenseCategory.COLLECTION_LABOR, 1800000), (25, ExpenseCategory.FUEL_VEHICLE, 420000),
                                  (10, ExpenseCategory.COLLECTION_LABOR, 1800000), (6, ExpenseCategory.EQUIPMENT_MAINTENANCE, 150000)):
            db.add(Expense(organization_id=org_id, category=cat, amount_paise=amount, incurred_on=(now - timedelta(days=back)).date(),
                           description="Synthetic sample expense", village_id=seeder.villages[code].id, recorded_by=seeder.gp_admin(code).id,
                           data_origin=DataOrigin.DEMO_SEED))
            stats["expenses"] += 1
    db.add(Expense(organization_id=seeder.orgs["operator"].id, category=ExpenseCategory.FACILITY_OPERATIONS, amount_paise=2500000,
                   incurred_on=(now - timedelta(days=15)).date(), facility_id=mrf.id, is_estimate=True,
                   assumption_note="ASSUMPTION: 2 sorting staff × 25 days × ₹500/day (synthetic estimate)", recorded_by=operator.id,
                   data_origin=DataOrigin.DEMO_SEED))
    stats["expenses"] += 1
    db.flush()
    return stats


def run(seeder) -> dict:
    out = {"devices": len(DEVICES), "device_readings": devices(seeder)}
    facilities_and_partners(seeder)
    out["routes"] = vehicles_and_routes(seeder)
    out.update(intakes_and_inventory(seeder))
    out.update(recovery_market_finance(seeder))
    return out
