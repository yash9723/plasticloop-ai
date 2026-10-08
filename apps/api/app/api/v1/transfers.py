import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.facilities import operable_facility, visible_facility_ids
from app.core.errors import forbidden, not_found
from app.models import Facility, MaterialBatch, MaterialCategory, ProcessingOutcome, ProcessingPartner, ProcessingTransfer
from app.models.enums import DataOrigin, EvidenceStatus, OutcomeType, RoleKey, TransferStatus
from app.schemas.common import Kg, KgIn, Page
from app.security.deps import DB, Principal, require
from app.services import recovery
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.media import signed_url

router = APIRouter()
VIEWERS = (RoleKey.MRF_OPERATOR, RoleKey.PROCESSOR, RoleKey.GP_ADMIN, RoleKey.EVALUATOR)


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transfer_id: uuid.UUID
    outcome_type: OutcomeType
    input_kg: Kg
    output_kg: Kg
    process_date: date
    process_description: str | None
    receipt_reference: str | None
    attested_by_name: str
    attestation_text: str | None
    evidence_status: EvidenceStatus
    review_notes: str | None
    reviewed_at: datetime | None
    data_origin: DataOrigin
    created_at: datetime
    evidence_url: str | None = None
    transfer_code: str | None = None
    partner_name: str | None = None
    category_label: str | None = None


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    source_facility_id: uuid.UUID
    batch_id: uuid.UUID
    partner_id: uuid.UUID
    status: TransferStatus
    allocated_kg: Kg
    transporter_name: str | None
    vehicle_no: str | None
    manifest_ref: str | None
    dispatched_at: datetime | None
    received_at: datetime | None
    received_kg: Kg | None
    receipt_discrepancy_kg: Kg | None
    discrepancy_flag: bool
    accepted_kg: Kg | None
    rejected_kg: Kg | None
    rejection_reason: str | None
    returned_kg: Kg | None
    receipt_reference: str | None
    decided_at: datetime | None
    notes: str | None
    data_origin: DataOrigin
    version: int
    created_at: datetime
    facility_name: str = ""
    partner_name: str = ""
    batch_code: str = ""
    category_label: str = ""
    verification_status: str = ""


class TransferDetail(TransferOut):
    outcomes: list[OutcomeOut] = []
    receipt_url: str | None = None
    warnings: list[str] = []


class AllocateIn(BaseModel):
    batch_id: uuid.UUID
    partner_id: uuid.UUID
    kg: KgIn
    transporter_name: str | None = Field(None, max_length=160)
    vehicle_no: str | None = Field(None, max_length=20)
    manifest_ref: str | None = Field(None, max_length=60)
    notes: str | None = Field(None, max_length=1000)


class VersionIn(BaseModel):
    version: int


class ReceiveIn(VersionIn):
    received_kg: KgIn
    receipt_reference: str | None = Field(None, max_length=60)
    receipt_media_id: uuid.UUID | None = None


class DecideIn(VersionIn):
    accepted_kg: KgIn
    rejected_kg: KgIn
    rejection_reason: str | None = Field(None, max_length=500)
    return_rejected: bool = False


class OutcomeIn(BaseModel):
    outcome_type: OutcomeType
    input_kg: KgIn
    output_kg: KgIn
    process_date: date
    attested_by_name: str = Field(min_length=3, max_length=120)
    process_description: str | None = Field(None, max_length=1000)
    receipt_reference: str | None = Field(None, max_length=60)
    evidence_media_id: uuid.UUID | None = None
    attestation_text: str | None = Field(None, max_length=1000)


class ReviewIn(BaseModel):
    decision: Literal["accept", "reject"]
    notes: str | None = Field(None, max_length=1000)


def serialize(db: Session, transfers: list[ProcessingTransfer], detail: bool = False) -> list:
    if not transfers:
        return []
    facs = dict(db.execute(select(Facility.id, Facility.name).where(Facility.id.in_({t.source_facility_id for t in transfers}))).all())
    partners = dict(db.execute(select(ProcessingPartner.id, ProcessingPartner.display_name).where(ProcessingPartner.id.in_({t.partner_id for t in transfers}))).all())
    batches = {r[0]: r[1:] for r in db.execute(
        select(MaterialBatch.id, MaterialBatch.code, MaterialCategory.label, MaterialBatch.verification_status)
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(MaterialBatch.id.in_({t.batch_id for t in transfers})))}
    out = []
    for t in transfers:
        o = (TransferDetail if detail else TransferOut).model_validate(t)
        o.facility_name, o.partner_name = facs.get(t.source_facility_id, ""), partners.get(t.partner_id, "")
        o.batch_code, o.category_label, vs = batches.get(t.batch_id, ("", "", ""))
        o.verification_status = str(vs)
        if detail:
            o.receipt_url = signed_url(t.receipt_media_id)
            o.outcomes = serialize_outcomes(db, list(db.scalars(select(ProcessingOutcome).where(ProcessingOutcome.transfer_id == t.id)
                                                                  .order_by(ProcessingOutcome.created_at))))
        out.append(o)
    return out


