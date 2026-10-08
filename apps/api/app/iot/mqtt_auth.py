"""Device credentials (generation, hashing, verification) and the Mosquitto password file.

Mosquitto 2.x `$7$` hashes are PBKDF2-HMAC-SHA512: `$7$<iterations>$<b64 salt>$<b64 hash>`.
The API is the source of truth; infra/mosquitto/entrypoint.sh reloads the broker when the file changes.
"""

import base64
import hashlib
import hmac
import os
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Device, DeviceCredential
from app.security.tokens import sha256_hex, utcnow

PBKDF2_ITERATIONS = 101  # mosquitto_passwd default
log = get_logger("app.iot.auth")


def mosquitto_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(12)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, PBKDF2_ITERATIONS, dklen=64)
    return f"$7${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _service_user_hash() -> str:
    # Stable salt so the file only changes when a credential changes (avoids needless broker reloads).
    salt = hashlib.sha256(f"plasticloop-service:{settings.mqtt_service_user}".encode()).digest()[:12]
    return mosquitto_hash(settings.mqtt_service_password, salt)


def generate_device_key() -> str:
    return secrets.token_urlsafe(24)


def demo_device_key(device_id: str) -> str:
    """Deterministic keys for seeded demo devices only (DEMO_DEVICE_SECRET is dev/test-only)."""
    return hmac.new(settings.demo_device_secret.encode(), device_id.encode(), hashlib.sha256).hexdigest()[:32]


def provision_credentials(db: Session, device: Device, actor_id=None, key: str | None = None) -> str:
    """Revokes previous credentials and returns the new plaintext key (shown once)."""
    key = key or generate_device_key()
    db.execute(
        update(DeviceCredential)
        .where(DeviceCredential.device_pk == device.id, DeviceCredential.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.add(
        DeviceCredential(
            device_pk=device.id,
            key_prefix=key[:6],
            key_hash=sha256_hex(key),
            mqtt_password_hash=mosquitto_hash(key),
            created_by=actor_id,
        )
    )
    return key


def revoke_credentials(db: Session, device: Device) -> None:
    db.execute(
        update(DeviceCredential)
        .where(DeviceCredential.device_pk == device.id, DeviceCredential.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def authenticate_device(db: Session, device_id: str, key: str) -> Device | None:
    device = db.scalar(
        select(Device).where(Device.device_id == device_id, Device.deleted_at.is_(None), Device.active.is_(True))
    )
    if device is None:
        return None
    digest = sha256_hex(key)
    hashes = db.scalars(
        select(DeviceCredential.key_hash).where(DeviceCredential.device_pk == device.id, DeviceCredential.revoked_at.is_(None))
    ).all()
    return device if any(hmac.compare_digest(digest, h) for h in hashes) else None


def write_passwd_file_from_db(db: Session | None = None) -> int:
    own_session = db is None
    if own_session:
        from app.db.session import SessionLocal

        db = SessionLocal()
    try:
        rows = db.execute(
            select(Device.device_id, DeviceCredential.mqtt_password_hash)
            .join(DeviceCredential, DeviceCredential.device_pk == Device.id)
            .where(DeviceCredential.revoked_at.is_(None), Device.active.is_(True), Device.deleted_at.is_(None))
            .order_by(DeviceCredential.created_at)
        ).all()
    finally:
        if own_session:
            db.close()

    entries = {settings.mqtt_service_user: _service_user_hash()}
    for device_id, mqtt_hash in rows:
        entries[device_id] = mqtt_hash
    content = "".join(f"{user}:{h}\n" for user, h in sorted(entries.items()))

    path = settings.mqtt_passwd_file
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return len(entries)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)
    log.info("mqtt_passwd_written", extra={"fields": {"entries": len(entries)}})
    return len(entries)
