import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import MaterialCategory, MediaFile, Organization, ProcessingOutcome, ProcessingPartner, ProcessingTransfer
from app.models.enums import DocumentationStatus, EvidenceStatus, OrgType, RoleKey
from app.schemas.common import Kg
from app.security.deps import DB, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit
from app.services.media import signed_url

router = APIRouter()
VIEWERS = (RoleKey.MRF_OPERATOR, RoleKey.PROCESSOR, RoleKey.GP_ADMIN, RoleKey.EVALUATOR)


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    display_name: str
    address: str | None
    supported_category_codes: list[str]
    acceptance_criteria: str | None
    capabilities: str | None
    authorization_refs: list
    documentation_status: DocumentationStatus
    documentation_reviewed_at: datetime | None
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    lat: float | None
    lng: float | None
    active: bool
    is_sample: bool
    documentation_url: str | None = None
    received_kg: Kg = Decimal("0")
    recovered_reviewed_kg: Kg = Decimal("0")
    transfers: int = 0


class PartnerIn(BaseModel):
    display_name: str = Field(min_length=3, max_length=200)
    address: str | None = Field(None, max_length=500)
    supported_category_codes: list[str] = Field(min_length=1, max_length=10)
    acceptance_criteria: str | None = Field(None, max_length=1000)
    capabilities: str | None = Field(None, max_length=1000)
    contact_name: str | None = Field(None, max_length=120)
    contact_phone: str | None = Field(None, pattern=r"^[0-9+ -]{7,20}$")
    contact_email: str | None = Field(None, max_length=254)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


class DocumentIn(BaseModel):
    media_id: uuid.UUID
    authorization_refs: list[str] = Field(default_factory=list, max_length=10, description="e.g. registration / authorisation numbers")


class DocReviewIn(BaseModel):
    decision: Literal["verify", "reject"]


def _out(db, partners: list[ProcessingPartner]) -> list[PartnerOut]:
    ids = [p.id for p in partners]
    stats = {r[0]: r[1:] for r in db.execute(
        select(ProcessingTransfer.partner_id, func.count(), func.coalesce(func.sum(ProcessingTransfer.received_kg), 0))
        .where(ProcessingTransfer.partner_id.in_(ids)).group_by(ProcessingTransfer.partner_id))} if ids else {}
    recovered = dict(db.execute(
        select(ProcessingTransfer.partner_id, func.sum(ProcessingOutcome.output_kg))
        .join(ProcessingOutcome, ProcessingOutcome.transfer_id == ProcessingTransfer.id)
        .where(ProcessingTransfer.partner_id.in_(ids), ProcessingOutcome.evidence_status == EvidenceStatus.REVIEWED_ACCEPTED)
        .group_by(ProcessingTransfer.partner_id)).all()) if ids else {}
    out = []
    for p in partners:
        o = PartnerOut.model_validate(p)
        o.documentation_url = signed_url(p.documentation_media_id)
        n, kg = stats.get(p.id, (0, Decimal("0")))
        o.transfers, o.received_kg, o.recovered_reviewed_kg = n, kg, recovered.get(p.id) or Decimal("0")
        out.append(o)
    return out


def _get(db, partner_id: uuid.UUID) -> ProcessingPartner:
    p = db.get(ProcessingPartner, partner_id)
    if p is None or p.deleted_at is not None:
        raise not_found("Processing partner")
    return p


@router.get("", response_model=list[PartnerOut])
def list_partners(db: DB, category: str | None = None, principal: Principal = Depends(require(*VIEWERS))):
    stmt = select(ProcessingPartner).where(ProcessingPartner.deleted_at.is_(None)).order_by(ProcessingPartner.display_name)
    partners = [p for p in db.scalars(stmt) if not category or category in (p.supported_category_codes or [])]
    return _out(db, partners)


@router.get("/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*VIEWERS))):
    return _out(db, [_get(db, partner_id)])[0]


@router.post("", response_model=PartnerOut, status_code=201, summary="Register a processing partner (creates its organisation)")
def create_partner(body: PartnerIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    valid = set(db.scalars(select(MaterialCategory.code)))
    if not set(body.supported_category_codes) <= valid:
        raise bad_request("UNKNOWN_CATEGORY", "Unknown material category")
    org = Organization(name=body.display_name, code=f"PL-PROC-{secrets.token_hex(3).upper()}", org_type=OrgType.PROCESSOR,
                       contact_name=body.contact_name, contact_phone=body.contact_phone)
    db.add(org)
    db.flush()
    p = ProcessingPartner(organization_id=org.id, **body.model_dump())
    db.add(p)
    db.flush()
    audit(db, principal, "partner.created", "processing_partner", p.id)
    db.commit()
    db.refresh(p)
    return _out(db, [p])[0]


@router.post("/{partner_id}/documents", response_model=PartnerOut, summary="Partner submits authorisation documents for review")
def submit_documents(partner_id: uuid.UUID, body: DocumentIn, db: DB, principal: Principal = Depends(require(RoleKey.PROCESSOR))):
    p = _get(db, partner_id)
    if not (principal.scope.is_super or p.id in principal.scope.partner_ids):
        raise forbidden("You can only submit documents for your own organisation")
    if db.get(MediaFile, body.media_id) is None:
        raise not_found("File")
    p.documentation_media_id, p.authorization_refs = body.media_id, body.authorization_refs
    p.documentation_status = DocumentationStatus.SUBMITTED
    p.documentation_reviewed_by = p.documentation_reviewed_at = None
    audit(db, principal, "partner.documents_submitted", "processing_partner", p.id)
    db.commit()
    return _out(db, [p])[0]


@router.post("/{partner_id}/documents/review", response_model=PartnerOut, summary="Record that partner documents were checked")
def review_documents(partner_id: uuid.UUID, body: DocReviewIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    p = _get(db, partner_id)
    if p.documentation_status != DocumentationStatus.SUBMITTED:
        raise conflict("NOTHING_TO_REVIEW", "No submitted documents to review")
    if p.id in principal.scope.partner_ids:
        raise conflict("SELF_REVIEW", "A partner cannot review its own documents")
    p.documentation_status = DocumentationStatus.REVIEWED_VERIFIED if body.decision == "verify" else DocumentationStatus.REVIEWED_REJECTED
    p.documentation_reviewed_by, p.documentation_reviewed_at = principal.id, utcnow()
    audit(db, principal, f"partner.documents_{body.decision}", "processing_partner", p.id)
    db.commit()
    return _out(db, [p])[0]
