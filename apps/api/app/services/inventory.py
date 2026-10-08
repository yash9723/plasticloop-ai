"""MRF / PWMU inventory: intake, sorting, split, merge, adjustments, MLP verification and mass balance.

Invariants (enforced here, by DB CHECK constraints and by the append-only trigger on batch_movements):
* every change to a batch's weight is one signed `batch_movements` row; balance_after_kg never goes negative;
* rows are locked (`SELECT … FOR UPDATE`) and version-checked before any weight change;
* a sorting step records measured input and outputs; the difference is kept on the operation, never silently erased;
* material can only become `verified_with_evidence` MLP through an explicit review with uploaded evidence.
"""

import secrets
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.models import (
    BatchLineage,
    BatchMovement,
    BatchOperation,
    Facility,
    FacilityIntake,
    MaterialBatch,
    MaterialCategory,
    MediaFile,
)
from app.models.enums import BatchStatus, DataOrigin, MovementType, VerificationStatus
from app.security.tokens import utcnow
from app.services import system_settings

KG = Decimal("0.001")
IN_TYPES = {MovementType.SORT_IN, MovementType.SPLIT_IN, MovementType.MERGE_IN}
OUT_TYPES = {MovementType.SORT_OUT, MovementType.SPLIT_OUT, MovementType.MERGE_OUT}


def q(value) -> Decimal:
    return Decimal(str(value)).quantize(KG)


def new_code(prefix: str) -> str:
    return f"{prefix}-{utcnow():%y%m%d}-{secrets.token_hex(3).upper()}"


def category_by_code(db: Session, code: str) -> MaterialCategory:
    cat = db.scalar(select(MaterialCategory).where(MaterialCategory.code == code))
    if cat is None:
        raise not_found(f"Material category '{code}'")
    return cat


def lock_batch(db: Session, batch_id: uuid.UUID, expected_version: int | None = None) -> MaterialBatch:
    batch = db.scalar(select(MaterialBatch).where(MaterialBatch.id == batch_id).with_for_update())
    if batch is None:
        raise not_found("Batch")
    if expected_version is not None and batch.version != expected_version:
        raise conflict("VERSION_CONFLICT", "This batch changed since you loaded it. Reload and try again.")
    return batch


def _move(db: Session, batch: MaterialBatch, mtype: MovementType, qty: Decimal, actor_id, *, operation_id=None,
          reference_type=None, reference_id=None, reason=None, at: datetime | None = None) -> BatchMovement:
    qty = q(qty)
    if qty == 0:
        raise bad_request("ZERO_QUANTITY", "Quantity must not be zero")
    balance = q(batch.current_weight_kg) + qty
    if balance < 0:
        raise conflict("INSUFFICIENT_STOCK", f"Batch {batch.code} holds {batch.current_weight_kg} kg; cannot remove {-qty} kg")
    batch.current_weight_kg = balance
    batch.status = BatchStatus.DEPLETED if balance == 0 else BatchStatus.ACTIVE
    m = BatchMovement(batch_id=batch.id, facility_id=batch.facility_id, operation_id=operation_id, movement_type=mtype,
                      quantity_kg=qty, balance_after_kg=balance, reference_type=reference_type,
                      reference_id=str(reference_id) if reference_id else None, reason=reason, actor_id=actor_id,
                      data_origin=batch.data_origin, occurred_at=at or utcnow())
    db.add(m)
    return m


def _new_batch(db: Session, facility: Facility, category: MaterialCategory, kg: Decimal, source: str, actor_id,
               mtype: MovementType, origin: DataOrigin, *, operation_id=None, verification: VerificationStatus | None = None,
               storage_location: str | None = None, notes: str | None = None, reference=(None, None),
               at: datetime | None = None) -> MaterialBatch:
    if verification is None:
        # Visual/manual sorting can only ever produce *suspected* MLP; verification is a separate evidence review.
        verification = VerificationStatus.SUSPECTED if category.is_mlp else VerificationStatus.UNVERIFIED
    kg = q(kg)
    if kg <= 0:
        raise bad_request("INVALID_WEIGHT", "A new batch needs a positive weight")
    batch = MaterialBatch(code=new_code("B"), facility_id=facility.id, category_id=category.id, verification_status=verification,
                          initial_weight_kg=kg, current_weight_kg=kg, storage_location=storage_location,
                          custodian_org_id=facility.organization_id, processing_eligible=category.recoverable, source=source,
                          notes=notes, created_by=actor_id, data_origin=origin, created_at=at or utcnow())
    db.add(batch)
    db.flush()
    # Opening ledger entry written directly (the batch is inserted with its weight, so it starts at version 1).
    db.add(BatchMovement(batch_id=batch.id, facility_id=facility.id, operation_id=operation_id, movement_type=mtype, quantity_kg=kg,
                         balance_after_kg=kg, reference_type=reference[0],
                         reference_id=str(reference[1]) if reference[1] else None, actor_id=actor_id, data_origin=origin,
                         occurred_at=at or utcnow()))
    return batch


