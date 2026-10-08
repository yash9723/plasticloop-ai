import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.facilities import operable_facility, visible_facility_ids
from app.core.errors import not_found
from app.models import BatchLineage, BatchMovement, BatchOperation, Facility, MaterialBatch, MaterialCategory, User
from app.models.enums import BatchStatus, DataOrigin, MovementType, RoleKey, VerificationStatus
from app.schemas.common import Kg, KgIn, Page
from app.security.deps import DB, Principal, require
from app.services import inventory
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.media import signed_url

router = APIRouter()
READERS = (RoleKey.MRF_OPERATOR, RoleKey.GP_ADMIN, RoleKey.EVALUATOR, RoleKey.PROCESSOR)


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    facility_id: uuid.UUID
    category_id: uuid.UUID
    verification_status: VerificationStatus
    initial_weight_kg: Kg
    current_weight_kg: Kg
    storage_location: str | None
    processing_eligible: bool
    status: BatchStatus
    source: str
    notes: str | None
    verification_note: str | None
    verified_at: datetime | None
    created_at: datetime
    data_origin: DataOrigin
    version: int
    category_code: str = ""
    category_label: str = ""
    is_mlp: bool = False
    facility_name: str = ""


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    movement_type: MovementType
    quantity_kg: Kg
    balance_after_kg: Kg
    reference_type: str | None
    reference_id: str | None
    reason: str | None
    operation_id: uuid.UUID | None
    occurred_at: datetime
    actor_name: str | None = None


class LinkOut(BaseModel):
    batch_id: uuid.UUID
    code: str
    category_label: str
    weight_kg: Kg
    operation_type: str


class OperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    operation_type: str
    input_kg: Kg
    output_kg: Kg
    difference_kg: Kg
    notes: str | None
    created_at: datetime


class BatchDetail(BaseModel):
    batch: BatchOut
    movements: list[MovementOut]
    parents: list[LinkOut]
    children: list[LinkOut]
    operations: list[OperationOut]
    verification_evidence_url: str | None
    ledger_sum_kg: Kg


class SortOutput(BaseModel):
    category_id: uuid.UUID
    weight_kg: KgIn
    storage_location: str | None = Field(None, max_length=80)


class SortIn(BaseModel):
    outputs: list[SortOutput] = Field(min_length=1, max_length=20)
    input_kg: KgIn | None = None
    version: int
    notes: str | None = Field(None, max_length=1000)


class SplitIn(BaseModel):
    parts_kg: list[KgIn] = Field(min_length=1, max_length=20)
    version: int
    notes: str | None = Field(None, max_length=1000)


class MergeIn(BaseModel):
    batch_ids: list[uuid.UUID] = Field(min_length=2, max_length=50)
    storage_location: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)


class AdjustIn(BaseModel):
    movement_type: Literal["loss", "disposal", "adjustment"]
    quantity_kg: float = Field(description="Positive amount for loss/disposal; signed for adjustment")
    reason: str = Field(min_length=5, max_length=500)
    version: int


class ReviewIn(BaseModel):
    decision: Literal["verify", "reject"]
    media_id: uuid.UUID | None = None
    note: str = Field(min_length=10, max_length=1000)
    version: int


class OperationResult(BaseModel):
    operation: OperationOut | None
    batches: list[BatchOut]


def serialize(db: Session, batches: list[MaterialBatch]) -> list[BatchOut]:
    cats = {c.id: c for c in db.scalars(select(MaterialCategory).where(MaterialCategory.id.in_({b.category_id for b in batches})))} if batches else {}
    facs = dict(db.execute(select(Facility.id, Facility.name).where(Facility.id.in_({b.facility_id for b in batches}))).all()) if batches else {}
    out = []
    for b in batches:
        o = BatchOut.model_validate(b)
        c = cats[b.category_id]
        o.category_code, o.category_label, o.is_mlp, o.facility_name = c.code, c.label, c.is_mlp, facs.get(b.facility_id, "")
        out.append(o)
    return out


def _visible_batch(db: Session, batch_id: uuid.UUID, principal: Principal) -> MaterialBatch:
    b = db.get(MaterialBatch, batch_id)
    visible = visible_facility_ids(db, principal.scope)
    if b is None or (visible is not None and b.facility_id not in visible):
        raise not_found("Batch")
    return b


def _writable_batch(db: Session, batch_id: uuid.UUID, principal: Principal) -> MaterialBatch:
    b = db.get(MaterialBatch, batch_id)
    if b is None:
        raise not_found("Batch")
    operable_facility(db, b.facility_id, principal)
    return b


