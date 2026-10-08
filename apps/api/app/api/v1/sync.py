import uuid

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import select

from app.core.errors import AppError, bad_request, not_found
from app.models import CollectionEvent, SyncReceipt
from app.models.enums import RoleKey
from app.schemas.collection import (
    CollectionPayload,
    ConflictResolveIn,
    SyncBatchIn,
    SyncBatchOut,
    SyncReceiptOut,
)
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit, snapshot
from app.services.collections import payload_hash, serialize_events
from app.services.sync import process_batch

router = APIRouter()


@router.post("/batch", response_model=SyncBatchOut, summary="Idempotent offline sync with per-event acknowledgement")
def sync_batch(
    body: SyncBatchIn,
    db: DB,
    principal: Principal = Depends(require(RoleKey.COLLECTOR, RoleKey.GP_ADMIN, RoleKey.DRIVER)),
):
    results = process_batch(db, principal, body)
    return SyncBatchOut(results=results, server_time=utcnow())


@router.get("/receipts", response_model=list[SyncReceiptOut], summary="My recent server acknowledgements")
def my_receipts(db: DB, principal: CurrentUser, limit: int = 100):
    return db.scalars(
        select(SyncReceipt).where(SyncReceipt.user_id == principal.id).order_by(SyncReceipt.received_at.desc()).limit(min(limit, 500))
    ).all()


@router.get("/conflicts", summary="Unresolved payload conflicts in my villages")
def list_conflicts(db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    rows = db.execute(
        select(SyncReceipt, CollectionEvent)
        .join(CollectionEvent, CollectionEvent.id == SyncReceipt.event_id)
        .where(SyncReceipt.conflict_payload.isnot(None), principal.scope.village_clause(CollectionEvent.village_id))
        .order_by(SyncReceipt.last_seen_at.desc())
    ).all()
    events = serialize_events(db, [e for _, e in rows])
    return [
        {"receipt": SyncReceiptOut.model_validate(r), "original": ev}
        for (r, _), ev in zip(rows, events, strict=True)
    ]


@router.post("/conflicts/{event_id}/resolve", summary="Keep the original or apply the newer offline version (audited)")
def resolve_conflict(event_id: uuid.UUID, body: ConflictResolveIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    receipt = db.get(SyncReceipt, event_id)
    event = db.get(CollectionEvent, event_id)
    if receipt is None or event is None or receipt.conflict_payload is None:
        raise not_found("Conflict")
    principal.scope.ensure_village(event.village_id, "Conflict")
    fields = ("waste_stream_id", "weight_kg", "notes", "collected_at", "media_id")
    before = snapshot(event, *fields)
    if body.action == "apply_new":
        try:
            newer = CollectionPayload.model_validate(receipt.conflict_payload)
        except ValidationError as exc:
            raise bad_request("INVALID_CONFLICT_PAYLOAD", "The newer version is invalid and cannot be applied") from exc
        if newer.collection_point_id != event.collection_point_id:
            raise AppError(422, "POINT_CHANGED", "The newer version targets a different collection point; record it as a new collection")
        event.waste_stream_id = newer.waste_stream_id
        event.weight_kg = newer.weight_kg
        event.notes = newer.notes
        event.collected_at = newer.collected_at
        event.media_id = newer.media_id
        receipt.payload_hash = payload_hash("collection", newer.model_dump(mode="json"))
    receipt.resolution = body.action
    receipt.resolved_by = principal.id
    receipt.resolved_at = utcnow()
    receipt.conflict_payload = None
    audit(db, principal, f"sync_conflict.{body.action}", "collection_event", event.id, before,
          {**snapshot(event, *fields), "note": body.note})
    db.commit()
    return {"ok": True, "event": serialize_events(db, [event])[0]}
