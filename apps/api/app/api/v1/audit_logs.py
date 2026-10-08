import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.models import AuditLog, UserMembership
from app.models.enums import RoleKey
from app.schemas.common import Page
from app.security.deps import DB, Principal, require
from app.services.listing import PageParams, paginate

router = APIRouter()


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_label: str | None
    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None


@router.get("", response_model=Page[AuditOut], summary="Append-only audit trail (read-only)")
def list_audit(db: DB, params: PageParams = Depends(), action: str | None = None, entity_type: str | None = None,
               entity_id: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
               principal: Principal = Depends(require(RoleKey.EVALUATOR, RoleKey.GP_ADMIN))):
    stmt = select(AuditLog)
    scope = principal.scope
    if not scope.sees_all:  # panchayat admins see actions by members of their own organisation
        members = select(UserMembership.user_id).where(UserMembership.organization_id.in_(scope.org_ids or {uuid.UUID(int=0)}))
        stmt = stmt.where(AuditLog.actor_user_id.in_(members))
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action.strip()[:80]))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.occurred_at <= date_to)
    return paginate(db, stmt, params, {"time": AuditLog.occurred_at, "action": AuditLog.action}, "-time")
