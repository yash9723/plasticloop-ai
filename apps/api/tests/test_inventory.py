"""MRF intake, sorting, split/merge, adjustments, MLP evidence review, ledger integrity and mass balance."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import BatchMovement, MaterialBatch, MaterialCategory, MediaFile
from app.models.enums import MediaPurpose
from tests import factories as f

API = "/api/v1"


@pytest.fixture
def mrf(db, client):
    op_org = f.org(db, "mrf_operator")
    fac = f.facility(db, op_org)
    gp = f.org(db)
    v = f.village(db, gp, fac)
    operator = f.user(db, "mrf_operator", op_org, facility_obj=fac)
    cats = {c.code: c for c in db.scalars(select(MaterialCategory))}
    return {"facility": fac, "village": v, "operator": operator, "gp": gp, "cats": cats, "h": f.headers(operator)}


def intake(client, w, gross="120.500", tare="20.000", **kw):
    r = client.post(f"{API}/facilities/{w['facility'].id}/intakes", headers=w["h"],
                    json={"gross_kg": gross, "tare_kg": tare, "origin_village_id": str(w["village"].id), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def batch(client, w, batch_id):
    r = client.get(f"{API}/inventory/batches/{batch_id}", headers=w["h"])
    assert r.status_code == 200, r.text
    return r.json()


def test_intake_creates_unsorted_batch_with_ledger_entry(mrf, client):
    i = intake(client, mrf, declared_collected_kg="104.000")
    assert i["net_kg"] == 100.5
    d = batch(client, mrf, i["batch_id"])
    assert d["batch"]["category_code"] == "mixed_unsorted" and d["batch"]["current_weight_kg"] == 100.5
    assert [m["movement_type"] for m in d["movements"]] == ["intake"] and d["ledger_sum_kg"] == 100.5


def test_intake_rejects_tare_above_gross(mrf, client):
    r = client.post(f"{API}/facilities/{mrf['facility'].id}/intakes", headers=mrf["h"], json={"gross_kg": "10", "tare_kg": "12"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_WEIGHTS"


def test_sort_records_fractions_and_keeps_difference_visible(mrf, client):
    i = intake(client, mrf, gross="110", tare="10")
    v = batch(client, mrf, i["batch_id"])["batch"]["version"]
    cats = mrf["cats"]
    r = client.post(f"{API}/inventory/batches/{i['batch_id']}/sort", headers=mrf["h"], json={"version": v, "outputs": [
        {"category_id": str(cats["rigid_plastic"].id), "weight_kg": "40"},
        {"category_id": str(cats["suspected_mlp"].id), "weight_kg": "35"},
        {"category_id": str(cats["contamination_rejects"].id), "weight_kg": "22"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["operation"]["difference_kg"] == 3.0  # 100 in, 97 out: kept, not erased
    mlp = next(b for b in body["batches"] if b["category_code"] == "suspected_mlp")
    assert mlp["verification_status"] == "suspected"  # sorting never yields verified MLP
    parent = batch(client, mrf, i["batch_id"])
    assert parent["batch"]["status"] == "depleted" and len(parent["children"]) == 3
    mb = client.get(f"{API}/facilities/{mrf['facility'].id}/mass-balance", headers=mrf["h"]).json()
    assert mb["intake_kg"] == 100 and mb["unexplained_processing_difference_kg"] == 3.0
    assert mb["closing_kg"] == 97 and mb["ledger_consistent"] is True and mb["flagged"] is True  # 3 kg > 1 kg tolerance


def test_sort_outputs_cannot_exceed_input(mrf, client):
    i = intake(client, mrf, gross="60", tare="10")
    r = client.post(f"{API}/inventory/batches/{i['batch_id']}/sort", headers=mrf["h"], json={"version": 1, "outputs": [
        {"category_id": str(mrf["cats"]["rigid_plastic"].id), "weight_kg": "55"}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "OUTPUTS_EXCEED_INPUT"


def test_overdraw_is_prevented_for_split_and_adjust(mrf, client):
    i = intake(client, mrf, gross="30", tare="10")
    r = client.post(f"{API}/inventory/batches/{i['batch_id']}/split", headers=mrf["h"], json={"version": 1, "parts_kg": ["15", "10"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    r = client.post(f"{API}/inventory/batches/{i['batch_id']}/adjust", headers=mrf["h"],
                    json={"version": 1, "movement_type": "loss", "quantity_kg": 25, "reason": "Spillage in yard"})
    assert r.status_code == 409


def test_stale_version_is_rejected(mrf, client):
    i = intake(client, mrf, gross="30", tare="10")
    ok = client.post(f"{API}/inventory/batches/{i['batch_id']}/adjust", headers=mrf["h"],
                     json={"version": 1, "movement_type": "loss", "quantity_kg": 1, "reason": "Moisture loss"})
    assert ok.status_code == 200
    stale = client.post(f"{API}/inventory/batches/{i['batch_id']}/adjust", headers=mrf["h"],
                        json={"version": 1, "movement_type": "loss", "quantity_kg": 1, "reason": "Moisture loss"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_split_then_merge_round_trip(mrf, client):
    i = intake(client, mrf, gross="40", tare="10")
    parts = client.post(f"{API}/inventory/batches/{i['batch_id']}/split", headers=mrf["h"],
                        json={"version": 1, "parts_kg": ["12.5", "17.5"]}).json()["batches"]
    merged = client.post(f"{API}/inventory/merge", headers=mrf["h"], json={"batch_ids": [p["id"] for p in parts]})
    assert merged.status_code == 200, merged.text
    assert merged.json()["batches"][0]["current_weight_kg"] == 30
    mb = client.get(f"{API}/facilities/{mrf['facility'].id}/mass-balance", headers=mrf["h"]).json()
    assert mb["unexplained_processing_difference_kg"] == 0 and mb["closing_kg"] == 30 and not mb["flagged"]


def test_merge_rejects_different_categories(mrf, client):
    a, b = intake(client, mrf), intake(client, mrf)
    rigid = client.post(f"{API}/inventory/batches/{a['batch_id']}/sort", headers=mrf["h"], json={"version": 1, "outputs": [
        {"category_id": str(mrf["cats"]["rigid_plastic"].id), "weight_kg": "100"}]}).json()["batches"][0]
    r = client.post(f"{API}/inventory/merge", headers=mrf["h"], json={"batch_ids": [rigid["id"], b["batch_id"]]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "MERGE_INCOMPATIBLE"


def test_mlp_verification_requires_evidence(mrf, client, db):
    i = intake(client, mrf, gross="30", tare="10")
    mlp = client.post(f"{API}/inventory/batches/{i['batch_id']}/sort", headers=mrf["h"], json={"version": 1, "outputs": [
        {"category_id": str(mrf["cats"]["suspected_mlp"].id), "weight_kg": "20"}]}).json()["batches"][0]
    no_evidence = client.post(f"{API}/inventory/batches/{mlp['id']}/mlp-review", headers=mrf["h"],
                              json={"version": mlp["version"], "decision": "verify", "note": "Looks like chip packets"})
    assert no_evidence.status_code == 400 and no_evidence.json()["error"]["code"] == "EVIDENCE_REQUIRED"
    media = MediaFile(owner_user_id=mrf["operator"].id, purpose=MediaPurpose.VERIFICATION_EVIDENCE, content_type="application/pdf",
                      size_bytes=10, sha256="0" * 64, storage_path="x.pdf")
    db.add(media)
    db.flush()
    ok = client.post(f"{API}/inventory/batches/{mlp['id']}/mlp-review", headers=mrf["h"], json={
        "version": mlp["version"], "decision": "verify", "media_id": str(media.id), "note": "Processor burn/peel test report attached"})
    assert ok.status_code == 200 and ok.json()["verification_status"] == "verified_with_evidence"
    plain = client.post(f"{API}/inventory/batches/{i['batch_id']}/mlp-review", headers=mrf["h"],
                        json={"version": 2, "decision": "reject", "note": "Not multilayer material at all"})
    assert plain.status_code == 400 and plain.json()["error"]["code"] == "NOT_MLP_CATEGORY"


def test_ledger_is_append_only(mrf, client, db):
    i = intake(client, mrf)
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("UPDATE batch_movements SET quantity_kg = 1 WHERE batch_id = :b"), {"b": i["batch_id"]})
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("DELETE FROM batch_movements WHERE batch_id = :b"), {"b": i["batch_id"]})


def test_every_batch_equals_its_ledger(mrf, client, db):
    i = intake(client, mrf, gross="80", tare="5")
    client.post(f"{API}/inventory/batches/{i['batch_id']}/split", headers=mrf["h"], json={"version": 1, "parts_kg": ["20", "30"]})
    sums = dict(db.execute(select(BatchMovement.batch_id, func.sum(BatchMovement.quantity_kg)).group_by(BatchMovement.batch_id)).all())
    for b in db.scalars(select(MaterialBatch).where(MaterialBatch.facility_id == mrf["facility"].id)):
        assert sums[b.id] == b.current_weight_kg
    assert sum(b.current_weight_kg for b in db.scalars(select(MaterialBatch).where(MaterialBatch.facility_id == mrf["facility"].id))) == Decimal("75")


def test_tenant_isolation_and_roles(mrf, client, db):
    i = intake(client, mrf)
    other_operator = f.user(db, "mrf_operator", f.org(db, "mrf_operator"))
    assert client.get(f"{API}/inventory/batches/{i['batch_id']}", headers=f.headers(other_operator)).status_code == 404
    gp_admin = f.user(db, "gp_admin", mrf["gp"])  # village delivers here → read-only view
    assert client.get(f"{API}/inventory/batches/{i['batch_id']}", headers=f.headers(gp_admin)).status_code == 200
    r = client.post(f"{API}/inventory/batches/{i['batch_id']}/adjust", headers=f.headers(gp_admin),
                    json={"version": 1, "movement_type": "loss", "quantity_kg": 1, "reason": "Should not be allowed"})
    assert r.status_code == 403
    evaluator = f.user(db, "evaluator", f.org(db))
    assert client.post(f"{API}/facilities/{mrf['facility'].id}/intakes", headers=f.headers(evaluator),
                       json={"gross_kg": "10", "tare_kg": "1"}).status_code == 403
