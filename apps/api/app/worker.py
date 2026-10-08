"""Background worker: MQTT telemetry subscriber + periodic operational checks.

    python -m app.worker

Runs the same ingestion service as the HTTPS endpoint. The broker's ACL guarantees a device can only publish on
its own topic, so the device id in the topic is the authenticated identity.
"""

import json
import signal
import threading
from pathlib import Path
from datetime import timedelta

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.iot.mqtt_auth import write_passwd_file_from_db
from app.models import Device, MaterialBatch, MaterialCategory, PickupRequest
from app.models.enums import BatchStatus, PickupStatus, Severity
from app.security.tokens import utcnow
from app.services import system_settings
from app.services.notifications import facility_operators, notify, village_admins
from app.services.telemetry import StatusIn, TelemetryIn, TelemetryRejected, handle_status, ingest, refresh_connection_states

log = get_logger("app.worker")
TOPIC_PREFIX = "plasticloop/devices/"
TICK_S = 60
HEARTBEAT = Path("/tmp/worker-heartbeat")  # docker healthcheck: stale file = stuck worker
stop = threading.Event()


def handle_message(topic: str, payload: bytes, session_factory=SessionLocal) -> str:
    """Returns an outcome label (also used by tests)."""
    parts = topic.split("/")
    if len(parts) != 4 or not topic.startswith(TOPIC_PREFIX) or parts[3] not in ("telemetry", "status"):
        return "ignored_topic"
    device_id, kind = parts[2], parts[3]
    try:
        data = json.loads(payload)
    except ValueError:
        log.warning("mqtt_bad_json", extra={"fields": {"device_id": device_id}})
        return "bad_json"
    with session_factory() as db:
        device = db.scalar(select(Device).where(Device.device_id == device_id, Device.deleted_at.is_(None),
                                                Device.active.is_(True)))
        if device is None:
            return "unknown_device"
        try:
            if kind == "telemetry":
                reading, duplicate = ingest(db, device, TelemetryIn.model_validate(data), transport="mqtt")
                outcome = "duplicate" if duplicate else f"accepted:{reading.quality}"
            else:
                handle_status(db, device, StatusIn.model_validate(data))
                outcome = "status"
            db.commit()
            return outcome
        except (ValidationError, TelemetryRejected) as exc:
            db.rollback()
            log.warning("mqtt_payload_rejected", extra={"fields": {"device_id": device_id, "error": str(exc)[:300]}})
            return "rejected"


def flag_overdue_pickups(db) -> int:
    hours = int(system_settings.get_value(db, "pickup_overdue_hours"))
    cutoff = utcnow() - timedelta(hours=hours)
    overdue = db.scalars(select(PickupRequest).where(
        PickupRequest.status.in_([PickupStatus.SUBMITTED, PickupStatus.ASSIGNED]), PickupRequest.created_at < cutoff))
    n = 0
    for pr in overdue:
        n += notify(db, [*village_admins(db, pr.village_id), pr.assigned_collector_id], type="pickup_overdue",
                    severity=Severity.WARNING, title=f"Pickup request open for more than {hours} h",
                    entity_type="pickup_request", entity_id=pr.id, link="/pickup-requests",
                    dedupe_key=f"overdue:{pr.id}", cooldown_minutes=24 * 60)
    return n


def flag_aging_batches(db) -> int:
    """Recoverable material sitting longer than the configured limit: nudge the facility to transfer or sell it."""
    days = int(system_settings.get_value(db, "inventory_aging_alert_days"))
    rows = db.execute(
        select(MaterialBatch.facility_id, func.count(), func.sum(MaterialBatch.current_weight_kg))
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(MaterialBatch.status == BatchStatus.ACTIVE, MaterialBatch.processing_eligible.is_(True), MaterialCategory.is_unsorted.is_(False),
               MaterialBatch.created_at < utcnow() - timedelta(days=days))
        .group_by(MaterialBatch.facility_id)
    ).all()
    n = 0
    for facility_id, count, kg in rows:
        n += notify(db, facility_operators(db, facility_id), type="inventory_aging", severity=Severity.INFO,
                    title=f"{count} batches ({float(kg):.0f} kg) waiting more than {days} days",
                    body="Consider allocating them to a processing partner or listing them.", entity_type="facility",
                    entity_id=facility_id, link=f"/inventory?facility_id={facility_id}", dedupe_key=f"aging:{facility_id}",
                    cooldown_minutes=7 * 24 * 60)
    return n


def tick() -> None:
    with SessionLocal() as db:
        changed = refresh_connection_states(db)
        notified = flag_overdue_pickups(db) + flag_aging_batches(db)
        db.commit()
        write_passwd_file_from_db(db)  # picks up credential changes made by any API process
    HEARTBEAT.touch()
    if changed["stale"] or changed["offline"] or notified:
        log.info("worker_tick", extra={"fields": {**changed, "overdue_notifications": notified}})


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("mqtt_connect_failed", extra={"fields": {"reason": str(reason_code)}})
        return
    client.subscribe([(f"{TOPIC_PREFIX}+/telemetry", 1), (f"{TOPIC_PREFIX}+/status", 1)])
    log.info("mqtt_connected", extra={"fields": {"host": settings.mqtt_host}})


def on_message(client, userdata, msg):
    try:
        handle_message(msg.topic, msg.payload)
    except Exception:  # noqa: BLE001 - one bad message must never kill the subscriber
        log.exception("mqtt_message_failed", extra={"fields": {"topic": msg.topic}})


def main() -> None:
    configure_logging(settings.log_level)
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="plasticloop-worker", clean_session=False)
    client.username_pw_set(settings.mqtt_service_user, settings.mqtt_service_password)
    client.on_connect, client.on_message = on_connect, on_message
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    write_passwd_file_from_db()
    client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    client.loop_start()
    log.info("worker_started")
    while not stop.is_set():
        try:
            tick()
        except Exception:  # noqa: BLE001 - keep the loop alive; DB may be restarting
            log.exception("worker_tick_failed")
        stop.wait(TICK_S)
    client.loop_stop()
    client.disconnect()
    log.info("worker_stopped")


if __name__ == "__main__":
    main()
