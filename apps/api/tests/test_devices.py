"""Device registration, credentials, HTTPS + MQTT telemetry ingestion, quality flags and alerts."""

import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import CollectionPoint, Device, DeviceReading, Notification
from app.models.enums import ConnectionStatus
from app.services.telemetry import refresh_connection_states
from app.worker import handle_message
from tests import factories as f


@pytest.fixture
def world(db, client):
    gp = f.org(db)
    v = f.village(db, gp)
    admin = f.user(db, "gp_admin", gp)
    collector = f.user(db, "collector", gp)
    s = f.stream(db)
    cp = f.point(db, v, [s], collector)
    r = client.post("/api/v1/devices", headers=f.headers(admin), json={
        "device_id": "DEV-TEST-001", "collection_point_id": str(cp.id), "weight_max_kg": "100", "is_simulated": False})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"gp": gp, "village": v, "admin": admin, "collector": collector, "stream": s, "cp": cp,
            "device": body["device"], "key": body["device_key"], "topics": body["topics"]}


def reading(reading_id="r-1", **over):
    p = {"device_id": "DEV-TEST-001", "reading_id": reading_id, "timestamp": datetime.now(UTC).isoformat(),
         "weight_kg": 12.5, "fill_percent": 40, "battery_percent": 90, "sensor_status": "ok", "firmware_version": "1.0.0"}
    p.update(over)
    return p


def dev_auth(w, key=None):
    return {"Authorization": f"Device DEV-TEST-001:{key or w['key']}"}


def test_register_returns_key_once_and_stores_only_hashes(world, client, db):
    assert len(world["key"]) >= 24
    assert world["topics"]["telemetry"] == "plasticloop/devices/DEV-TEST-001/telemetry"
    r = client.get(f"/api/v1/devices/{world['device']['id']}", headers=f.headers(world["admin"]))
    assert r.status_code == 200 and "device_key" not in r.json()
    from app.core.config import settings

    passwd = settings.mqtt_passwd_file.read_text()
    assert "DEV-TEST-001:$7$101$" in passwd and world["key"] not in passwd


def test_https_telemetry_is_idempotent_and_updates_device(world, client, db):
    r = client.post("/api/v1/devices/telemetry", json=reading(), headers=dev_auth(world))
    assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["quality"] == "ok"
    r2 = client.post("/api/v1/devices/telemetry", json=reading(), headers=dev_auth(world))
    assert r2.json()["status"] == "duplicate"
    n = db.scalar(select(func.count()).select_from(DeviceReading).where(DeviceReading.reading_id == "r-1"))
    assert n == 1
    d = db.scalar(select(Device).where(Device.device_id == "DEV-TEST-001"))
    assert d.connection_status == ConnectionStatus.ONLINE and float(d.last_weight_kg) == 12.5 and d.battery_percent == 90
    assert float(db.get(CollectionPoint, world["cp"].id).fill_percent) == 40.0


def test_device_auth_failures(world, client):
    assert client.post("/api/v1/devices/telemetry", json=reading()).status_code == 422  # header missing
    assert client.post("/api/v1/devices/telemetry", json=reading(), headers=dev_auth(world, "wrong-key")).status_code == 401
    r = client.post("/api/v1/devices/telemetry", json=reading(device_id="DEV-OTHER-9"), headers=dev_auth(world))
    assert r.status_code == 400 and r.json()["error"]["code"] == "TELEMETRY_REJECTED"


def test_key_rotation_invalidates_old_key(world, client):
    r = client.post(f"/api/v1/devices/{world['device']['id']}/rotate-key", headers=f.headers(world["admin"]))
    assert r.status_code == 200
    assert client.post("/api/v1/devices/telemetry", json=reading(), headers=dev_auth(world)).status_code == 401
    ok = client.post("/api/v1/devices/telemetry", json=reading(), headers=dev_auth(world, r.json()["device_key"]))
    assert ok.status_code == 200


def test_out_of_range_reading_is_stored_but_flagged_and_not_applied(world, client, db):
    r = client.post("/api/v1/devices/telemetry", json=reading("r-big", weight_kg=999, fill_percent=95), headers=dev_auth(world))
    assert r.json()["quality"] == "out_of_range"
    assert db.get(CollectionPoint, world["cp"].id).fill_percent is None
    alerts = db.scalars(select(Notification.type).where(Notification.user_id == world["admin"].id)).all()
    assert "device_anomaly" in alerts and "bin_fill_alert" not in alerts


def test_fill_alert_and_low_battery_notify(world, client, db):
    client.post("/api/v1/devices/telemetry", json=reading("r-full", fill_percent=91, battery_percent=12), headers=dev_auth(world))
    admin_types = set(db.scalars(select(Notification.type).where(Notification.user_id == world["admin"].id)))
    assert {"bin_fill_alert", "device_low_battery"} <= admin_types
    collector_types = set(db.scalars(select(Notification.type).where(Notification.user_id == world["collector"].id)))
    assert "bin_fill_alert" in collector_types


def test_clock_skew_flagged(world, client):
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    r = client.post("/api/v1/devices/telemetry", json=reading("r-skew", timestamp=future), headers=dev_auth(world))
    assert r.json()["quality"] == "clock_skew"