def serialize_outcomes(db: Session, outcomes: list[ProcessingOutcome]) -> list[OutcomeOut]:
    if not outcomes:
        return []
    info = {r[0]: r[1:] for r in db.execute(
        select(ProcessingTransfer.id, ProcessingTransfer.code, ProcessingPartner.display_name, MaterialCategory.label)
        .join(ProcessingPartner, ProcessingPartner.id == ProcessingTransfer.partner_id)
        .join(MaterialBatch, MaterialBatch.id == ProcessingTransfer.batch_id)
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(ProcessingTransfer.id.in_({o.transfer_id for o in outcomes})))}
    out = []
    for o in outcomes:
        x = OutcomeOut.model_validate(o)
        x.evidence_url = signed_url(o.evidence_media_id)
        x.transfer_code, x.partner_name, x.category_label = info.get(o.transfer_id, (None, None, None))
        out.append(x)
    return out


def visible_clause(db: Session, principal: Principal):
    scope = principal.scope
    if scope.sees_all:
        return None
    fac = visible_facility_ids(db, scope) or {uuid.UUID(int=0)}
    return ProcessingTransfer.source_facility_id.in_(fac) | ProcessingTransfer.partner_id.in_(scope.partner_ids or {uuid.UUID(int=0)})


def get_visible(db: Session, transfer_id: uuid.UUID, principal: Principal) -> ProcessingTransfer:
    stmt = select(ProcessingTransfer).where(ProcessingTransfer.id == transfer_id)
    clause = visible_clause(db, principal)
    if clause is not None:
        stmt = stmt.where(clause)
    t = db.scalar(stmt)
    if t is None:
        raise not_found("Transfer")
    return t


def as_partner(db: Session, transfer_id: uuid.UUID, principal: Principal) -> ProcessingTransfer:
    t = get_visible(db, transfer_id, principal)
    if not (principal.scope.is_super or t.partner_id in principal.scope.partner_ids):
        raise forbidden("Only the receiving processing partner can do this")
    return t


def as_operator(db: Session, transfer_id: uuid.UUID, principal: Principal) -> ProcessingTransfer:
    t = get_visible(db, transfer_id, principal)
    operable_facility(db, t.source_facility_id, principal)
    return t


@router.get("", response_model=Page[TransferOut])
def list_transfers(db: DB, params: PageParams = Depends(), status: TransferStatus | None = None, flagged: bool | None = None,
                   principal: Principal = Depends(require(*VIEWERS))):
    stmt = select(ProcessingTransfer)
    clause = visible_clause(db, principal)
    if clause is not None:
        stmt = stmt.where(clause)
    if status:
        stmt = stmt.where(ProcessingTransfer.status == status)
    if flagged is not None:
        stmt = stmt.where(ProcessingTransfer.discrepancy_flag.is_(flagged))
    page = paginate(db, stmt, params, {"created": ProcessingTransfer.created_at, "kg": ProcessingTransfer.allocated_kg,
                                       "status": ProcessingTransfer.status}, "-created")
    page["items"] = serialize(db, page["items"])
    return page


@router.get("/{transfer_id}", response_model=TransferDetail)
def get_transfer(transfer_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*VIEWERS))):
    return serialize(db, [get_visible(db, transfer_id, principal)], detail=True)[0]


