import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import OrgType
from app.schemas.auth import PHONE_PATTERN
from app.schemas.common import ORM

CODE_PATTERN = r"^[A-Z0-9][A-Z0-9-]{1,39}$"


class OrganizationOut(ORM):
    id: uuid.UUID
    name: str
    code: str
    org_type: OrgType
    parent_id: uuid.UUID | None
    address: str | None
    contact_name: str | None
    contact_phone: str | None
    is_sample: bool
    active: bool
    created_at: datetime


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(pattern=CODE_PATTERN)
    org_type: OrgType
    parent_id: uuid.UUID | None = None
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    active: bool | None = None


class VillageOut(ORM):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    district: str | None
    state: str | None
    lat: float | None
    lng: float | None
    boundary_geojson: dict[str, Any] | None
    facility_id: uuid.UUID | None
    population: int | None
    is_sample: bool
    created_at: datetime


class VillageDetail(VillageOut):
    stats: dict[str, Any] = {}


class VillageIn(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(pattern=CODE_PATTERN, max_length=20)
    district: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    facility_id: uuid.UUID | None = None
    population: int | None = Field(default=None, ge=0)


class VillagePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    district: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    facility_id: uuid.UUID | None = None
    population: int | None = Field(default=None, ge=0)


class VillagePublic(ORM):
    id: uuid.UUID
    name: str
    district: str | None
    is_sample: bool


class UserOut(ORM):
    id: uuid.UUID
    email: str
    phone: str | None
    full_name: str
    is_active: bool
    preferred_language: str
    last_login_at: datetime | None
    created_at: datetime
    is_sample: bool
    role_keys: list[str]


class UserBrief(ORM):
    id: uuid.UUID
    full_name: str


class MePatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    preferred_language: Literal["en", "hi", "te"] | None = None
    notification_prefs: dict[str, Any] | None = None


class RoleOut(ORM):
    key: str
    label: str
    description: str | None
