import secrets
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.errors import forbidden, not_found
from app.models import CollectionEvent, CollectionPoint, Complaint, Household, PickupRequest, Village
from app.models.enums import RoleKey
from app.schemas.collection import HouseholdIn, HouseholdOut, HouseholdPatch, PickupRequestOut
from app.schemas.common import Page
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.scope import AccessScope
from app.security.tokens import utcnow
from app.services.audit import audit, snapshot
from app.services.collections import serialize_events
from app.services.listing import PageParams, paginate

router = APIRouter()


def household_out(h: Household, scope: AccessScope) -> HouseholdOut:
    """PII minimisation: evaluators get initials only; collectors don't see phone numbers."""
    own = h.id in scope.household_ids
    admin = scope.is_super or RoleKey.GP_ADMIN in scope.roles
    full = own or admin
    redact = scope.is_evaluator and not scope.is_super
    name = h.head_name
    if redact:
        name = " ".join(p[0] + "." for p in h.head_name.split() if p) or "—"
    return HouseholdOut(
        id=h.id,
        village_id=h.village_id,
        household_code=h.household_code,
        head_name=name,
        phone=h.phone if full and not redact else None,
        address_line=None if redact else h.address_line,
        lat=h.lat if full and not redact else None,
        lng=h.lng if full and not redact else None,
        members_count=h.members_count,
        active=h.active,
        is_sample=h.is_sample,
        has_account=h.user_id is not None,
        created_at=h.created_at,
        redacted=redact,
    )


def _get_visible(db, household_id: uuid.UUID, scope: AccessScope) -> Household:
    h = db.get(Household, household_id)
    if h is None or h.deleted_at is not None:
        raise not_found("Household")
    if h.id not in scope.household_ids:
        scope.ensure_village(h.village_id, "Household")
    return h


@router.get("", response_model=Page[HouseholdOut])
def list_households(
    db: DB,
    principal: CurrentUser,
    params: PageParams = Depends(),
    village_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=80),
    active: bool | None = None,
):
    scope = principal.scope
    stmt = select(Household).where(Household.deleted_at.is_(None))
    if RoleKey.HOUSEHOLD in scope.roles and not (scope.sees_all or scope.village_ids):
        stmt = stmt.where(Household.id.in_(scope.household_ids or {uuid.UUID(int=0)}))
    else:
        stmt = stmt.where(scope.village_clause(Household.village_id))
    if village_id:
        stmt = stmt.where(Household.village_id == village_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Household.head_name).like(like), func.lower(Household.household_code).like(like)))
    if active is not None:
        stmt = stmt.where(Household.active.is_(active))
    page = paginate(db, stmt, params, {"code": Household.household_code, "name": Household.head_name, "created": Household.created_at}, "code")
    page["items"] = [household_out(h, scope) for h in page["items"]]
    return page


@router.get("/{household_id}")
def get_household(household_id: uuid.UUID, db: DB, principal: CurrentUser):
    h = _get_visible(db, household_id, principal.scope)
    point_ids = list(db.scalars(select(CollectionPoint.id).where(CollectionPoint.household_id == h.id)))
    events = (
        db.scalars(
            select(CollectionEvent)
            .where(CollectionEvent.collection_point_id.in_(point_ids))
            .order_by(CollectionEvent.collected_at.desc())
            .limit(20)
        ).all()
        if point_ids
        else []
    )
    requests = db.scalars(
        select(PickupRequest).where(PickupRequest.household_id == h.id).order_by(PickupRequest.created_at.desc()).limit(20)
    ).all()
    village = db.get(Village, h.village_id)
    return {
        "household": household_out(h, principal.scope),
        "village_name": village.name if village else None,
        "collection_point_ids": point_ids,
        "recent_collections": serialize_events(db, events),
        "pickup_requests": [PickupRequestOut.model_validate(r) for r in requests],
        "open_complaints": db.scalar(
            select(func.count()).where(Complaint.household_id == h.id, Complaint.status.in_(["open", "assigned", "under_review"]))
        ),
    }


@router.post("", response_model=HouseholdOut, status_code=201)
def create_household(body: HouseholdIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    principal.scope.ensure_village(body.village_id, "Village")
    village = db.get(Village, body.village_id)
    h = Household(**body.model_dump(), household_code=f"{village.code}-HH-{secrets.token_hex(3).upper()}", consent_at=utcnow())
    db.add(h)
    db.flush()
    audit(db, principal, "household.created", "household", h.id, after={"village_id": h.village_id, "code": h.household_code})
    db.commit()
    db.refresh(h)
    return household_out(h, principal.scope)


@router.patch("/{household_id}", response_model=HouseholdOut)
def update_household(household_id: uuid.UUID, body: HouseholdPatch, db: DB, principal: CurrentUser):
    h = _get_visible(db, household_id, principal.scope)
    own = h.id in principal.scope.household_ids
    if not (own or principal.scope.is_super or RoleKey.GP_ADMIN in principal.scope.roles):
        raise forbidden()
    data = body.model_dump(exclude_unset=True)
    if own and not principal.scope.has(RoleKey.GP_ADMIN):
        data.pop("active", None)
    before = snapshot(h, *data.keys())
    for k, v in data.items():
        setattr(h, k, v)
    audit(db, principal, "household.updated", "household", h.id, before, data)
    db.commit()
    db.refresh(h)
    return household_out(h, principal.scope)


@router.delete("/{household_id}", status_code=204, summary="Erase personal data (retention policy); keeps anonymous traceability")
def erase_household(household_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    h = _get_visible(db, household_id, principal.scope)
    h.head_name = "Erased household"
    h.phone = None
    h.address_line = None
    h.lat = None
    h.lng = None
    h.active = False
    h.deleted_at = utcnow()
    audit(db, principal, "household.erased", "household", h.id)
    db.commit()
