import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.errors import conflict, not_found
from app.models import CollectionEvent, CollectionPoint, Household, UserMembership, Village
from app.models.enums import RoleKey
from app.schemas.common import Page
from app.schemas.identity import VillageDetail, VillageIn, VillageOut, VillagePatch, VillagePublic
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit, snapshot
from app.services.listing import PageParams, paginate

router = APIRouter()


@router.get("/public", response_model=list[VillagePublic], summary="Public list for citizen registration (names only)")
def public_villages(db: DB):
    return db.scalars(select(Village).where(Village.deleted_at.is_(None)).order_by(Village.name)).all()


@router.get("", response_model=Page[VillageOut])
def list_villages(
    db: DB,
    principal: CurrentUser,
    params: PageParams = Depends(),
    q: str | None = Query(None, max_length=80),
    organization_id: uuid.UUID | None = None,
):
    scope = principal.scope
    stmt = select(Village).where(Village.deleted_at.is_(None))
    if not scope.sees_all:
        stmt = stmt.where(Village.id.in_(scope.village_ids | scope.household_village_ids or {uuid.UUID(int=0)}))
    if q:
        stmt = stmt.where(func.lower(Village.name).like(f"%{q.lower()}%"))
    if organization_id:
        stmt = stmt.where(Village.organization_id == organization_id)
    return paginate(db, stmt, params, {"name": Village.name, "code": Village.code, "created": Village.created_at}, "name")


@router.get("/{village_id}", response_model=VillageDetail)
def get_village(village_id: uuid.UUID, db: DB, principal: CurrentUser):
    v = db.get(Village, village_id)
    if v is None or v.deleted_at is not None:
        raise not_found("Village")
    if v.id not in principal.scope.household_village_ids:
        principal.scope.ensure_village(v.id, "Village")
    since = utcnow() - timedelta(days=30)
    stats = {
        "collection_points": db.scalar(
            select(func.count()).where(CollectionPoint.village_id == v.id, CollectionPoint.deleted_at.is_(None))
        ),
        "households": db.scalar(select(func.count()).where(Household.village_id == v.id, Household.deleted_at.is_(None))),
        "collectors": db.scalar(
            select(func.count(func.distinct(UserMembership.user_id))).where(
                UserMembership.organization_id == v.organization_id, UserMembership.role_key == RoleKey.COLLECTOR
            )
        ),
        "collected_kg_30d": float(
            db.scalar(
                select(func.coalesce(func.sum(CollectionEvent.weight_kg), 0)).where(
                    CollectionEvent.village_id == v.id, CollectionEvent.collected_at >= since
                )
            )
        ),
    }
    out = VillageDetail.model_validate(v)
    out.stats = stats
    return out


@router.post("", response_model=VillageOut, status_code=201)
def create_village(body: VillageIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    principal.scope.ensure_org(body.organization_id, "Organization")
    if db.scalar(select(Village.id).where(Village.code == body.code)):
        raise conflict("CODE_TAKEN", "Village code already exists")
    v = Village(**body.model_dump())
    db.add(v)
    db.flush()
    audit(db, principal, "village.created", "village", v.id, after=body.model_dump())
    db.commit()
    db.refresh(v)
    return v


@router.patch("/{village_id}", response_model=VillageOut)
def update_village(village_id: uuid.UUID, body: VillagePatch, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    v = db.get(Village, village_id)
    if v is None or v.deleted_at is not None:
        raise not_found("Village")
    principal.scope.ensure_org(v.organization_id, "Village")
    data = body.model_dump(exclude_unset=True)
    before = snapshot(v, *data.keys())
    for k, val in data.items():
        setattr(v, k, val)
    audit(db, principal, "village.updated", "village", v.id, before, data)
    db.commit()
    db.refresh(v)
    return v
