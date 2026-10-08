"""In-app notifications with per-user fan-out, dedupe/cooldown and muting. No paid third-party service needed."""

import uuid
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Facility, Notification, ProcessingPartner, User, UserMembership, Village
from app.models.enums import RoleKey, Severity
from app.security.tokens import utcnow


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID | None],
    *,
    type: str,
    title: str,
    body: str | None = None,
    severity: Severity = Severity.INFO,
    entity_type: str | None = None,
    entity_id=None,
    link: str | None = None,
    dedupe_key: str | None = None,
    cooldown_minutes: int = 60,
) -> int:
    now = utcnow()
    created = 0
    for uid in {u for u in user_ids if u}:
        if dedupe_key:
            recent = db.scalar(
                select(Notification.id)
                .where(
                    Notification.user_id == uid,
                    Notification.dedupe_key == dedupe_key,
                    Notification.created_at >= now - timedelta(minutes=cooldown_minutes),
                )
                .limit(1)
            )
            if recent:
                continue
        user = db.get(User, uid)
        if user is None or not user.is_active:
            continue
        muted = (user.notification_prefs or {}).get("muted_types", [])
        if type in muted and severity != Severity.CRITICAL:
            continue
        db.add(
            Notification(
                user_id=uid,
                type=type,
                severity=severity,
                title=title,
                body=body,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                link=link,
                dedupe_key=dedupe_key,
                created_at=now,
            )
        )
        created += 1
    db.flush()
    return created


def _active_members(db: Session, org_id, roles: Iterable[str], village_id=None, facility_id=None) -> list[uuid.UUID]:
    stmt = (
        select(UserMembership.user_id)
        .join(User, User.id == UserMembership.user_id)
        .where(UserMembership.organization_id == org_id, UserMembership.role_key.in_(list(roles)), User.is_active.is_(True))
    )
    if village_id:
        stmt = stmt.where(or_(UserMembership.village_id.is_(None), UserMembership.village_id == village_id))
    if facility_id:
        stmt = stmt.where(or_(UserMembership.facility_id.is_(None), UserMembership.facility_id == facility_id))
    return list(db.scalars(stmt))


def village_admins(db: Session, village_id) -> list[uuid.UUID]:
    village = db.get(Village, village_id)
    return _active_members(db, village.organization_id, [RoleKey.GP_ADMIN], village_id=village_id) if village else []


def facility_operators(db: Session, facility_id) -> list[uuid.UUID]:
    facility = db.get(Facility, facility_id)
    return _active_members(db, facility.organization_id, [RoleKey.MRF_OPERATOR], facility_id=facility_id) if facility else []


def partner_users(db: Session, partner_id) -> list[uuid.UUID]:
    partner = db.get(ProcessingPartner, partner_id)
    return _active_members(db, partner.organization_id, [RoleKey.PROCESSOR]) if partner else []


def super_admins(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(UserMembership.user_id)
            .join(User, User.id == UserMembership.user_id)
            .where(UserMembership.role_key == RoleKey.SUPER_ADMIN, User.is_active.is_(True))
        )
    )