def record_intake(db: Session, facility: Facility, actor_id, *, gross_kg, tare_kg, received_at: datetime,
                  origin_village_id=None, route_id=None, vehicle_id=None, transporter_name=None, declared_collected_kg=None,
                  storage_location=None, notes=None, origin: DataOrigin = DataOrigin.LIVE) -> FacilityIntake:
    """Movements are stamped with `received_at` so period reports reflect when material actually arrived."""
    gross, tare = q(gross_kg), q(tare_kg)
    if gross <= 0 or tare < 0 or gross <= tare:
        raise bad_request("INVALID_WEIGHTS", "Gross weight must be greater than tare weight")
    net = gross - tare
    intake = FacilityIntake(code=new_code("IN"), facility_id=facility.id, origin_village_id=origin_village_id, route_id=route_id,
                            vehicle_id=vehicle_id, transporter_name=transporter_name, received_at=received_at, gross_kg=gross,
                            tare_kg=tare, net_kg=net, declared_collected_kg=q(declared_collected_kg) if declared_collected_kg is not None else None,
                            operator_id=actor_id, operator_confirmed_at=received_at, notes=notes, data_origin=origin)
    db.add(intake)
    db.flush()
    batch = _new_batch(db, facility, category_by_code(db, "mixed_unsorted"), net, "intake", actor_id, MovementType.INTAKE, origin,
                       storage_location=storage_location, notes=f"Intake {intake.code}", reference=("intake", intake.id),
                       at=received_at)
    intake.batch_id = batch.id
    db.flush()
    return intake


def sort_batch(db: Session, batch_id: uuid.UUID, outputs: list[dict], actor_id, *, input_kg=None, expected_version=None,
               notes=None, at: datetime | None = None) -> tuple[BatchOperation, list[MaterialBatch]]:
    """outputs: [{category_id, weight_kg, storage_location?}]. Consumes `input_kg` (default: the whole batch)."""
    parent = lock_batch(db, batch_id, expected_version)
    if parent.status != BatchStatus.ACTIVE:
        raise conflict("BATCH_DEPLETED", "This batch has no remaining material")
    if not outputs:
        raise bad_request("NO_OUTPUTS", "Record at least one sorted fraction")
    consumed = q(input_kg) if input_kg is not None else q(parent.current_weight_kg)
    if consumed <= 0 or consumed > q(parent.current_weight_kg):
        raise conflict("INSUFFICIENT_STOCK", f"Batch holds {parent.current_weight_kg} kg")
    total_out = sum((q(o["weight_kg"]) for o in outputs), Decimal("0"))
    if any(q(o["weight_kg"]) <= 0 for o in outputs):
        raise bad_request("INVALID_WEIGHT", "Every sorted fraction needs a positive weight")
    tol = Decimal(str(system_settings.get_value(db, "mass_balance_tolerance_kg")))
    if total_out > consumed + tol:
        raise bad_request("OUTPUTS_EXCEED_INPUT",
                          f"Sorted fractions total {total_out} kg but only {consumed} kg was sorted; re-weigh before saving")
    facility = db.get(Facility, parent.facility_id)
    op = BatchOperation(operation_type="sort", facility_id=facility.id, input_kg=consumed, output_kg=total_out,
                        difference_kg=consumed - total_out, notes=notes, actor_id=actor_id, data_origin=parent.data_origin,
                        created_at=at or utcnow())
    db.add(op)
    db.flush()
    _move(db, parent, MovementType.SORT_OUT, -consumed, actor_id, operation_id=op.id, at=at)
    children = []
    for o in outputs:
        cat = db.get(MaterialCategory, o["category_id"])
        if cat is None:
            raise not_found("Material category")
        if cat.is_unsorted:
            raise bad_request("UNSORTED_OUTPUT", "A sorted fraction cannot be 'mixed / unsorted'")
        child = _new_batch(db, facility, cat, q(o["weight_kg"]), "sort", actor_id, MovementType.SORT_IN, parent.data_origin,
                           operation_id=op.id, storage_location=o.get("storage_location"), at=at)
        db.add(BatchLineage(parent_batch_id=parent.id, child_batch_id=child.id, operation_id=op.id, weight_kg=child.initial_weight_kg))
        children.append(child)
    db.flush()
    return op, children


