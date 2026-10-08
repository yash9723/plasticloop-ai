import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.errors import conflict, not_found
from app.models import Organization
from app.models.enums import OrgType
from app.schemas.common import Page
from app.schemas.identity import OrganizationIn, OrganizationOut, OrganizationPatch
from app.security.deps import DB, CurrentUser, Principal, require
from app.services.audit import audit, snapshot
from app.services.listing import PageParams, paginate

router = APIRouter()


@router.get("", response_model=Page[OrganizationOut])
def list_organizations(
    db: DB, principal: CurrentUser, params: PageParams = Depends(), org_type: OrgType | None = None
):
    stmt = select(Organization).where(Organization.deleted_at.is_(None))
    scope = principal.scope
    if not scope.sees_all:
        # Everyone may see processor/buyer organisations (needed for transfers & marketplace); other tenants only their own.
        stmt = stmt.where(
            scope.org_clause(Organization.id) | Organization.org_type.in_([OrgType.PROCESSOR, OrgType.BUYER])
        )
    if org_type:
        stmt = stmt.where(Organization.org_type == org_type)
    return paginate(db, stmt, params, {"name": Organization.name, "created": Organization.created_at}, "name")


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(org_id: uuid.UUID, db: DB, principal: CurrentUser):
    org = db.get(Organization, org_id)
    if org is None or org.deleted_at is not None:
        raise not_found("Organization")
    if org.org_type not in (OrgType.PROCESSOR, OrgType.BUYER):
        principal.scope.ensure_org(org.id, "Organization")
    return org


@router.post("", response_model=OrganizationOut, status_code=201)
def create_organization(body: OrganizationIn, db: DB, principal: Principal = Depends(require())):
    if db.scalar(select(Organization.id).where(Organization.code == body.code)):
        raise conflict("CODE_TAKEN", "Organization code already exists")
    org = Organization(**body.model_dump())
    db.add(org)
    db.flush()
    audit(db, principal, "organization.created", "organization", org.id, after=body.model_dump())
    db.commit()
    db.refresh(org)
    return org


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(org_id: uuid.UUID, body: OrganizationPatch, db: DB, principal: Principal = Depends(require())):
    org = db.get(Organization, org_id)
    if org is None or org.deleted_at is not None:
        raise not_found("Organization")
    data = body.model_dump(exclude_unset=True)
    before = snapshot(org, *data.keys())
    for k, v in data.items():
        setattr(org, k, v)
    audit(db, principal, "organization.updated", "organization", org.id, before, data)
    db.commit()
    db.refresh(org)
    return org
