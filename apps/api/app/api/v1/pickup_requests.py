import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import CollectionPoint, Household, PickupRequest, UserMembership, Village
from app.models.enums import PickupStatus, RoleKey, Severity
from app.schemas.collection import PickupRequestIn, PickupRequestOut, PickupRequestPatch
from app.schemas.common import Page
from app.security.deps import DB, CurrentUser
from app.security.tokens import utcnow
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.notifications import notify, village_admins

router = APIRouter()

TRANSITIONS = {
    PickupStatus.SUBMITTED: {PickupStatus.ASSIGNED, PickupStatus.CANCELLED},
    PickupStatus.ASSIGNED: {PickupStatus.IN_PROGRESS, PickupStatus.COMPLETED, PickupStatus.CANCELLED, PickupStatus.ASSIGNED},
    PickupStatus.IN_PROGRESS: {PickupStatus.COMPLETED, PickupStatus.CANCELLED},
    PickupStatus.COMPLETED: set(),
    PickupStatus.CANCELLED: set(),
}


@router.get("", response_model=Page[PickupRequestOut])
def list_requests(
    db: DB,
    principal: CurrentUser,
    params: PageParams = Depends(),
    status: PickupStatus | None = None,
    village_id: uuid.UUID | None = None,
    mine: bool = False,
):
    scope = principal.scope
    if scope.sees_all or scope.village_ids:
        stmt = select(PickupRequest).where(scope.village_clause(PickupRequest.village_id))
    else:
        stmt = select(PickupRequest).where(PickupRequest.household_id.in_(scope.household_ids or {uuid.UUID(int=0)}))
    if status:
        stmt = stmt.where(PickupRequest.status == status)
    if village_id:
        stmt = stmt.where(PickupRequest.village_id == village_id)
    if mine:
        stmt = stmt.where(PickupRequest.assigned_collector_id == principal.id)
    return paginate(db, stmt, params, {"created": PickupRequest.created_at, "preferred": PickupRequest.preferred_date}, "-created")


@router.post("", response_model=PickupRequestOut, status_code=201)
def create_request(body: PickupRequestIn, db: DB, principal: CurrentUser):
    scope = principal.scope
    if scope.is_evaluator and not scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    household = None
    if RoleKey.HOUSEHOLD in scope.roles and not scope.has(RoleKey.GP_ADMIN):
        if not scope.household_ids:
            raise bad_request("NO_HOUSEHOLD", "Your account is not linked to a household")
        household = db.get(Household, next(iter(scope.household_ids)))
    elif scope.has(RoleKey.GP_ADMIN, RoleKey.COLLECTOR):
        if body.household_id:
            household = db.get(Household, body.household_id)
            if household is None:
                raise not_found("Household")
            scope.ensure_village(household.village_id, "Household")
        elif not body.collection_point_id:
            raise bad_request("TARGET_REQUIRED", "Provide a household or a collection point")
    else:
        raise forbidden()

    cp = None
    if body.collection_point_id:
        cp = db.get(CollectionPoint, body.collection_point_id)
        if cp is None or cp.deleted_at is not None:
            raise not_found("Collection point")
        if household and cp.village_id != household.village_id:
            raise bad_request("INVALID_POINT", "Collection point is in a different village")
        if not household:
            scope.ensure_village(cp.village_id, "Collection point")
    elif household:
        cp = db.scalar(select(CollectionPoint).where(CollectionPoint.household_id == household.id, CollectionPoint.deleted_at.is_(None)))

    village_id = household.village_id if household else cp.village_id
    req = PickupRequest(
        village_id=village_id,
        household_id=household.id if household else None,
        collection_point_id=cp.id if cp else None,
        waste_stream_id=body.waste_stream_id,
        requested_by=principal.id,
        preferred_date=body.preferred_date,
        estimated_weight_kg=body.estimated_weight_kg,
        notes=body.notes,
    )
    db.add(req)
    db.flush()
    notify(
        db, village_admins(db, village_id), type="pickup_request_created", title="New pickup request",
        body=f"Requested for {body.preferred_date or 'the next available slot'}", entity_type="pickup_request",
        entity_id=req.id, link="/pickup-requests",
    )
    audit(db, principal, "pickup_request.created", "pickup_request", req.id)
    db.commit()
    db.refresh(req)
    return req


@router.patch("/{request_id}", response_model=PickupRequestOut)
def update_request(request_id: uuid.UUID, body: PickupRequestPatch, db: DB, principal: CurrentUser):
    scope = principal.scope
    req = db.get(PickupRequest, request_id)
    if req is None:
        raise not_found("Pickup request")
    own = req.household_id in scope.household_ids
    if not own:
        scope.ensure_village(req.village_id, "Pickup request")
    if req.version != body.version:
        raise conflict("VERSION_CONFLICT", "This request was changed by someone else. Reload and try again.")
    if scope.is_evaluator and not scope.is_super:
        raise forbidden("Evaluator accounts are read-only")

    is_admin = scope.has(RoleKey.GP_ADMIN)
    is_assigned_collector = RoleKey.COLLECTOR in scope.roles and req.assigned_collector_id == principal.id
    target = body.status or (PickupStatus.ASSIGNED if body.assigned_collector_id else req.status)

    if target != req.status or target == PickupStatus.ASSIGNED:
        if target not in TRANSITIONS[req.status]:
            raise bad_request("INVALID_TRANSITION", f"Cannot move from {req.status} to {target}")
        if target == PickupStatus.CANCELLED:
            if not (is_admin or (own and req.status in (PickupStatus.SUBMITTED, PickupStatus.ASSIGNED))):
                raise forbidden("Only the requester (before pickup starts) or an admin can cancel")
            req.cancelled_reason = body.cancelled_reason
        elif target == PickupStatus.ASSIGNED:
            if not is_admin:
                raise forbidden("Only a Panchayat admin can assign pickups")
            if body.assigned_collector_id is None:
                raise bad_request("COLLECTOR_REQUIRED", "Choose a collector")
            village = db.get(Village, req.village_id)
            ok = db.scalar(
                select(UserMembership.id).where(
                    UserMembership.user_id == body.assigned_collector_id,
                    UserMembership.organization_id == village.organization_id,
                    UserMembership.role_key == RoleKey.COLLECTOR,
                )
            )
            if not ok:
                raise bad_request("INVALID_COLLECTOR", "Assigned user is not a collector for this village")
            req.assigned_collector_id = body.assigned_collector_id
            notify(
                db, [body.assigned_collector_id], type="pickup_assigned", title="Pickup assigned to you",
                severity=Severity.INFO, entity_type="pickup_request", entity_id=req.id, link="/collector",
            )
        elif target in (PickupStatus.IN_PROGRESS, PickupStatus.COMPLETED):
            if not (is_admin or is_assigned_collector):
                raise forbidden("Only the assigned collector or an admin can update progress")
            if target == PickupStatus.COMPLETED:
                req.completed_at = utcnow()
        req.status = target
    audit(db, principal, "pickup_request.updated", "pickup_request", req.id, after=body.model_dump(mode="json"))
    db.commit()
    db.refresh(req)
    return req
