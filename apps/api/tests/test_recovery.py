"""Processing transfers, evidence-gated outcomes, marketplace sales, finance and reports."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import MaterialCategory, MediaFile
from app.models.enums import MediaPurpose
from tests import factories as f

API = "/api/v1"


@pytest.fixture
def chain(db, client):
    op_org = f.org(db, "mrf_operator")
    fac = f.facility(db, op_org)
    gp = f.org(db)
    f.village(db, gp, fac)
    operator = f.user(db, "mrf_operator", op_org, facility_obj=fac)
    proc_org = f.org(db, "processor")
    partner = f.partner(db, proc_org)
    processor = f.user(db, "processor", proc_org)
    cats = {c.code: c for c in db.scalars(select(MaterialCategory))}
    oh = f.headers(operator)
    intake = client.post(f"{API}/facilities/{fac.id}/intakes", headers=oh, json={"gross_kg": "110", "tare_kg": "10"}).json()
    batches = client.post(f"{API}/inventory/batches/{intake['batch_id']}/sort", headers=oh, json={"version": 1, "outputs": [
        {"category_id": str(cats["suspected_mlp"].id), "weight_kg": "40"},
        {"category_id": str(cats["rigid_plastic"].id), "weight_kg": "30"},
        {"category_id": str(cats["paper_cardboard"].id), "weight_kg": "28"}]}).json()["batches"]
    by_cat = {b["category_code"]: b for b in batches}
    return {"facility": fac, "operator": operator, "processor": processor, "partner": partner, "oh": oh, "ph": f.headers(processor),
            "mlp": by_cat["suspected_mlp"], "rigid": by_cat["rigid_plastic"], "paper": by_cat["paper_cardboard"], "proc_org": proc_org}


def evidence(db, owner) -> str:
    m = MediaFile(owner_user_id=owner.id, purpose=MediaPurpose.OUTCOME_EVIDENCE, content_type="application/pdf", size_bytes=1,
                  sha256="1" * 64, storage_path="e.pdf")
    db.add(m)
    db.flush()
    return str(m.id)


def outcome_body(**kw):
    return {"outcome_type": "recycled_with_evidence", "input_kg": "30", "output_kg": "24", "process_date": date.today().isoformat(),
            "attested_by_name": "Plant supervisor", **kw}


def test_full_transfer_lifecycle_and_evidence_review(chain, client, db):
    oh, ph = chain["oh"], chain["ph"]
    t = client.post(f"{API}/processing-transfers", headers=oh, json={"batch_id": chain["mlp"]["id"], "partner_id": str(chain["partner"].id), "kg": "40"})
    assert t.status_code == 201, t.text
    t = t.json()
    assert t["status"] == "allocated" and t["warnings"]  # partner documents not reviewed yet
    t = client.post(f"{API}/processing-transfers/{t['id']}/dispatch", headers=oh, json={"version": t["version"]}).json()
    assert t["status"] == "dispatched"
    batch = client.get(f"{API}/inventory/batches/{chain['mlp']['id']}", headers=oh).json()
    assert batch["batch"]["current_weight_kg"] == 0 and batch["movements"][-1]["movement_type"] == "transfer_out"
    mb = client.get(f"{API}/facilities/{chain['facility'].id}/mass-balance", headers=oh).json()
    assert mb["transferred_out_kg"] == 40 and mb["ledger_consistent"]

    assert client.post(f"{API}/processing-transfers/{t['id']}/receive", headers=oh, json={"version": t["version"], "received_kg": "38"}).status_code == 403
    t = client.post(f"{API}/processing-transfers/{t['id']}/receive", headers=ph, json={"version": t["version"], "received_kg": "38"}).json()
    assert t["receipt_discrepancy_kg"] == 2 and t["discrepancy_flag"] is True  # 5% > 2% tolerance

    bad = client.post(f"{API}/processing-transfers/{t['id']}/decide", headers=ph, json={"version": t["version"], "accepted_kg": "35", "rejected_kg": "2"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "WEIGHTS_MUST_ADD_UP"
    t = client.post(f"{API}/processing-transfers/{t['id']}/decide", headers=ph, json={
        "version": t["version"], "accepted_kg": "35", "rejected_kg": "3", "rejection_reason": "Wet and mixed with soil", "return_rejected": True}).json()
    assert t["status"] == "partially_accepted" and t["returned_kg"] == 3

    no_ev = client.post(f"{API}/processing-transfers/{t['id']}/outcomes", headers=ph, json=outcome_body())
    assert no_ev.status_code == 400 and no_ev.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    too_much = client.post(f"{API}/processing-transfers/{t['id']}/outcomes", headers=ph, json=outcome_body(input_kg="36", evidence_media_id=evidence(db, chain["processor"])))
    assert too_much.status_code == 409
    o = client.post(f"{API}/processing-transfers/{t['id']}/outcomes", headers=ph, json=outcome_body(evidence_media_id=evidence(db, chain["processor"])))
    assert o.status_code == 201 and o.json()["evidence_status"] == "submitted"
    o = o.json()

    funnel = {s["stage"]: s["kg"] for s in client.get(f"{API}/analytics/operations", headers=oh).json()["funnel"]}
    assert funnel["dispatched"] == 40 and funnel["recovered_reviewed"] == 0  # submitted evidence is not yet counted

    assert client.post(f"{API}/processing-transfers/outcomes/{o['id']}/review", headers=ph, json={"decision": "accept"}).status_code == 403
    rv = client.post(f"{API}/processing-transfers/outcomes/{o['id']}/review", headers=oh, json={"decision": "accept"})
    assert rv.status_code == 200 and rv.json()["evidence_status"] == "reviewed_accepted"
    funnel = {s["stage"]: s["kg"] for s in client.get(f"{API}/analytics/operations", headers=oh).json()["funnel"]}
    assert funnel["recovered_reviewed"] == 24 and funnel["accepted"] == 35


def test_self_reported_outcome_is_never_counted_as_recovered(chain, client):
    oh, ph = chain["oh"], chain["ph"]
    t = client.post(f"{API}/processing-transfers", headers=oh, json={"batch_id": chain["mlp"]["id"], "partner_id": str(chain["partner"].id), "kg": "10"}).json()
    t = client.post(f"{API}/processing-transfers/{t['id']}/dispatch", headers=oh, json={"version": t["version"]}).json()
    t = client.post(f"{API}/processing-transfers/{t['id']}/receive", headers=ph, json={"version": t["version"], "received_kg": "10"}).json()
    t = client.post(f"{API}/processing-transfers/{t['id']}/decide", headers=ph, json={"version": t["version"], "accepted_kg": "10", "rejected_kg": "0"}).json()
    o = client.post(f"{API}/processing-transfers/{t['id']}/outcomes", headers=ph, json=outcome_body(outcome_type="accepted_for_processing", input_kg="10", output_kg="10"))
    assert o.status_code == 201 and o.json()["evidence_status"] == "none"
    assert client.post(f"{API}/processing-transfers/outcomes/{o.json()['id']}/review", headers=oh, json={"decision": "accept"}).status_code == 409
    overview = client.get(f"{API}/analytics/overview", headers=oh).json()
    assert overview["recovered_kg"]["evidence_reviewed"] == 0


def test_transfer_rules(chain, client, db):
    oh = chain["oh"]
    unsupported = client.post(f"{API}/processing-transfers", headers=oh, json={"batch_id": chain["rigid"]["id"], "partner_id": str(chain["partner"].id), "kg": "5"})
    assert unsupported.status_code == 400 and unsupported.json()["error"]["code"] == "CATEGORY_NOT_SUPPORTED"
    over = client.post(f"{API}/processing-transfers", headers=oh, json={"batch_id": chain["mlp"]["id"], "partner_id": str(chain["partner"].id), "kg": "41"})
    assert over.status_code == 409
    other_proc = f.user(db, "processor", f.org(db, "processor"))
    t = client.post(f"{API}/processing-transfers", headers=oh, json={"batch_id": chain["mlp"]["id"], "partner_id": str(chain["partner"].id), "kg": "5"}).json()
    assert client.get(f"{API}/processing-transfers/{t['id']}", headers=f.headers(other_proc)).status_code == 404
    assert client.get(f"{API}/processing-transfers/{t['id']}", headers=chain["ph"]).status_code == 200


def test_marketplace_offer_sale_and_payments(chain, client):
    oh, ph = chain["oh"], chain["ph"]
    listing = client.post(f"{API}/marketplace/listings", headers=oh, json={"batch_id": chain["paper"]["id"], "quantity_kg": "28", "asking_price_paise_per_kg": 900})
    assert listing.status_code == 201 and listing.json()["price_is_hypothetical"] is True
    lid = listing.json()["id"]
    assert any(x["id"] == lid for x in client.get(f"{API}/marketplace/listings", headers=ph).json())
    offer = client.post(f"{API}/marketplace/listings/{lid}/offers", headers=ph, json={"kind": "offer", "quantity_kg": "20", "price_paise_per_kg": 850})
    assert offer.status_code == 201
    oid = offer.json()["offers"][0]["id"]
    assert client.post(f"{API}/marketplace/offers/{oid}/sale", headers=oh, json={"quantity_kg": "20", "unit_price_paise": 850, "sold_on": date.today().isoformat()}).status_code == 409
    assert client.post(f"{API}/marketplace/offers/{oid}/respond", headers=oh, json={"decision": "accept"}).json()["status"] == "reserved"
    sold = client.post(f"{API}/marketplace/offers/{oid}/sale", headers=oh, json={"quantity_kg": "20", "unit_price_paise": 850, "sold_on": date.today().isoformat(), "invoice_number": "INV-1"})
    assert sold.status_code == 200 and sold.json()["status"] == "sold"
    assert client.get(f"{API}/inventory/batches/{chain['paper']['id']}", headers=oh).json()["batch"]["current_weight_kg"] == 8
    sale = client.get(f"{API}/finance/sales", headers=oh).json()["items"][0]
    assert sale["total_paise"] == 17000 and sale["payment_status"] == "pending"
    part = client.post(f"{API}/finance/sales/{sale['id']}/payments", headers=oh, json={"amount_paise": 10000, "paid_on": date.today().isoformat(), "method": "upi"})
    assert part.json()["payment_status"] == "partially_paid"
    assert client.post(f"{API}/finance/sales/{sale['id']}/payments", headers=oh, json={"amount_paise": 8000, "paid_on": date.today().isoformat(), "method": "upi"}).status_code == 409
    summary = client.get(f"{API}/finance/summary", headers=oh).json()
    assert summary["revenue_paise"] == 17000 and summary["received_paise"] == 10000 and summary["receivable_paise"] == 7000


def test_expenses_and_reports(chain, client, db):
    oh = chain["oh"]
    est = client.post(f"{API}/finance/expenses", headers=oh, json={"category": "fuel_vehicle", "amount_paise": 50000, "incurred_on": date.today().isoformat(), "is_estimate": True})
    assert est.status_code == 400 and est.json()["error"]["code"] == "ASSUMPTION_REQUIRED"
    ok = client.post(f"{API}/finance/expenses", headers=oh, json={"category": "facility_operations", "amount_paise": 120000, "incurred_on": date.today().isoformat()})
    assert ok.status_code == 201
    assert client.get(f"{API}/finance/summary", headers=oh).json()["expenses_recorded_paise"] == 120000
    csv_r = client.get(f"{API}/reports/inventory.csv", headers=oh)
    assert csv_r.status_code == 200 and csv_r.headers["content-type"].startswith("text/csv")
    lines = csv_r.text.strip().splitlines()
    assert lines[0].startswith("# PlasticLoop AI export") and lines[1].startswith("batch,") and len(lines) >= 5
    pdf = client.get(f"{API}/reports/summary.pdf", headers=oh)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    collector = f.user(db, "collector", f.org(db))
    assert client.get(f"{API}/reports/collections.csv", headers=f.headers(collector)).status_code == 403