def split_batch(db: Session, batch_id: uuid.UUID, parts: list, actor_id, *, expected_version=None, notes=None):
    parent = lock_batch(db, batch_id, expected_version)
    amounts = [q(p) for p in parts]
    if len(amounts) < 1 or any(a <= 0 for a in amounts):
        raise bad_request("INVALID_SPLIT", "Each part needs a positive weight")
    total = sum(amounts, Decimal("0"))
    if total > q(parent.current_weight_kg):
        raise conflict("INSUFFICIENT_STOCK", f"Parts total {total} kg but the batch holds {parent.current_weight_kg} kg")
    facility, cat = db.get(Facility, parent.facility_id), db.get(MaterialCategory, parent.category_id)
    op = BatchOperation(operation_type="split", facility_id=facility.id, input_kg=total, output_kg=total, difference_kg=Decimal("0"),
                        notes=notes, actor_id=actor_id, data_origin=parent.data_origin)
    db.add(op)
    db.flush()
    _move(db, parent, MovementType.SPLIT_OUT, -total, actor_id, operation_id=op.id)
    children = []
    for a in amounts:
        child = _new_batch(db, facility, cat, a, "split", actor_id, MovementType.SPLIT_IN, parent.data_origin, operation_id=op.id,
                           verification=parent.verification_status, storage_location=parent.storage_location)
        child.verification_media_id, child.verified_by, child.verified_at = parent.verification_media_id, parent.verified_by, parent.verified_at
        db.add(BatchLineage(parent_batch_id=parent.id, child_batch_id=child.id, operation_id=op.id, weight_kg=a))
        children.append(child)
    db.flush()
    return op, children


def merge_batches(db: Session, batch_ids: list[uuid.UUID], actor_id, *, notes=None, storage_location=None):
    ids = sorted(set(batch_ids))  # fixed lock order prevents deadlocks between concurrent merges
    if len(ids) < 2:
        raise bad_request("MERGE_NEEDS_TWO", "Select at least two batches to merge")
    batches = [lock_batch(db, i) for i in ids]
    first = batches[0]
    for b in batches:
        if (b.facility_id, b.category_id, b.verification_status) != (first.facility_id, first.category_id, first.verification_status):
            raise bad_request("MERGE_INCOMPATIBLE", "Only batches at the same facility with the same category and verification status can be merged")
        if b.status != BatchStatus.ACTIVE:
            raise conflict("BATCH_DEPLETED", f"Batch {b.code} is empty")
    total = sum((q(b.current_weight_kg) for b in batches), Decimal("0"))
    origin = DataOrigin.LIVE if all(b.data_origin == DataOrigin.LIVE for b in batches) else (
        DataOrigin.SIMULATED if any(b.data_origin == DataOrigin.SIMULATED for b in batches) else DataOrigin.DEMO_SEED)
    facility, cat = db.get(Facility, first.facility_id), db.get(MaterialCategory, first.category_id)
    op = BatchOperation(operation_type="merge", facility_id=facility.id, input_kg=total, output_kg=total, difference_kg=Decimal("0"),
                        notes=notes, actor_id=actor_id, data_origin=origin)
    db.add(op)
    db.flush()
    merged = _new_batch(db, facility, cat, total, "merge", actor_id, MovementType.MERGE_IN, origin, operation_id=op.id,
                        verification=first.verification_status, storage_location=storage_location or first.storage_location)
    for b in batches:
        amount = q(b.current_weight_kg)
        _move(db, b, MovementType.MERGE_OUT, -amount, actor_id, operation_id=op.id)
        db.add(BatchLineage(parent_batch_id=b.id, child_batch_id=merged.id, operation_id=op.id, weight_kg=amount))
    db.flush()
    return op, merged


def adjust_batch(db: Session, batch_id: uuid.UUID, movement_type: MovementType, quantity_kg, reason: str, actor_id,
                 *, expected_version=None, at: datetime | None = None) -> BatchMovement:
    if movement_type not in (MovementType.LOSS, MovementType.DISPOSAL, MovementType.ADJUSTMENT):
        raise bad_request("INVALID_ADJUSTMENT", "Use loss, disposal or adjustment")
    if not reason or len(reason.strip()) < 5:
        raise bad_request("REASON_REQUIRED", "Explain the adjustment (at least 5 characters)")
    qty = q(quantity_kg)
    if movement_type in (MovementType.LOSS, MovementType.DISPOSAL):
        qty = -abs(qty)
    batch = lock_batch(db, batch_id, expected_version)
    m = _move(db, batch, movement_type, qty, actor_id, reason=reason.strip(), at=at)
    db.flush()
    return m


