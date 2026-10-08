"""Database-level guarantees that hold even if application code is bypassed."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import AuditLog, CollectionEvent, CollectionPoint
from app.models.enums import MeasurementSource
from tests import factories as f


def _expect_db_error(db, exc_type, fn):
    with pytest.raises(exc_type):
        with db.begin_nested():
            fn()
            db.flush()


def test_collection_weight_must_be_positive(db):
    v = f.village(db, f.org(db))
    s = f.stream(db)
    cp = f.point(db, v, [s])
    u = f.user(db, "collector", f.org(db))

    def insert():
        eid = uuid.uuid4()
        db.add(CollectionEvent(id=eid, idempotency_key=str(eid), collection_point_id=cp.id, village_id=v.id, collector_id=u.id,
                               waste_stream_id=s.id, weight_kg=Decimal("0"), measurement_source=MeasurementSource.MANUAL_ENTRY,
                               collected_at=datetime.now(UTC), payload_hash="x"))

    _expect_db_error(db, IntegrityError, insert)


def test_qr_codes_are_unique(db):
    v = f.village(db, f.org(db))
    s = f.stream(db)
    cp = f.point(db, v, [s])
    _expect_db_error(db, IntegrityError, lambda: db.add(CollectionPoint(code="DUP-1", qr_code=cp.qr_code, name="dup", village_id=v.id)))


def test_audit_log_is_append_only(db):
    entry = AuditLog(action="test.event", entity_type="test", entity_id="1")
    db.add(entry)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        with db.begin_nested():
            db.execute(text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": entry.id})
    with pytest.raises(DBAPIError, match="append-only"):
        with db.begin_nested():
            db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry.id})


def test_enum_values_enforced_by_database(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("INSERT INTO organizations (id, name, code, org_type) VALUES (gen_random_uuid(), 'x', 'BAD-1', 'pirate')"))
