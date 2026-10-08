import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.core.errors import not_found
from app.models import Notification
from app.models.enums import Severity
from app.schemas.common import ORM, Page
from app.security.deps import DB, CurrentUser
from app.security.tokens import utcnow
from app.services.listing import PageParams, paginate

router = APIRouter()

NOTIFICATION_TYPES = [
    "bin_fill_alert", "missed_collection", "pickup_overdue", "device_disconnected", "device_low_battery",
    "invalid_sensor_reading", "sync_failed", "sync_conflict", "inventory_discrepancy", "batch_awaiting_processing",
    "transfer_rejected", "transfer_discrepancy", "complaint_assigned", "complaint_created", "route_capacity_warning",
    "pickup_request_created", "pickup_assigned", "collection_flagged", "transfer_incoming",
]


class NotificationOut(ORM):
    id: uuid.UUID
    type: str
    severity: Severity
    title: str
    body: str | None
    entity_type: str | None
    entity_id: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class Preferences(BaseModel):
    muted_types: list[str] = Field(default_factory=list)


@router.get("", response_model=Page[NotificationOut])
def list_notifications(db: DB, principal: CurrentUser, params: PageParams = Depends(), unread_only: bool = False,
                       severity: Severity | None = None):
    stmt = select(Notification).where(Notification.user_id == principal.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if severity:
        stmt = stmt.where(Notification.severity == severity)
    return paginate(db, stmt, params, {"created": Notification.created_at}, "-created")


@router.get("/unread-count")
def unread_count(db: DB, principal: CurrentUser):
    n = db.scalar(select(func.count()).where(Notification.user_id == principal.id, Notification.read_at.is_(None)))
    return {"unread": n or 0}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, db: DB, principal: CurrentUser):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != principal.id:
        raise not_found("Notification")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return n


@router.post("/read-all")
def mark_all_read(db: DB, principal: CurrentUser):
    res = db.execute(
        update(Notification).where(Notification.user_id == principal.id, Notification.read_at.is_(None)).values(read_at=utcnow())
    )
    db.commit()
    return {"updated": res.rowcount}


@router.get("/preferences", response_model=Preferences)
def get_preferences(principal: CurrentUser):
    return Preferences(muted_types=(principal.user.notification_prefs or {}).get("muted_types", []))


@router.put("/preferences", response_model=Preferences)
def set_preferences(body: Preferences, db: DB, principal: CurrentUser):
    valid = [t for t in body.muted_types if t in NOTIFICATION_TYPES]
    principal.user.notification_prefs = {**(principal.user.notification_prefs or {}), "muted_types": valid}
    db.commit()
    return Preferences(muted_types=valid)


@router.get("/types")
def types(_: CurrentUser):
    return NOTIFICATION_TYPES
