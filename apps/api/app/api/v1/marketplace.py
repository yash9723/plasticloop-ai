"""Material exchange: facilities list sorted material, processors/buyers ask for quotes or make offers, accepted offers become sales.
Prices are marked hypothetical unless the operator says otherwise; no payment is processed here."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.facilities import operable_facility, visible_facility_ids
from app.core.errors import bad_request, conflict, not_found
from app.models import Facility, MaterialBatch, MaterialCategory, MaterialListing, MaterialOffer, Organization, Sale
from app.models.enums import BatchStatus, DataOrigin, ListingStatus, MovementType, OfferStatus, RoleKey
from app.schemas.common import Kg, KgIn
from app.security.deps import DB, Principal, require
from app.services import inventory
from app.services.audit import audit
from app.services.inventory import q
from app.services.notifications import facility_operators, notify

router = APIRouter()
VIEWERS = (RoleKey.MRF_OPERATOR, RoleKey.PROCESSOR, RoleKey.EVALUATOR)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    buyer_org_id: uuid.UUID
    kind: str
    quantity_kg: Kg
    price_paise_per_kg: int | None
    status: OfferStatus
    message: str | None
    created_at: datetime
    buyer_name: str = ""
    sale_id: uuid.UUID | None = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    facility_id: uuid.UUID
    batch_id: uuid.UUID
    category_id: uuid.UUID
    quantity_kg: Kg
    asking_price_paise_per_kg: int | None
    price_is_hypothetical: bool
    quality_notes: str | None
    status: ListingStatus
    data_origin: DataOrigin
    version: int
    created_at: datetime
    facility_name: str = ""
    category_label: str = ""
    verification_status: str = ""
    batch_code: str = ""
    offers: list[OfferOut] = []


class ListingIn(BaseModel):
    batch_id: uuid.UUID
    quantity_kg: KgIn
    asking_price_paise_per_kg: int | None = Field(None, ge=0, le=100_000)
    price_is_hypothetical: bool = True
    quality_notes: str | None = Field(None, max_length=1000)


class OfferIn(BaseModel):
    kind: Literal["quote_request", "offer"]
    quantity_kg: KgIn
    price_paise_per_kg: int | None = Field(None, ge=0, le=100_000)
    message: str | None = Field(None, max_length=1000)


class RespondIn(BaseModel):
    decision: Literal["accept", "reject"]


class SaleIn(BaseModel):
    quantity_kg: KgIn
    unit_price_paise: int = Field(ge=0, le=100_000)
    sold_on: date
    invoice_number: str | None = Field(None, max_length=40)
    shipment_note: str | None = Field(None, max_length=500)


def _serialize(db: Session, listings: list[MaterialListing], principal: Principal) -> list[ListingOut]:
    if not listings:
        return []
    facs = dict(db.execute(select(Facility.id, Facility.name).where(Facility.id.in_({x.facility_id for x in listings}))).all())
    cats = dict(db.execute(select(MaterialCategory.id, MaterialCategory.label).where(MaterialCategory.id.in_({x.category_id for x in listings}))).all())
    batches = {b.id: b for b in db.scalars(select(MaterialBatch).where(MaterialBatch.id.in_({x.batch_id for x in listings})))}
    offers = list(db.scalars(select(MaterialOffer).where(MaterialOffer.listing_id.in_([x.id for x in listings])).order_by(MaterialOffer.created_at)))
    sales = dict(db.execute(select(Sale.offer_id, Sale.id).where(Sale.offer_id.in_([o.id for o in offers]))).all()) if offers else {}
    buyers = dict(db.execute(select(Organization.id, Organization.name).where(Organization.id.in_({o.buyer_org_id for o in offers}))).all()) if offers else {}
    seller = principal.scope.sees_all or bool(principal.scope.facility_ids)
    out = []
    for x in listings:
        o = ListingOut.model_validate(x)
        b = batches[x.batch_id]
        o.facility_name, o.category_label = facs.get(x.facility_id, ""), cats.get(x.category_id, "")
        o.verification_status, o.batch_code = str(b.verification_status), b.code
        visible = [of for of in offers if of.listing_id == x.id and (seller or of.buyer_org_id in principal.scope.org_ids)]
        o.offers = []
        for of in visible:
            oo = OfferOut.model_validate(of)
            oo.buyer_name, oo.sale_id = buyers.get(of.buyer_org_id, ""), sales.get(of.id)
            o.offers.append(oo)
        out.append(o)
    return out


def _listing(db: Session, listing_id: uuid.UUID, principal: Principal) -> MaterialListing:
    x = db.get(MaterialListing, listing_id)
    if x is None:
        raise not_found("Listing")
    visible = visible_facility_ids(db, principal.scope)
    is_seller = visible is None or x.facility_id in visible
    if not is_seller and not (RoleKey.PROCESSOR in principal.scope.roles and x.status != ListingStatus.WITHDRAWN):
        raise not_found("Listing")
    return x


@router.get("/listings", response_model=list[ListingOut])
def list_listings(db: DB, status: ListingStatus | None = None, principal: Principal = Depends(require(*VIEWERS))):
    stmt = select(MaterialListing).order_by(MaterialListing.created_at.desc()).limit(200)
    visible = visible_facility_ids(db, principal.scope)
    if visible is not None and not principal.scope.has(RoleKey.PROCESSOR):
        stmt = stmt.where(MaterialListing.facility_id.in_(visible or {uuid.UUID(int=0)}))
    elif visible is not None:  # processors browse open/reserved listings plus anything they have offered on
        mine = select(MaterialOffer.listing_id).where(MaterialOffer.buyer_org_id.in_(principal.scope.org_ids or {uuid.UUID(int=0)}))
        stmt = stmt.where(MaterialListing.status.in_([ListingStatus.OPEN, ListingStatus.RESERVED]) | MaterialListing.id.in_(mine))
    if status:
        stmt = stmt.where(MaterialListing.status == status)
    return _serialize(db, list(db.scalars(stmt)), principal)


@router.post("/listings", response_model=ListingOut, status_code=201)
def create_listing(body: ListingIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    batch = db.get(MaterialBatch, body.batch_id)
    if batch is None:
        raise not_found("Batch")
    operable_facility(db, batch.facility_id, principal)
    cat = db.get(MaterialCategory, batch.category_id)
    if cat.is_unsorted or not cat.recoverable:
        raise bad_request("NOT_SALEABLE", "Only sorted, recoverable material can be listed")
    if batch.status != BatchStatus.ACTIVE or q(body.quantity_kg) > q(batch.current_weight_kg):
        raise conflict("INSUFFICIENT_STOCK", f"Batch holds {batch.current_weight_kg} kg")
    x = MaterialListing(facility_id=batch.facility_id, batch_id=batch.id, category_id=batch.category_id, quantity_kg=q(body.quantity_kg),
                        asking_price_paise_per_kg=body.asking_price_paise_per_kg, price_is_hypothetical=body.price_is_hypothetical,
                        quality_notes=body.quality_notes, created_by=principal.id, data_origin=batch.data_origin)
    db.add(x)
    db.flush()
    audit(db, principal, "listing.created", "material_listing", x.id)
    db.commit()
    return _serialize(db, [x], principal)[0]


@router.post("/listings/{listing_id}/withdraw", response_model=ListingOut)
def withdraw(listing_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    x = _listing(db, listing_id, principal)
    operable_facility(db, x.facility_id, principal)
    if x.status == ListingStatus.SOLD:
        raise conflict("ALREADY_SOLD", "A sold listing cannot be withdrawn")
    x.status = ListingStatus.WITHDRAWN
    audit(db, principal, "listing.withdrawn", "material_listing", x.id)
    db.commit()
    return _serialize(db, [x], principal)[0]


@router.post("/listings/{listing_id}/offers", response_model=ListingOut, status_code=201, summary="Ask for a quote or make an offer")
def make_offer(listing_id: uuid.UUID, body: OfferIn, db: DB, principal: Principal = Depends(require(RoleKey.PROCESSOR))):
    x = _listing(db, listing_id, principal)
    if x.status != ListingStatus.OPEN:
        raise conflict("LISTING_CLOSED", "This listing is not open for offers")
    if body.kind == "offer" and body.price_paise_per_kg is None:
        raise bad_request("PRICE_REQUIRED", "An offer needs a price per kg")
    if q(body.quantity_kg) > q(x.quantity_kg):
        raise bad_request("TOO_MUCH", f"Only {x.quantity_kg} kg is listed")
    if len(principal.scope.org_ids) != 1:
        raise bad_request("ORGANIZATION_REQUIRED", "Offers are made on behalf of exactly one organisation")
    of = MaterialOffer(listing_id=x.id, buyer_org_id=next(iter(principal.scope.org_ids)), kind=body.kind, quantity_kg=q(body.quantity_kg),
                       price_paise_per_kg=body.price_paise_per_kg, message=body.message, created_by=principal.id,
                       status=OfferStatus.QUOTE_REQUESTED if body.kind == "quote_request" else OfferStatus.OFFERED, data_origin=x.data_origin)
    db.add(of)
    db.flush()
    notify(db, facility_operators(db, x.facility_id), type="marketplace_offer", title=f"New {body.kind.replace('_', ' ')} for {x.quantity_kg} kg",
           entity_type="material_listing", entity_id=x.id, link="/marketplace")
    audit(db, principal, f"offer.{body.kind}", "material_offer", of.id)
    db.commit()
    return _serialize(db, [x], principal)[0]


@router.post("/offers/{offer_id}/respond", response_model=ListingOut)
def respond(offer_id: uuid.UUID, body: RespondIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    of = db.get(MaterialOffer, offer_id)
    if of is None:
        raise not_found("Offer")
    x = db.get(MaterialListing, of.listing_id)
    operable_facility(db, x.facility_id, principal)
    if of.status != OfferStatus.OFFERED:
        raise conflict("NOT_AN_OPEN_OFFER", "Only open priced offers can be accepted or rejected")
    of.status, of.responded_by = (OfferStatus.ACCEPTED if body.decision == "accept" else OfferStatus.REJECTED), principal.id
    if body.decision == "accept":
        x.status = ListingStatus.RESERVED
    audit(db, principal, f"offer.{body.decision}", "material_offer", of.id)
    db.commit()
    return _serialize(db, [x], principal)[0]


@router.post("/offers/{offer_id}/sale", response_model=ListingOut, summary="Record the sale for an accepted offer (moves stock out)")
def record_sale(offer_id: uuid.UUID, body: SaleIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    of = db.get(MaterialOffer, offer_id)
    if of is None:
        raise not_found("Offer")
    x = db.get(MaterialListing, of.listing_id)
    operable_facility(db, x.facility_id, principal)
    if of.status != OfferStatus.ACCEPTED:
        raise conflict("OFFER_NOT_ACCEPTED", "Accept the offer before recording a sale")
    if db.scalar(select(Sale.id).where(Sale.offer_id == of.id)):
        raise conflict("ALREADY_SOLD", "This offer already has a sale")
    qty = q(body.quantity_kg)
    if qty <= 0 or qty > q(x.quantity_kg):
        raise bad_request("INVALID_QUANTITY", f"Sell between 0 and {x.quantity_kg} kg")
    batch = inventory.lock_batch(db, x.batch_id)
    sale = Sale(listing_id=x.id, offer_id=of.id, batch_id=batch.id, facility_id=x.facility_id, buyer_org_id=of.buyer_org_id, quantity_kg=qty,
                unit_price_paise=body.unit_price_paise, total_paise=int(qty * body.unit_price_paise), sold_on=body.sold_on,
                invoice_number=body.invoice_number, invoice_date=body.sold_on if body.invoice_number else None,
                shipment_note=body.shipment_note, created_by=principal.id, data_origin=x.data_origin)
    db.add(sale)
    db.flush()
    inventory._move(db, batch, MovementType.TRANSFER_OUT, -qty, principal.id, reference_type="sale", reference_id=sale.id,
                    reason=f"Sold ({body.invoice_number or 'no invoice no.'})")
    x.status = ListingStatus.SOLD
    audit(db, principal, "sale.recorded", "sale", sale.id, after={"kg": str(qty), "total_paise": sale.total_paise})
    db.commit()
    return _serialize(db, [x], principal)[0]