def test_other_tenant_cannot_see_device(world, client, db):
    other_admin = f.user(db, "gp_admin", f.org(db))
    assert client.get(f"/api/v1/devices/{world['device']['id']}", headers=f.headers(other_admin)).status_code == 404
    listing = client.get("/api/v1/devices", headers=f.headers(other_admin)).json()
    assert listing["total"] == 0
    assert client.get("/api/v1/devices/latest-reading", params={"device_id": "DEV-TEST-001"},
                      headers=f.headers(other_admin)).status_code == 404


def test_collector_uses_scale_reading_in_collection(world, client, db):
    client.post("/api/v1/devices/telemetry", json=reading("r-scale", weight_kg=7.25), headers=dev_auth(world))
    r = client.get("/api/v1/devices/latest-reading", params={"device_id": "DEV-TEST-001"}, headers=f.headers(world["collector"]))
    assert r.status_code == 200 and r.json()["weight_kg"] == 7.25 and r.json()["is_synthetic"] is False
    c = client.post("/api/v1/collections", headers=f.headers(world["collector"]), json={
        "event_id": "6f1f5ba0-3c1e-4c1a-9a43-2d3a39f0c001", "collection_point_id": str(world["cp"].id),
        "waste_stream_id": str(world["stream"].id), "weight_kg": "7.250", "measurement_source": "manual_entry",
        "device_reading_id": r.json()["id"], "collected_at": datetime.now(UTC).isoformat()})
    assert c.status_code in (200, 201), c.text
    assert c.json()["event"]["measurement_source"] == "device_measured"  # promoted only because a real reading is attached


def test_mqtt_messages_through_worker_handler(world, db):
    factory = lambda: nullcontext(db)  # noqa: E731
    topic = world["topics"]["telemetry"]
    assert handle_message(topic, json.dumps(reading("m-1")).encode(), factory) == "accepted:ok"
    assert handle_message(topic, json.dumps(reading("m-1")).encode(), factory) == "duplicate"
    assert handle_message(topic, b"{not json", factory) == "bad_json"
    # A device publishing someone else's id in the payload is rejected even on its own topic.
    assert handle_message(topic, json.dumps(reading("m-2", device_id="DEV-OTHER-9")).encode(), factory) == "rejected"
    assert handle_message("plasticloop/devices/DEV-NOPE/telemetry", json.dumps(reading("m-3")).encode(), factory) == "unknown_device"
    assert handle_message(world["topics"]["status"], b'{"status":"offline"}', factory) == "status"
    assert db.scalar(select(Device).where(Device.device_id == "DEV-TEST-001")).connection_status == ConnectionStatus.OFFLINE


def test_calibration_result_from_device_status(world, db, client):
    factory = lambda: nullcontext(db)  # noqa: E731
    msg = {"type": "calibration_result", "result": "pass", "reference_mass_kg": 5.0, "scale_factor": 21.3, "offset": 0.02}
    assert handle_message(world["topics"]["status"], json.dumps(msg).encode(), factory) == "status"
    cals = client.get(f"/api/v1/devices/{world['device']['id']}/calibrations", headers=f.headers(world["admin"])).json()
    assert cals[0]["source"] == "device_command" and cals[0]["result"] == "pass"


def test_silent_device_goes_offline_with_alert(world, client, db):
    client.post("/api/v1/devices/telemetry", json=reading("r-old"), headers=dev_auth(world))
    d = db.scalar(select(Device).where(Device.device_id == "DEV-TEST-001"))
    d.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    db.flush()
    assert refresh_connection_states(db)["offline"] == 1
    assert d.connection_status == ConnectionStatus.OFFLINE
    assert db.scalar(select(Notification.id).where(Notification.type == "device_offline", Notification.user_id == world["admin"].id))


def test_command_publishes_to_device_topic(world, client, monkeypatch):
    sent = {}

    def fake_single(topic, payload, **kw):
        sent.update(topic=topic, payload=json.loads(payload), auth=kw["auth"]["username"])

    monkeypatch.setattr("paho.mqtt.publish.single", fake_single)
    r = client.post(f"/api/v1/devices/{world['device']['id']}/commands", headers=f.headers(world["admin"]),
                    json={"command": "calibrate", "known_mass_kg": 5})
    assert r.status_code == 200, r.text
    assert sent["topic"] == world["topics"]["commands"] and sent["payload"]["known_mass_kg"] == 5
    bad = client.post(f"/api/v1/devices/{world['device']['id']}/commands", headers=f.headers(world["admin"]), json={"command": "calibrate"})
    assert bad.status_code == 400
    assert client.post(f"/api/v1/devices/{world['device']['id']}/commands", headers=f.headers(world["collector"]),
                       json={"command": "ping"}).status_code == 403


def test_simulator_only_drives_simulated_devices(world, client, db):
    evaluator = f.user(db, "evaluator", f.org(db))
    r = client.post(f"/api/v1/demo/devices/{world['device']['id']}/simulate", headers=f.headers(evaluator), json={"fill_percent": 50})
    assert r.status_code == 400 and r.json()["error"]["code"] == "NOT_SIMULATED"
    sim = client.post("/api/v1/devices", headers=f.headers(world["admin"]), json={
        "device_id": "DEV-SIM-001", "organization_id": str(world["gp"].id), "is_simulated": True}).json()["device"]
    r = client.post(f"/api/v1/demo/devices/{sim['id']}/simulate", headers=f.headers(evaluator), json={"weight_kg": 3.5})
    assert r.status_code == 200 and r.json()["reading"]["is_synthetic"] is True
