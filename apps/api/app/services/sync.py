"""Idempotent offline sync.

Guarantees:
* An event UUID is processed at most once. Retrying the same payload returns the original acknowledgement.
* The same UUID with a *different* payload is a conflict: the original is kept, the new payload is stored
  for an administrator to resolve (never silently overwritten, never silently dropped).
* Each event runs in its own SAVEPOINT, so one bad event cannot roll back the others.
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CollectionEvent, SyncReceipt
from app.models.enums import Severity, SyncReceiptStatus
from app.schemas.collection import CollectionPayload, SyncBatchIn, SyncEventIn, SyncEventResult
from app.security.deps import Principal
from app.security.tokens import utcnow
from app.services.collections import CollectionRejected, payload_hash, record_collection
from app.services.notifications import notify, village_admins


def _result_from_receipt(receipt: SyncReceipt, status: SyncReceiptStatus | None = None, **extra: Any) -> SyncEventResult:
    r = receipt.result or {}
    return SyncEventResult(
        event_id=receipt.event_id,
        status=status or receipt.status,
        server_id=r.get("server_id"),
        code=extra.get("code", r.get("code")),
        message=extra.get("message", r.get("message")),
        review_status=r.get("review_status"),
    )


def _handle_existing(db: Session, actor: Principal, receipt: SyncReceipt, ev: SyncEventIn, digest: str) -> SyncEventResult:
    receipt.last_seen_at = utcnow()
    if receipt.user_id != actor.id:
        return SyncEventResult(
            event_id=ev.event_id, status=SyncReceiptStatus.CONFLICT, code="EVENT_ID_COLLISION",
            message="This event ID was already used by another account. Re-create the record.",
        )
    if receipt.payload_hash == digest:
        if receipt.status == SyncReceiptStatus.ACCEPTED:
            return _result_from_receipt(receipt, SyncReceiptStatus.DUPLICATE, code="ALREADY_SYNCED", message="Already saved on the server")
        return _result_from_receipt(receipt)

    # Same immutable ID, different content: keep original, park the new version for review.
    receipt.conflict_payload = ev.payload
    receipt.conflict_count += 1
    receipt.resolution = None
    original = db.get(CollectionEvent, receipt.event_id)
    if original is not None:
        notify(
            db, village_admins(db, original.village_id), type="sync_conflict", severity=Severity.WARNING,
            title="Offline record conflict needs review",
            body="A collector re-sent an already-synced record with different values.",
            entity_type="sync_receipt", entity_id=receipt.event_id, link="/collector/offline-queue?tab=conflicts",
            dedupe_key=f"sync_conflict:{receipt.event_id}",
        )
    return SyncEventResult(
        event_id=ev.event_id, status=SyncReceiptStatus.CONFLICT, server_id=receipt.result.get("server_id"),
        code="PAYLOAD_MISMATCH",
        message="The server already has this record with different values. The original was kept and an admin will review.",
    )


def process_event(db: Session, actor: Principal, ev: SyncEventIn, client_id: str | None, offline: bool = True) -> SyncEventResult:
    # Hash the normalised payload so semantically identical retries ("2.45" vs "2.450") match.
    try:
        payload = CollectionPayload.model_validate(ev.payload)
        digest = payload_hash(ev.type, payload.model_dump(mode="json"))
        invalid = None
    except ValidationError as exc:
        payload = None
        digest = payload_hash(ev.type, ev.payload)
        invalid = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]

    existing = db.get(SyncReceipt, ev.event_id)
    if existing is not None:
        return _handle_existing(db, actor, existing, ev, digest)

    if invalid is not None:
        result = SyncEventResult(event_id=ev.event_id, status=SyncReceiptStatus.REJECTED, code="VALIDATION_ERROR",
                                 message="Some fields are invalid", details=invalid)
        _store_receipt(db, actor, ev, client_id, digest, result)
        return result

    try:
        with db.begin_nested():
            event = record_collection(db, actor, ev.event_id, payload, client_created_at=ev.client_created_at,
                                      offline_captured=offline)
            result = SyncEventResult(event_id=ev.event_id, status=SyncReceiptStatus.ACCEPTED, server_id=event.id,
                                     review_status=event.review_status, message="Saved")
            _store_receipt(db, actor, ev, client_id, digest, result)
        return result
    except CollectionRejected as rej:
        result = SyncEventResult(event_id=ev.event_id, status=SyncReceiptStatus.REJECTED, code=rej.code, message=rej.message)
        _store_receipt(db, actor, ev, client_id, digest, result)
        return result
    except IntegrityError:
        # Concurrent retry of the same event won the race; report its outcome.
        existing = db.get(SyncReceipt, ev.event_id)
        if existing is not None:
            return _handle_existing(db, actor, existing, ev, digest)
        raise


def _store_receipt(db: Session, actor: Principal, ev: SyncEventIn, client_id: str | None, digest: str, result: SyncEventResult) -> None:
    db.add(
        SyncReceipt(
            event_id=ev.event_id,
            user_id=actor.id,
            client_id=client_id,
            event_type=ev.type,
            payload_hash=digest,
            status=result.status,
            result=result.model_dump(mode="json", exclude={"event_id", "status", "details"}),
        )
    )
    db.flush()


def process_batch(db: Session, actor: Principal, batch: SyncBatchIn) -> list[SyncEventResult]:
    results: list[SyncEventResult] = []
    seen: set[uuid.UUID] = set()
    for ev in batch.events:
        if ev.event_id in seen:  # duplicate inside the same batch
            results.append(SyncEventResult(event_id=ev.event_id, status=SyncReceiptStatus.DUPLICATE,
                                           code="DUPLICATE_IN_BATCH", message="Repeated in the same batch"))
            continue
        seen.add(ev.event_id)
        results.append(process_event(db, actor, ev, batch.client_id))
    db.commit()
    return results
