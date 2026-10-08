import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import RoleKey

PHONE_PATTERN = r"^\+?[0-9]{10,15}$"


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=254, description="Email or phone number")
    password: str = Field(min_length=1, max_length=256)


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str | None = None
    organization_type: str | None = None
    role: str
    village_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    phone: str | None
    full_name: str
    preferred_language: str
    roles: list[str]
    memberships: list[MembershipOut]
    household_id: uuid.UUID | None = None
    village_ids: list[uuid.UUID] = []
    facility_ids: list[uuid.UUID] = []
    read_only: bool = False
    demo_mode: bool = False


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: MeOut


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    password: str = Field(min_length=10, max_length=128)
    village_id: uuid.UUID
    address_line: str | None = Field(default=None, max_length=255)
    consent: bool = Field(description="Consent to store the minimum data needed for pickups")

    @field_validator("consent")
    @classmethod
    def _must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to register")
        return v


class InvitationIn(BaseModel):
    email: EmailStr
    role: RoleKey
    organization_id: uuid.UUID
    village_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    organization_id: uuid.UUID
    village_id: uuid.UUID | None
    facility_id: uuid.UUID | None
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    # Only returned once, at creation (no email service is required to run the platform).
    token: str | None = None
    invite_path: str | None = None


class InvitationPublic(BaseModel):
    email: str
    role: str
    organization_name: str
    expires_at: datetime


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)
