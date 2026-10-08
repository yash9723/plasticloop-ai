import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import CollectionPoint, Complaint, Household
from app.models.enums import ComplaintStatus, RoleKey, Severity
from app.schemas.collection import ComplaintIn, ComplaintOut, ComplaintPatch
from app.schemas.common import Page
from app.security.deps import DB, CurrentUser, Principal
from app.security.tokens import utcnow
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.media import signed_url
from app.services.notifications import notify, village_admins

router = APIRouter()

TRANSITIONS = {
    ComplaintStatus.OPEN: {ComplaintStatus.ASSIGNED, ComplaintStatus.UNDER_REVIEW, ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED},
    ComplaintStatus.ASSIGNED: {ComplaintStatus.UNDER_REVIEW, ComplaintStatus.RESOLVED, ComplaintStatus.ASSIGNED},
    ComplaintStatus.UNDER_REVIEW: {ComplaintStatus.RESOLVED, ComplaintStatus.ASSIGNED},
    ComplaintStatus.RESOLVED: {ComplaintStatus.CLOSED, ComplaintStatus.UNDER_REVIEW},
    ComplaintStatus.CLOSED: set(),
}


def _out(c: Complaint) -> ComplaintOut:
    out = ComplaintOut.model_validate(c)
    out.photo_url = signed_url(c.media_id)
    return out


def _visible(db, complaint_id: uuid.UUID, principal: Principal) -> Complaint:
    c = db.get(Complaint, complaint_id)
    if c is None:
        raise not_found("Complaint")
    if c.household_id not in principal.scope.household_ids and c.raised_by != principal.id:
        principal.scope.ensure_village(c.village_id, "Complaint")
    return c


@router.get("", response_model=Page[ComplaintOut])
def list_complaints(db: DB, principal: CurrentUser, params: PageParams = Depends(), status: ComplaintStatus | None = None,
                    village_id: uuid.UUID | None = None, assigned_to_me: bool = False):
    scope = principal.scope
    if scope.sees_all or scope.village_ids:
        stmt = select(Complaint).where(scope.village_clause(Complaint.village_id))
    else:
        stmt = select(Complaint).where(Complaint.raised_by == principal.id)
    if status:
        stmt = stmt.where(Complaint.status == status)
    if village_id:
        stmt = stmt.where(Complaint.village_id == village_id)
    if assigned_to_me:
        stmt = stmt.where(Complaint.assigned_to == principal.id)
    page = paginate(db, stmt, params, {"created": Complaint.created_at, "status": Complaint.status}, "-created")
    page["items"] = [_out(c) for c in page["items"]]
    return page


@router.get("/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: uuid.UUID, db: DB, principal: CurrentUser):
    return _out(_visible(db, complaint_id, principal))


@router.post("", response_model=ComplaintOut, status_code=201)
def create_complaint(body: ComplaintIn, db: DB, principal: CurrentUser):
    scope = principal.scope
    if scope.is_evaluator and not scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    household_id = None
    if scope.household_ids and not scope.has(RoleKey.GP_ADMIN, RoleKey.COLLECTOR):
        household_id = next(iter(scope.household_ids))
        village_id = db.get(Household, household_id).village_id
    else:
        household_id = body.household_id
        village_id = body.village_id
        if household_id:
            hh = db.get(Household, household_id)
            if hh is None:
                raise not_found("Household")
            village_id = hh.village_id
        if body.collection_point_id and not village_id:
            cp = db.get(CollectionPoint, body.collection_point_id)
            village_id = cp.village_id if cp else None
        if village_id is None:
            raise bad_request("VILLAGE_REQUIRED", "Provide a village, household or collection point")
        scope.ensure_village(village_id, "Village")
    c = Complaint(
        village_id=village_id,
        household_id=household_id,
        raised_by=principal.id,
        category=body.category,
        description=body.description,
        collection_point_id=body.collection_point_id,
        pickup_request_id=body.pickup_request_id,
        media_id=body.media_id,
    )
    db.add(c)
    db.flush()
    notify(db, village_admins(db, village_id), type="complaint_created", title=f"New complaint: {body.category.replace('_', ' ')}",
           body=body.description[:140], severity=Severity.WARNING if body.category == "missed_pickup" else Severity.INFO,
           entity_type="complaint", entity_id=c.id, link="/complaints")
    audit(db, principal, "complaint.created", "complaint", c.id)
    db.commit()
    db.refresh(c)
    return _out(c)


@router.patch("/{complaint_id}", response_model=ComplaintOut)
def update_complaint(complaint_id: uuid.UUID, body: ComplaintPatch, db: DB, principal: CurrentUser):
    c = _visible(db, complaint_id, principal)
    scope = principal.scope
    if not scope.has(RoleKey.GP_ADMIN):
        if not (RoleKey.COLLECTOR in scope.roles and c.assigned_to == principal.id):
            raise forbidden()
    if body.version != c.version:
        raise conflict("VERSION_CONFLICT", "This complaint was changed by someone else. Reload and try again.")
    target = body.status or (ComplaintStatus.ASSIGNED if body.assigned_to else c.status)
    if target != c.status or target == ComplaintStatus.ASSIGNED:
        if target not in TRANSITIONS[c.status]:
            raise bad_request("INVALID_TRANSITION", f"Cannot move from {c.status} to {target}")
    if target == ComplaintStatus.ASSIGNED:
        if not body.assigned_to:
            raise bad_request("ASSIGNEE_REQUIRED", "Choose who handles this complaint")
        c.assigned_to = body.assigned_to
        notify(db, [body.assigned_to], type="complaint_assigned", title="Complaint assigned to you",
               body=c.description[:140], entity_type="complaint", entity_id=c.id, link="/complaints")
    if target in (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED):
        if not (body.resolution_note or c.resolution_note):
            raise bad_request("RESOLUTION_REQUIRED", "Add a resolution note")
        c.resolved_at = c.resolved_at or utcnow()
    if body.resolution_note:
        c.resolution_note = body.resolution_note
    before = {"status": c.status}
    c.status = target
    audit(db, principal, "complaint.updated", "complaint", c.id, before, body.model_dump(mode="json"))
    db.commit()
    db.refresh(c)
    return _out(c)
