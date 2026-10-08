"""Tenant / village / facility scoping. Every data query filters through an AccessScope."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import Facility, Household, ProcessingPartner, User, Village
from app.models.enums import RoleKey

FIELD_ROLES = {RoleKey.GP_ADMIN, RoleKey.COLLECTOR, RoleKey.DRIVER}


@dataclass
class AccessScope:
    user_id: uuid.UUID
    roles: frozenset[str]
    is_super: bool = False
    is_evaluator: bool = False
    org_ids: set[uuid.UUID] = field(default_factory=set)
    village_ids: set[uuid.UUID] = field(default_factory=set)
    facility_ids: set[uuid.UUID] = field(default_factory=set)
    partner_ids: set[uuid.UUID] = field(default_factory=set)
    household_ids: set[uuid.UUID] = field(default_factory=set)
    household_village_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def sees_all(self) -> bool:
        """Super admins see everything; evaluators may read everything but write nothing."""
        return self.is_super or self.is_evaluator

    def has(self, *roles: str) -> bool:
        return self.is_super or bool(self.roles & set(roles))

    @staticmethod
    def _clause(column, allowed: set) -> ColumnElement[bool]:
        return column.in_(allowed) if allowed else false()

    def village_clause(self, column) -> ColumnElement[bool]:
        return true() if self.sees_all else self._clause(column, self.village_ids)

    def facility_clause(self, column) -> ColumnElement[bool]:
        return true() if self.sees_all else self._clause(column, self.facility_ids)

    def org_clause(self, column) -> ColumnElement[bool]:
        return true() if self.sees_all else self._clause(column, self.org_ids)

    def partner_clause(self, column) -> ColumnElement[bool]:
        return true() if self.sees_all else self._clause(column, self.partner_ids)

    def can_village(self, village_id: uuid.UUID | None) -> bool:
        return self.sees_all or village_id in self.village_ids

    def can_facility(self, facility_id: uuid.UUID | None) -> bool:
        return self.sees_all or facility_id in self.facility_ids

    # 404 (not 403) so other tenants' record IDs are not confirmed to exist.
    def ensure_village(self, village_id: uuid.UUID | None, entity: str = "Record") -> None:
        if not self.can_village(village_id):
            raise not_found(entity)

    def ensure_facility(self, facility_id: uuid.UUID | None, entity: str = "Record") -> None:
        if not self.can_facility(facility_id):
            raise not_found(entity)

    def ensure_org(self, org_id: uuid.UUID | None, entity: str = "Record") -> None:
        if not (self.sees_all or org_id in self.org_ids):
            raise not_found(entity)


def build_scope(db: Session, user: User) -> AccessScope:
    roles = frozenset(m.role_key for m in user.memberships)
    scope = AccessScope(
        user_id=user.id,
        roles=roles,
        is_super=RoleKey.SUPER_ADMIN in roles,
        is_evaluator=RoleKey.EVALUATOR in roles,
    )
    if scope.is_super:
        return scope

    for m in user.memberships:
        if m.role_key in FIELD_ROLES:
            scope.org_ids.add(m.organization_id)
            if m.village_id:
                scope.village_ids.add(m.village_id)
            else:
                scope.village_ids |= set(
                    db.scalars(
                        select(Village.id).where(Village.organization_id == m.organization_id, Village.deleted_at.is_(None))
                    )
                )
        elif m.role_key == RoleKey.MRF_OPERATOR:
            scope.org_ids.add(m.organization_id)
            facility_ids = (
                {m.facility_id}
                if m.facility_id
                else set(db.scalars(select(Facility.id).where(Facility.organization_id == m.organization_id)))
            )
            scope.facility_ids |= facility_ids
            if facility_ids:
                scope.village_ids |= set(db.scalars(select(Village.id).where(Village.facility_id.in_(facility_ids))))
        elif m.role_key == RoleKey.PROCESSOR:
            scope.org_ids.add(m.organization_id)
            scope.partner_ids |= set(
                db.scalars(select(ProcessingPartner.id).where(ProcessingPartner.organization_id == m.organization_id))
            )

    if RoleKey.HOUSEHOLD in roles:
        for hid, vid in db.execute(select(Household.id, Household.village_id).where(Household.user_id == user.id)):
            scope.household_ids.add(hid)
            scope.household_village_ids.add(vid)
    return scope
