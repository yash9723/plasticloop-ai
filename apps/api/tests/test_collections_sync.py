"""Collection points, QR identity, online collections and idempotent offline sync."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, CollectionEvent, Notification, SyncReceipt
from tests import factories as f


@pytest.fixture
def world(db, client):
    gp = f.org(db)
    v = f.village(db, gp)
    admin = f.user(db, "gp_admin", gp)
    collector = f.user(db, "collector", gp)
    s1, s2 = f.stream(db), f.stream(db)
    r = client.post("/api/v1/collection-points", headers=f.headers(admin), json={
        "village_id": str(v.id), "name": "Ward 3 community bin", "lat": 17.91, "lng": 78.92,
        "stream_ids": [str(s1.id), str(s2.id)], "assigned_collector_id": str(collector.id), "pickup_days": ["mon", "thu"],
    })
    assert r.status_code == 201, r.text
    return {"gp": gp, "village": v, "admin": admin, "collector": collector, "s1": s1, "s2": s2, "cp": r.json()}


def payload(w, weight="2.450", **over):
    p = {"collection_point_id": w["cp"]["id"], "waste_stream_id": str(w["s1"].id), "weight_kg": weight,
         "measurement_source": "manual_entry", "collected_at": datetime.now(UTC).isoformat()}
    p.update(over)
    return p


def batch(*events):
    return {"client_id": "test-phone", "events": [{"event_id": eid, "type": "collection", "payload": p} for eid, p in events]}


def count_events(db, point_id):
    return db.scalar(select(func.count()).select_from(CollectionEvent).where(CollectionEvent.collection_point_id == point_id))


def test_point_gets_unique_code_and_qr_and_is_resolvable(client, world):
    cp = world["cp"]
    assert cp["code"] == f"{world['village'].code}-CP-001"
    assert cp["qr_code"].startswith("PL") and len(cp["qr_code"]) == 12
    found = client.get(f"/api/v1/collection-points/by-qr/plasticloop:cp:{cp['qr_code']}", headers=f.headers(world["collector"]))
    assert found.status_code == 200 and found.json()["id"] == cp["id"]
    rotated = client.post(f"/api/v1/collection-points/{cp['id']}/regenerate-qr", headers=f.headers(world["admin"])).json()
    assert rotated["qr_code"] != cp["qr_code"]


def test_spatial_nearby_search_uses_postgis(client, world):
    h = f.headers(world["collector"])
    near = client.get("/api/v1/collection-points/nearby", headers=h, params={"lat": 17.9101, "lng": 78.9201, "radius_m": 200}).json()
    far = client.get("/api/v1/collection-points/nearby", headers=h, params={"lat": 18.5, "lng": 79.5, "radius_m": 200}).json()
    assert [p["id"] for p in near] == [world["cp"]["id"]] and far == []


def test_online_collection_is_idempotent(client, db, world):
    h = {**f.headers(world["collector"]), "Idempotency-Key": str(uuid.uuid4())}
    body = payload(world)
    first = client.post("/api/v1/collections", headers=h, json=body)
    second = client.post("/api/v1/collections", headers=h, json=body)
    changed = client.post("/api/v1/collections", headers=h, json={**body, "weight_kg": "7.000"})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "PAYLOAD_MISMATCH"
    assert first.status_code == 201 and first.json()["status"] == "accepted"
    assert second.status_code == 200 and second.json()["status"] == "duplicate"
    assert count_events(db, world["cp"]["id"]) == 1
    receipt = client.get(f"/api/v1/collections/{first.json()['event']['id']}/receipt", headers=f.headers(world["collector"])).json()
    assert receipt["receipt_no"].startswith("PL-") and receipt["weight_kg"] == 2.45


def test_offline_batch_retry_creates_no_duplicates(client, db, world):
    h = f.headers(world["collector"])
    events = [(str(uuid.uuid4()), payload(world, weight=w)) for w in ("1.200", "3.750", "0.900")]
    r1 = client.post("/api/v1/sync/batch", headers=h, json=batch(*events))
    assert r1.status_code == 200, r1.text
    assert [x["status"] for x in r1.json()["results"]] == ["accepted"] * 3

    r2 = client.post("/api/v1/sync/batch", headers=h, json=batch(*events))  # network retry of the same batch
    assert [x["status"] for x in r2.json()["results"]] == ["duplicate"] * 3
    assert [x["server_id"] for x in r2.json()["results"]] == [x["server_id"] for x in r1.json()["results"]]
    assert count_events(db, world["cp"]["id"]) == 3
    assert db.scalar(select(func.count()).select_from(SyncReceipt).where(SyncReceipt.user_id == world["collector"].id)) == 3


def test_changed_payload_with_same_id_is_a_conflict_and_original_is_kept(client, db, world):
    h = f.headers(world["collector"])
    eid = str(uuid.uuid4())
    original = payload(world, weight="5.000")
    client.post("/api/v1/sync/batch", headers=h, json=batch((eid, original)))
    altered = {**original, "weight_kg": "9.000"}
    r = client.post("/api/v1/sync/batch", headers=h, json=batch((eid, altered))).json()["results"][0]
    assert r["status"] == "conflict" and r["code"] == "PAYLOAD_MISMATCH"
    event = db.get(CollectionEvent, uuid.UUID(eid))
    assert float(event.weight_kg) == 5.0
    assert db.get(SyncReceipt, uuid.UUID(eid)).conflict_payload["weight_kg"] == "9.000"
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.type == "sync_conflict")) >= 1

    resolved = client.post(f"/api/v1/sync/conflicts/{eid}/resolve", headers=f.headers(world["admin"]), json={"action": "apply_new", "note": "Scale re-read"})
    assert resolved.status_code == 200, resolved.text
    db.refresh(event)
    assert float(event.weight_kg) == 9.0
    assert db.scalar(select(AuditLog).where(AuditLog.action == "sync_conflict.apply_new", AuditLog.entity_id == eid)) is not None


@pytest.mark.parametrize(
    "override,code",
    [
        ({"weight_kg": "-1"}, "VALIDATION_ERROR"),
        ({"weight_kg": "0"}, "VALIDATION_ERROR"),
        ({"weight_kg": "1.2345"}, "VALIDATION_ERROR"),
        ({"collected_at": "2026-10-01T10:00:00"}, "VALIDATION_ERROR"),
        ({"unexpected_field": 1}, "VALIDATION_ERROR"),
        ({"weight_kg": "600"}, "WEIGHT_OUT_OF_RANGE"),
        ({"measurement_source": "device_measured"}, "DEVICE_READING_REQUIRED"),
        ({"collection_point_id": str(uuid.uuid4())}, "UNKNOWN_COLLECTION_POINT"),
    ],
)
def test_invalid_events_are_rejected_with_reason(client, db, world, override, code):
    r = client.post("/api/v1/sync/batch", headers=f.headers(world["collector"]), json=batch((str(uuid.uuid4()), payload(world, **override))))
    result = r.json()["results"][0]
    assert result["status"] == "rejected" and result["code"] == code
    assert count_events(db, world["cp"]["id"]) == 0


def test_future_timestamp_rejected(client, world):
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    r = client.post("/api/v1/sync/batch", headers=f.headers(world["collector"]), json=batch((str(uuid.uuid4()), payload(world, collected_at=future))))
    assert r.json()["results"][0]["code"] == "FUTURE_TIMESTAMP"


def test_one_bad_event_does_not_roll_back_the_others(client, db, world):
    good, bad = (str(uuid.uuid4()), payload(world)), (str(uuid.uuid4()), payload(world, weight_kg="999"))
    results = client.post("/api/v1/sync/batch", headers=f.headers(world["collector"]), json=batch(good, bad)).json()["results"]
    assert [x["status"] for x in results] == ["accepted", "rejected"]
    assert count_events(db, world["cp"]["id"]) == 1


def test_out_of_scope_collector_rejected(client, db, world):
    outsider = f.user(db, "collector", f.org(db))
    r = client.post("/api/v1/sync/batch", headers=f.headers(outsider), json=batch((str(uuid.uuid4()), payload(world))))
    assert r.json()["results"][0]["code"] == "OUT_OF_SCOPE"


def test_unassigned_collector_is_accepted_but_flagged_for_review(client, db, world):
    colleague = f.user(db, "collector", world["gp"])
    r = client.post("/api/v1/sync/batch", headers=f.headers(colleague), json=batch((str(uuid.uuid4()), payload(world))))
    result = r.json()["results"][0]
    assert result["status"] == "accepted" and result["review_status"] == "flagged"
    assert db.scalar(select(Notification).where(Notification.user_id == world["admin"].id, Notification.type == "collection_flagged"))


def test_collector_tasks_bundle_for_offline_cache(client, world):
    data = client.get("/api/v1/collections/my-tasks", headers=f.headers(world["collector"])).json()
    assert world["cp"]["qr_code"] in {p["qr_code"] for p in data["points"]}
    assert {str(world["s1"].id), str(world["s2"].id)} <= {s["id"] for s in data["streams"]}
    assert all("phone" not in p for p in data["points"])
