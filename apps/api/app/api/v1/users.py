import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.errors import bad_request, forbidden, not_found
from app.models import Role, User, UserMembership, Village
from app.models.enums import RoleKey
from app.schemas.common import Page
from app.schemas.identity import MePatch, RoleOut, UserBrief, UserOut
from app.security.deps import DB, CurrentUser, Principal, require
from app.services.audit import audit, snapshot
from app.services.listing import PageParams, paginate

router = APIRouter()

GP_MANAGEABLE = {RoleKey.COLLECTOR, RoleKey.DRIVER}


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        phone=u.phone,
        full_name=u.full_name,
        is_active=u.is_active,
        preferred_language=u.preferred_language,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        is_sample=u.is_sample,
        role_keys=sorted({m.role_key for m in u.memberships}),
    )


def _members_of(org_ids: set[uuid.UUID]):
    return select(UserMembership.user_id).where(UserMembership.organization_id.in_(org_ids))


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DB,
    params: PageParams = Depends(),
    role: str | None = None,
    organization_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=80),
    active: bool | None = None,
    principal: Principal = Depends(require(RoleKey.GP_ADMIN)),
):
    stmt = select(User).where(User.deleted_at.is_(None))
    if not principal.scope.is_super:
        stmt = stmt.where(User.id.in_(_members_of(principal.scope.org_ids)))
    if role:
        stmt = stmt.where(User.id.in_(select(UserMembership.user_id).where(UserMembership.role_key == role)))
    if organization_id:
        stmt = stmt.where(User.id.in_(_members_of({organization_id})))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    page = paginate(db, stmt, params, {"name": User.full_name, "created": User.created_at, "last_login": User.last_login_at}, "name")
    page["items"] = [_user_out(u) for u in page["items"]]
    return page


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: DB, _: CurrentUser):
    return db.scalars(select(Role).order_by(Role.key)).all()


@router.get("/assignable", response_model=list[UserBrief], summary="Collectors/drivers that can be assigned in a village")
def assignable(
    db: DB,
    village_id: uuid.UUID,
    role: RoleKey = RoleKey.COLLECTOR,
    principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR)),
):
    village = db.get(Village, village_id)
    if village is None:
        raise not_found("Village")
    principal.scope.ensure_village(village.id, "Village")
    stmt = (
        select(User)
        .join(UserMembership, UserMembership.user_id == User.id)
        .where(
            UserMembership.organization_id == village.organization_id,
            UserMembership.role_key == role,
            or_(UserMembership.village_id.is_(None), UserMembership.village_id == village.id),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(User.full_name)
    )
    return db.scalars(stmt).unique().all()


@router.patch("/me", response_model=UserOut)
def update_me(body: MePatch, principal: CurrentUser, db: DB):
    user = principal.user
    data = body.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"] and db.scalar(select(User.id).where(User.phone == data["phone"], User.id != user.id)):
        raise bad_request("PHONE_TAKEN", "Phone number is used by another account")
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise not_found("User")
    if not principal.scope.is_super and not ({m.organization_id for m in user.memberships} & principal.scope.org_ids):
        raise not_found("User")
    return _user_out(user)


def _set_active(user_id: uuid.UUID, active: bool, db, principal: Principal) -> UserOut:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise not_found("User")
    if user.id == principal.id:
        raise bad_request("SELF_CHANGE", "You cannot change your own account status")
    if not principal.scope.is_super:
        orgs = {m.organization_id for m in user.memberships}
        roles = {m.role_key for m in user.memberships}
        if not orgs or not orgs <= principal.scope.org_ids:
            raise not_found("User")
        if not roles <= GP_MANAGEABLE:
            raise forbidden("Only collectors and drivers can be managed by a Panchayat admin")
    before = snapshot(user, "is_active")
    user.is_active = active
    if not active:
        from app.api.v1.auth import _revoke_all_for_user

        _revoke_all_for_user(db, user.id, "account_disabled")
    audit(db, principal, "user.activated" if active else "user.deactivated", "user", user.id, before, {"is_active": active})
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    return _set_active(user_id, False, db, principal)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate(user_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    return _set_active(user_id, True, db, principal)
