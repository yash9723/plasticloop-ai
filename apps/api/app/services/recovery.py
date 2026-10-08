"""Processing transfers and outcomes.

Lifecycle: allocated → dispatched (ledger TRANSFER_OUT) → received (discrepancy check) → accepted / partially_accepted /
rejected (optional TRANSFER_RETURN batch) → outcomes → completed.

Honesty rules enforced here:
* dispatch or acceptance is never counted as recycling;
* "recycled_with_evidence" / "recovered_documented_process" outcomes need an evidence file and stay `submitted` until a
  person other than the processor reviews them; outcomes without evidence are `self_reported` (evidence_status=none);
* outcome input can never exceed what the processor accepted.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.models import (
    Facility,
    MaterialBatch,
    MaterialCategory,
    MediaFile,
    ProcessingOutcome,
    ProcessingPartner,
    ProcessingTransfer,
)
from app.models.enums import (
    BatchStatus,
    EvidenceStatus,
    MovementType,
    OutcomeType,
    TransferStatus,
    VerificationStatus,
)
from app.security.tokens import utcnow
from app.services import inventory, system_settings
from app.services.inventory import q
from app.services.notifications import facility_operators, notify, partner_users

EVIDENCE_REQUIRED = {OutcomeType.RECYCLED_WITH_EVIDENCE, OutcomeType.RECOVERED_DOCUMENTED_PROCESS}


def lock_transfer(db: Session, transfer_id: uuid.UUID, expected_version: int | None = None) -> ProcessingTransfer:
    t = db.scalar(select(ProcessingTransfer).where(ProcessingTransfer.id == transfer_id).with_for_update())
    if t is None:
        raise not_found("Transfer")
    if expected_version is not None and t.version != expected_version:
        raise conflict("VERSION_CONFLICT", "This transfer changed since you loaded it. Reload and try again.")
    return t


def _require(t: ProcessingTransfer, *statuses: TransferStatus) -> None:
    if t.status not in statuses:
        raise conflict("INVALID_TRANSITION", f"Transfer is {t.status.replace('_', ' ')}")


def allocate(db: Session, batch_id: uuid.UUID, partner_id: uuid.UUID, kg, actor_id, *, transporter_name=None, vehicle_no=None,
             manifest_ref=None, notes=None) -> tuple[ProcessingTransfer, list[str]]:
    batch = inventory.lock_batch(db, batch_id)
    partner = db.get(ProcessingPartner, partner_id)
    if partner is None or partner.deleted_at is not None or not partner.active:
        raise not_found("Processing partner")
    cat = db.get(MaterialCategory, batch.category_id)
    if batch.status != BatchStatus.ACTIVE or not batch.processing_eligible:
        raise conflict("BATCH_NOT_ELIGIBLE", "This batch is empty or not eligible for processing")
    if cat.is_unsorted:
        raise bad_request("SORT_FIRST", "Sort mixed material before sending it to a processor")
    if cat.code not in (partner.supported_category_codes or []):
        raise bad_request("CATEGORY_NOT_SUPPORTED", f"{partner.display_name} does not accept {cat.label}")
    if batch.verification_status == VerificationStatus.VERIFICATION_REJECTED:
        raise bad_request("VERIFICATION_REJECTED", "This batch failed verification; re-sort it before transfer")
    kg = q(kg)
    committed = q(db.scalar(select(func.coalesce(func.sum(ProcessingTransfer.allocated_kg), 0)).where(
        ProcessingTransfer.batch_id == batch.id, ProcessingTransfer.status == TransferStatus.ALLOCATED)))
    if kg <= 0 or kg + committed > q(batch.current_weight_kg):
        raise conflict("INSUFFICIENT_STOCK", f"Batch holds {batch.current_weight_kg} kg, {committed} kg already allocated")
    warnings = []
    if partner.documentation_status != "reviewed_verified":
        warnings.append("Partner documentation has not been reviewed; recycling claims will need outcome evidence.")
    t = ProcessingTransfer(code=inventory.new_code("TR"), source_facility_id=batch.facility_id, batch_id=batch.id, partner_id=partner.id,
                           allocated_kg=kg, transporter_name=transporter_name, vehicle_no=vehicle_no, manifest_ref=manifest_ref,
                           notes=notes, created_by=actor_id, data_origin=batch.data_origin)
    db.add(t)
    db.flush()
    notify(db, partner_users(db, partner.id), type="transfer_allocated", title=f"{kg} kg of {cat.label} allocated to you",
           entity_type="transfer", entity_id=t.id, link=f"/processing-transfers/{t.id}")
    return t, warnings


def dispatch(db: Session, transfer_id: uuid.UUID, actor_id, *, expected_version=None, at: datetime | None = None) -> ProcessingTransfer:
    t = lock_transfer(db, transfer_id, expected_version)
    _require(t, TransferStatus.ALLOCATED)
    batch = inventory.lock_batch(db, t.batch_id)
    # The material leaves the facility here. It is NOT recycled yet — that needs a reviewed outcome.
    inventory._move(db, batch, MovementType.TRANSFER_OUT, -q(t.allocated_kg), actor_id, reference_type="transfer", reference_id=t.id,
                    reason=f"Dispatched to processor ({t.code})", at=at)
    t.status, t.dispatched_at = TransferStatus.DISPATCHED, at or utcnow()
    db.flush()
    notify(db, partner_users(db, t.partner_id), type="transfer_dispatched", title=f"{t.code} is on its way ({t.allocated_kg} kg)",
           entity_type="transfer", entity_id=t.id, link=f"/processing-transfers/{t.id}")
    return t


def receive(db: Session, transfer_id: uuid.UUID, received_kg, actor_id, *, receipt_reference=None, receipt_media_id=None,
            expected_version=None, at: datetime | None = None) -> ProcessingTransfer:
    t = lock_transfer(db, transfer_id, expected_version)
    _require(t, TransferStatus.DISPATCHED)
    received = q(received_kg)
    if received < 0 or received > q(t.allocated_kg) * Decimal("1.1"):
        raise bad_request("INVALID_WEIGHT", "Received weight must be between 0 and 110% of the dispatched weight")
    tol = Decimal(str(system_settings.get_value(db, "transfer_discrepancy_tolerance_percent")))
    t.received_kg, t.received_at = received, at or utcnow()
    t.receipt_discrepancy_kg = q(t.allocated_kg) - received
    t.discrepancy_flag = abs(t.receipt_discrepancy_kg) > q(t.allocated_kg) * tol / 100
    t.receipt_reference, t.receipt_media_id = receipt_reference, receipt_media_id
    t.status = TransferStatus.RECEIVED
    db.flush()
    if t.discrepancy_flag:
        notify(db, facility_operators(db, t.source_facility_id), type="transfer_discrepancy",
               title=f"{t.code}: received {received} kg of {t.allocated_kg} kg dispatched",
               entity_type="transfer", entity_id=t.id, link=f"/processing-transfers/{t.id}", dedupe_key=f"disc:{t.id}")
    return t


def decide(db: Session, transfer_id: uuid.UUID, accepted_kg, rejected_kg, actor_id, *, rejection_reason=None, return_rejected=False,
           expected_version=None, at: datetime | None = None) -> ProcessingTransfer:
    t = lock_transfer(db, transfer_id, expected_version)
    _require(t, TransferStatus.RECEIVED)
    acc, rej = q(accepted_kg), q(rejected_kg)
    if acc < 0 or rej < 0 or abs((acc + rej) - q(t.received_kg)) > Decimal("0.001"):
        raise bad_request("WEIGHTS_MUST_ADD_UP", f"Accepted + rejected must equal the received {t.received_kg} kg")
    if rej > 0 and not (rejection_reason and len(rejection_reason.strip()) >= 5):
        raise bad_request("REASON_REQUIRED", "Explain why material was rejected")
    t.accepted_kg, t.rejected_kg, t.rejection_reason = acc, rej, (rejection_reason or None)
    t.status = TransferStatus.REJECTED if acc == 0 else (TransferStatus.PARTIALLY_ACCEPTED if rej > 0 else TransferStatus.ACCEPTED)
    t.decided_at, t.decided_by = at or utcnow(), actor_id
    if return_rejected and rej > 0:
        src = db.get(MaterialBatch, t.batch_id)
        facility = db.get(Facility, t.source_facility_id)
        inventory._new_batch(db, facility, db.get(MaterialCategory, src.category_id), rej, "return", actor_id,
                                   MovementType.TRANSFER_RETURN, src.data_origin, verification=src.verification_status,
                                   notes=f"Returned from {t.code}: {rejection_reason}", reference=("transfer", t.id), at=at)
        t.returned_kg = rej
    db.flush()
    notify(db, facility_operators(db, t.source_facility_id), type="transfer_decided",
           title=f"{t.code}: {acc} kg accepted, {rej} kg rejected", entity_type="transfer", entity_id=t.id,
           link=f"/processing-transfers/{t.id}")
    return t


def record_outcome(db: Session, transfer_id: uuid.UUID, actor_id, *, outcome_type: OutcomeType, input_kg, output_kg, process_date: date,
                   attested_by_name: str, process_description=None, receipt_reference=None, evidence_media_id=None,
                   attestation_text=None, at: datetime | None = None) -> ProcessingOutcome:
    t = lock_transfer(db, transfer_id)
    _require(t, TransferStatus.ACCEPTED, TransferStatus.PARTIALLY_ACCEPTED, TransferStatus.REJECTED)
    inp, out = q(input_kg), q(output_kg)
    if inp <= 0 or out < 0 or out > inp:
        raise bad_request("INVALID_WEIGHT", "Output must be between 0 and the input weight")
    if process_date > (at or utcnow()).date():
        raise bad_request("FUTURE_DATE", "Processing date cannot be in the future")
    used = q(db.scalar(select(func.coalesce(func.sum(ProcessingOutcome.input_kg), 0)).where(ProcessingOutcome.transfer_id == t.id)))
    limit = q(t.accepted_kg or 0) if outcome_type != OutcomeType.REJECTED else q(t.rejected_kg or 0)
    if outcome_type != OutcomeType.REJECTED and used + inp > q(t.accepted_kg or 0):
        raise conflict("EXCEEDS_ACCEPTED", f"Only {q(t.accepted_kg or 0) - used} kg of accepted material is left to report")
    if outcome_type == OutcomeType.REJECTED and inp > limit:
        raise conflict("EXCEEDS_REJECTED", f"Only {limit} kg was rejected")
    if evidence_media_id is not None and db.get(MediaFile, evidence_media_id) is None:
        raise not_found("Evidence file")
    if outcome_type in EVIDENCE_REQUIRED and evidence_media_id is None:
        raise bad_request("EVIDENCE_REQUIRED", "A recycling/recovery claim needs an evidence file (e.g. processing record, output photo, invoice)")
    o = ProcessingOutcome(transfer_id=t.id, outcome_type=outcome_type, input_kg=inp, output_kg=out, process_date=process_date,
                          process_description=process_description, receipt_reference=receipt_reference,
                          evidence_media_id=evidence_media_id, attested_by_name=attested_by_name, attested_by_user=actor_id,
                          attestation_text=attestation_text,
                          evidence_status=EvidenceStatus.SUBMITTED if evidence_media_id else EvidenceStatus.NONE,
                          data_origin=t.data_origin, created_at=at or utcnow())
    db.add(o)
    db.flush()
    reported = used + inp
    if outcome_type != OutcomeType.REJECTED and reported >= q(t.accepted_kg or 0):
        t.status = TransferStatus.COMPLETED
    notify(db, facility_operators(db, t.source_facility_id), type="outcome_reported",
           title=f"{t.code}: {outcome_type.replace('_', ' ')} reported ({out} kg output)",
           body="Evidence submitted — please review." if evidence_media_id else "Self-reported without evidence.",
           entity_type="transfer", entity_id=t.id, link="/recovery")
    return o


def review_outcome(db: Session, outcome_id: uuid.UUID, decision: str, notes: str | None, actor_id) -> ProcessingOutcome:
    o = db.scalar(select(ProcessingOutcome).where(ProcessingOutcome.id == outcome_id).with_for_update())
    if o is None:
        raise not_found("Outcome")
    if o.evidence_status != EvidenceStatus.SUBMITTED:
        raise conflict("NOTHING_TO_REVIEW", "Only outcomes with submitted evidence can be reviewed")
    if o.attested_by_user == actor_id:
        raise conflict("SELF_REVIEW", "The person who reported an outcome cannot review it")
    if decision not in ("accept", "reject"):
        raise bad_request("INVALID_DECISION", "Decision must be 'accept' or 'reject'")
    if decision == "reject" and not (notes and len(notes.strip()) >= 5):
        raise bad_request("REASON_REQUIRED", "Explain why the evidence is not sufficient")
    o.evidence_status = EvidenceStatus.REVIEWED_ACCEPTED if decision == "accept" else EvidenceStatus.REVIEWED_REJECTED
    o.reviewed_by, o.reviewed_at, o.review_notes = actor_id, utcnow(), notes
    db.flush()
    return o
