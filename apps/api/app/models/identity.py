import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import LOCATION_SQL, Base, Geography, SoftDelete, Timestamps, UUIDPk, enum_col, flag
from app.models.enums import OrgType


class Organization(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40), unique=True)
    org_type: Mapped[OrgType] = enum_col(OrgType)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    address: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    is_sample: Mapped[bool] = flag(False)
    active: Mapped[bool] = flag(True)


class Village(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "villages"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    district: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None]
    lng: Mapped[float | None]
    location: Mapped[Any] = mapped_column(Geography(), Computed(LOCATION_SQL, persisted=True), nullable=True, deferred=True)
    boundary_geojson: Mapped[dict[str, Any] | None]
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"), index=True)
    population: Mapped[int | None]
    is_sample: Mapped[bool] = flag(False)


class Role(Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)


class User(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = flag(True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    notification_prefs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    last_login_at: Mapped[datetime | None]
    failed_logins: Mapped[int] = mapped_column(default=0, server_default="0")
    is_sample: Mapped[bool] = flag(False)

    memberships: Mapped[list["UserMembership"]] = relationship(back_populates="user", lazy="selectin")


class UserMembership(UUIDPk, Base):
    __tablename__ = "user_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "role_key", name="uq_membership_user_org_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key", ondelete="RESTRICT"))
    # Optional narrowing within the organisation
    village_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User] = relationship(back_populates="memberships")


class Invitation(UUIDPk, Base):
    __tablename__ = "invitations"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(254))
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key", ondelete="RESTRICT"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    village_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("villages.id", ondelete="RESTRICT"))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id", ondelete="RESTRICT"))
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RefreshToken(UUIDPk, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None] = mapped_column(String(40))
    replaced_by_id: Mapped[uuid.UUID | None]
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class AuditLog(UUIDPk, Base):
    """Append-only (enforced by a DB trigger)."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"),)

    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    actor_label: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