def review_mlp(db: Session, batch_id: uuid.UUID, decision: str, media_id: uuid.UUID | None, note: str, actor_id,
               *, expected_version=None) -> MaterialBatch:
    """Evidence review for a suspected-MLP batch. Never automatic; requires an uploaded evidence file and a reviewer note."""
    batch = lock_batch(db, batch_id, expected_version)
    cat = db.get(MaterialCategory, batch.category_id)
    if not cat.is_mlp:
        raise bad_request("NOT_MLP_CATEGORY", "Only suspected multilayer-plastic batches go through MLP verification")
    if batch.verification_status not in (VerificationStatus.SUSPECTED, VerificationStatus.UNVERIFIED):
        raise conflict("ALREADY_REVIEWED", f"This batch is already {batch.verification_status.replace('_', ' ')}")
    if not note or len(note.strip()) < 10:
        raise bad_request("NOTE_REQUIRED", "Describe the evidence (at least 10 characters)")
    if decision == "verify":
        if media_id is None or db.get(MediaFile, media_id) is None:
            raise bad_request("EVIDENCE_REQUIRED", "Upload evidence (e.g. lab/processor test report or labelled photos) first")
        batch.verification_status = VerificationStatus.VERIFIED_WITH_EVIDENCE
    elif decision == "reject":
        batch.verification_status = VerificationStatus.VERIFICATION_REJECTED
    else:
        raise bad_request("INVALID_DECISION", "Decision must be 'verify' or 'reject'")
    batch.verification_media_id, batch.verification_note = media_id, note.strip()
    batch.verified_by, batch.verified_at = actor_id, utcnow()
    db.flush()
    return batch


def mass_balance(db: Session, facility_id: uuid.UUID, start: datetime, end: datetime) -> dict:
    """Ledger-based balance for a facility and period. All figures in kg."""
    def total(*conds) -> Decimal:
        return q(db.scalar(select(func.coalesce(func.sum(BatchMovement.quantity_kg), 0)).where(BatchMovement.facility_id == facility_id, *conds)))

    opening = total(BatchMovement.occurred_at < start)
    period = (BatchMovement.occurred_at >= start, BatchMovement.occurred_at < end)
    rows = db.execute(
        select(BatchMovement.movement_type, func.sum(BatchMovement.quantity_kg))
        .where(BatchMovement.facility_id == facility_id, *period).group_by(BatchMovement.movement_type)
    ).all()
    by_type = {str(t): q(v) for t, v in rows}
    closing = opening + sum(by_type.values(), Decimal("0"))
    intake = by_type.get(MovementType.INTAKE, Decimal("0"))
    processing_net = sum((v for k, v in by_type.items() if k in IN_TYPES | OUT_TYPES), Decimal("0"))
    unexplained = -processing_net  # mass that disappeared inside sort/split/merge steps without a recorded loss
    stock_now = q(db.scalar(select(func.coalesce(func.sum(MaterialBatch.current_weight_kg), 0)).where(MaterialBatch.facility_id == facility_id)))
    ledger_now = total()
    tol_kg = Decimal(str(system_settings.get_value(db, "mass_balance_tolerance_kg")))
    tol_pct = Decimal(str(system_settings.get_value(db, "mass_balance_tolerance_percent")))
    allowed = max(tol_kg, (intake * tol_pct / 100).quantize(KG))
    declared = db.scalar(select(func.sum(FacilityIntake.declared_collected_kg)).where(
        FacilityIntake.facility_id == facility_id, FacilityIntake.received_at >= start, FacilityIntake.received_at < end))
    return {
        "facility_id": facility_id,
        "start": start,
        "end": end,
        "opening_kg": opening,
        "intake_kg": intake,
        "transferred_out_kg": -by_type.get(MovementType.TRANSFER_OUT, Decimal("0")),
        "returned_kg": by_type.get(MovementType.TRANSFER_RETURN, Decimal("0")),
        "loss_kg": -by_type.get(MovementType.LOSS, Decimal("0")),
        "disposed_kg": -by_type.get(MovementType.DISPOSAL, Decimal("0")),
        "adjustment_kg": by_type.get(MovementType.ADJUSTMENT, Decimal("0")),
        "unexplained_processing_difference_kg": unexplained,
        "closing_kg": closing,
        "tolerance_kg": allowed,
        "flagged": abs(unexplained) > allowed,
        "declared_collected_kg": q(declared) if declared is not None else None,
        "collection_to_intake_gap_kg": (q(declared) - intake) if declared is not None else None,
        "ledger_consistent": stock_now == ledger_now,
        "movements_by_type": by_type,
    }