@router.get("/batches", response_model=Page[BatchOut])
def list_batches(db: DB, params: PageParams = Depends(), facility_id: uuid.UUID | None = None, category: str | None = None,
                 status: BatchStatus | None = BatchStatus.ACTIVE, verification: VerificationStatus | None = None,
                 q: str | None = None, principal: Principal = Depends(require(*READERS))):
    stmt = select(MaterialBatch)
    visible = visible_facility_ids(db, principal.scope)
    if visible is not None:
        stmt = stmt.where(MaterialBatch.facility_id.in_(visible or {uuid.UUID(int=0)}))
    if facility_id:
        stmt = stmt.where(MaterialBatch.facility_id == facility_id)
    if category:
        stmt = stmt.join(MaterialCategory).where(MaterialCategory.code == category)
    if status:
        stmt = stmt.where(MaterialBatch.status == status)
    if verification:
        stmt = stmt.where(MaterialBatch.verification_status == verification)
    if q:
        stmt = stmt.where(MaterialBatch.code.ilike(f"%{q.strip()[:40]}%"))
    page = paginate(db, stmt, params, {"created": MaterialBatch.created_at, "weight": MaterialBatch.current_weight_kg,
                                       "code": MaterialBatch.code}, "-created")
    page["items"] = serialize(db, page["items"])
    return page


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def batch_detail(batch_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*READERS))):
    b = _visible_batch(db, batch_id, principal)
    movements = list(db.scalars(select(BatchMovement).where(BatchMovement.batch_id == b.id).order_by(BatchMovement.occurred_at)))
    actors = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({m.actor_id for m in movements if m.actor_id}))).all()) if movements else {}

    def links(column_self, column_other):
        rows = db.execute(
            select(MaterialBatch.id, MaterialBatch.code, MaterialCategory.label, BatchLineage.weight_kg, BatchOperation.operation_type)
            .join(BatchLineage, column_other == MaterialBatch.id)
            .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
            .join(BatchOperation, BatchOperation.id == BatchLineage.operation_id)
            .where(column_self == b.id).order_by(MaterialBatch.code)
        ).all()
        return [LinkOut(batch_id=r[0], code=r[1], category_label=r[2], weight_kg=r[3], operation_type=r[4]) for r in rows]

    op_ids = {m.operation_id for m in movements if m.operation_id}
    ops = list(db.scalars(select(BatchOperation).where(BatchOperation.id.in_(op_ids)).order_by(BatchOperation.created_at))) if op_ids else []
    mv_out = []
    for m in movements:
        o = MovementOut.model_validate(m)
        o.actor_name = actors.get(m.actor_id)
        mv_out.append(o)
    return BatchDetail(
        batch=serialize(db, [b])[0], movements=mv_out,
        parents=links(BatchLineage.child_batch_id, BatchLineage.parent_batch_id),
        children=links(BatchLineage.parent_batch_id, BatchLineage.child_batch_id),
        operations=[OperationOut.model_validate(o) for o in ops],
        verification_evidence_url=signed_url(b.verification_media_id),
        ledger_sum_kg=sum((m.quantity_kg for m in movements), start=0),
    )


@router.post("/batches/{batch_id}/sort", response_model=OperationResult, summary="Sort a batch into measured fractions")
def sort(batch_id: uuid.UUID, body: SortIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    _writable_batch(db, batch_id, principal)
    op, children = inventory.sort_batch(db, batch_id, [o.model_dump() for o in body.outputs], principal.id,
                                        input_kg=body.input_kg, expected_version=body.version, notes=body.notes)
    audit(db, principal, "batch.sorted", "material_batch", batch_id,
          after={"input_kg": str(op.input_kg), "output_kg": str(op.output_kg), "difference_kg": str(op.difference_kg)})
    db.commit()
    return OperationResult(operation=OperationOut.model_validate(op), batches=serialize(db, children))


@router.post("/batches/{batch_id}/split", response_model=OperationResult)
def split(batch_id: uuid.UUID, body: SplitIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    _writable_batch(db, batch_id, principal)
    op, children = inventory.split_batch(db, batch_id, body.parts_kg, principal.id, expected_version=body.version, notes=body.notes)
    audit(db, principal, "batch.split", "material_batch", batch_id, after={"parts": [str(p) for p in body.parts_kg]})
    db.commit()
    return OperationResult(operation=OperationOut.model_validate(op), batches=serialize(db, children))


@router.post("/merge", response_model=OperationResult)
def merge(body: MergeIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    for bid in body.batch_ids:
        _writable_batch(db, bid, principal)
    op, merged = inventory.merge_batches(db, body.batch_ids, principal.id, notes=body.notes, storage_location=body.storage_location)
    audit(db, principal, "batch.merged", "material_batch", merged.id, after={"sources": [str(b) for b in body.batch_ids]})
    db.commit()
    return OperationResult(operation=OperationOut.model_validate(op), batches=serialize(db, [merged]))


@router.post("/batches/{batch_id}/adjust", response_model=MovementOut, summary="Record a loss, disposal or correction (reason required)")
def adjust(batch_id: uuid.UUID, body: AdjustIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    _writable_batch(db, batch_id, principal)
    m = inventory.adjust_batch(db, batch_id, MovementType(body.movement_type), body.quantity_kg, body.reason, principal.id,
                               expected_version=body.version)
    audit(db, principal, f"batch.{body.movement_type}", "material_batch", batch_id, after={"kg": str(m.quantity_kg), "reason": body.reason})
    db.commit()
    return MovementOut.model_validate(m)


@router.post("/batches/{batch_id}/mlp-review", response_model=BatchOut,
             summary="Evidence review of a suspected multilayer-plastic batch (never automatic)")
def mlp_review(batch_id: uuid.UUID, body: ReviewIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    _writable_batch(db, batch_id, principal)
    b = inventory.review_mlp(db, batch_id, body.decision, body.media_id, body.note, principal.id, expected_version=body.version)
    audit(db, principal, f"batch.mlp_{body.decision}", "material_batch", batch_id, after={"media_id": str(body.media_id)})
    db.commit()
    return serialize(db, [b])[0]