@router.post("", response_model=TransferDetail, status_code=201, summary="Allocate part of a batch to a processing partner")
def allocate(body: AllocateIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    batch = db.get(MaterialBatch, body.batch_id)
    if batch is None:
        raise not_found("Batch")
    operable_facility(db, batch.facility_id, principal)
    t, warnings = recovery.allocate(db, body.batch_id, body.partner_id, body.kg, principal.id, transporter_name=body.transporter_name,
                                    vehicle_no=body.vehicle_no, manifest_ref=body.manifest_ref, notes=body.notes)
    audit(db, principal, "transfer.allocated", "transfer", t.id, after={"kg": str(t.allocated_kg)})
    db.commit()
    out = serialize(db, [t], detail=True)[0]
    out.warnings = warnings
    return out


@router.post("/{transfer_id}/dispatch", response_model=TransferDetail)
def dispatch(transfer_id: uuid.UUID, body: VersionIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    as_operator(db, transfer_id, principal)
    t = recovery.dispatch(db, transfer_id, principal.id, expected_version=body.version)
    audit(db, principal, "transfer.dispatched", "transfer", t.id)
    db.commit()
    return serialize(db, [t], detail=True)[0]


@router.post("/{transfer_id}/cancel", response_model=TransferDetail)
def cancel(transfer_id: uuid.UUID, body: VersionIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    t = as_operator(db, transfer_id, principal)
    t = recovery.lock_transfer(db, t.id, body.version)
    recovery._require(t, TransferStatus.ALLOCATED)
    t.status = TransferStatus.CANCELLED
    audit(db, principal, "transfer.cancelled", "transfer", t.id)
    db.commit()
    return serialize(db, [t], detail=True)[0]


@router.post("/{transfer_id}/receive", response_model=TransferDetail, summary="Processor confirms the weight received")
def receive(transfer_id: uuid.UUID, body: ReceiveIn, db: DB, principal: Principal = Depends(require(RoleKey.PROCESSOR))):
    as_partner(db, transfer_id, principal)
    t = recovery.receive(db, transfer_id, body.received_kg, principal.id, receipt_reference=body.receipt_reference,
                         receipt_media_id=body.receipt_media_id, expected_version=body.version)
    audit(db, principal, "transfer.received", "transfer", t.id, after={"received_kg": str(t.received_kg)})
    db.commit()
    return serialize(db, [t], detail=True)[0]


@router.post("/{transfer_id}/decide", response_model=TransferDetail, summary="Processor accepts / rejects received material")
def decide(transfer_id: uuid.UUID, body: DecideIn, db: DB, principal: Principal = Depends(require(RoleKey.PROCESSOR))):
    as_partner(db, transfer_id, principal)
    t = recovery.decide(db, transfer_id, body.accepted_kg, body.rejected_kg, principal.id, rejection_reason=body.rejection_reason,
                        return_rejected=body.return_rejected, expected_version=body.version)
    audit(db, principal, "transfer.decided", "transfer", t.id, after={"accepted": str(t.accepted_kg), "rejected": str(t.rejected_kg)})
    db.commit()
    return serialize(db, [t], detail=True)[0]


@router.post("/{transfer_id}/outcomes", response_model=OutcomeOut, status_code=201,
             summary="Processor reports what happened to accepted material (evidence needed for recycling claims)")
def add_outcome(transfer_id: uuid.UUID, body: OutcomeIn, db: DB, principal: Principal = Depends(require(RoleKey.PROCESSOR))):
    as_partner(db, transfer_id, principal)
    o = recovery.record_outcome(db, transfer_id, principal.id, **body.model_dump())
    audit(db, principal, "outcome.reported", "processing_outcome", o.id, after={"type": body.outcome_type, "output_kg": str(o.output_kg)})
    db.commit()
    return serialize_outcomes(db, [o])[0]


@router.get("/outcomes/all", response_model=Page[OutcomeOut], summary="Outcomes across visible transfers (recovery page)")
def list_outcomes(db: DB, params: PageParams = Depends(), evidence_status: EvidenceStatus | None = None,
                  principal: Principal = Depends(require(*VIEWERS))):
    stmt = select(ProcessingOutcome).join(ProcessingTransfer, ProcessingTransfer.id == ProcessingOutcome.transfer_id)
    clause = visible_clause(db, principal)
    if clause is not None:
        stmt = stmt.where(clause)
    if evidence_status:
        stmt = stmt.where(ProcessingOutcome.evidence_status == evidence_status)
    page = paginate(db, stmt, params, {"created": ProcessingOutcome.created_at, "date": ProcessingOutcome.process_date}, "-created")
    page["items"] = serialize_outcomes(db, page["items"])
    return page


@router.post("/outcomes/{outcome_id}/review", response_model=OutcomeOut, summary="Review submitted evidence (not by the processor)")
def review_outcome(outcome_id: uuid.UUID, body: ReviewIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    o = db.get(ProcessingOutcome, outcome_id)
    if o is None:
        raise not_found("Outcome")
    as_operator(db, o.transfer_id, principal)
    o = recovery.review_outcome(db, outcome_id, body.decision, body.notes, principal.id)
    audit(db, principal, f"outcome.evidence_{body.decision}", "processing_outcome", o.id)
    db.commit()
    return serialize_outcomes(db, [o])[0]

