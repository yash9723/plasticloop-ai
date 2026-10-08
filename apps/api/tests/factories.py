"""Minimal data builders for tests (flush only; the test transaction is rolled back afterwards)."""

import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    CollectionPoint,
    Facility,
    Household,
    Organization,
    ProcessingPartner,
    User,
    UserMembership,
    Village,
    WasteStream,
)
from app.models.enums import FacilityType, OrgType
from app.security.passwords import hash_password
from app.security.tokens import create_access_token

PASSWORD = "Testpass123"
_PW_HASH = hash_password(PASSWORD)  # hash once: Argon2 is deliberately slow


def _code(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(2).upper()}"


def org(db: Session, org_type: OrgType = OrgType.GRAM_PANCHAYAT, name: str | None = None) -> Organization:
    o = Organization(name=name or f"Test {org_type} {_code('')}", code=_code("ORG-"), org_type=org_type)
    db.add(o)
    db.flush()
    return o


def facility(db: Session, operator_org: Organization) -> Facility:
    f = Facility(organization_id=operator_org.id, name=f"MRF {_code('')}", code=_code("F"), facility_type=FacilityType.MRF,
                 lat=17.95, lng=78.95)
    db.add(f)
    db.flush()
    return f


def village(db: Session, gp: Organization, facility_obj: Facility | None = None, lat: float = 17.9, lng: float = 78.9) -> Village:
    v = Village(organization_id=gp.id, name=f"Village {_code('')}", code=_code("V"), lat=lat, lng=lng,
                facility_id=facility_obj.id if facility_obj else None)
    db.add(v)
    db.flush()
    return v


def user(db: Session, role: str, organization: Organization | None = None, village_obj: Village | None = None,
         facility_obj: Facility | None = None, email: str | None = None) -> User:
    u = User(email=email or f"{role}-{uuid.uuid4().hex[:8]}@test.example", full_name=f"Test {role.title()}", password_hash=_PW_HASH)
    db.add(u)
    db.flush()
    if organization is not None:
        db.add(UserMembership(user_id=u.id, organization_id=organization.id, role_key=role,
                              village_id=village_obj.id if village_obj else None,
                              facility_id=facility_obj.id if facility_obj else None))
        db.flush()
    db.refresh(u)
    return u


def household(db: Session, village_obj: Village, owner: User | None = None) -> Household:
    h = Household(village_id=village_obj.id, user_id=owner.id if owner else None, household_code=_code("HH-"),
                  head_name="Test Household", phone="9876543210", address_line="Ward 1", lat=17.901, lng=78.901)
    db.add(h)
    db.flush()
    return h


def stream(db: Session, code: str | None = None) -> WasteStream:
    s = WasteStream(code=code or f"s_{uuid.uuid4().hex[:6]}", label="Test stream")
    db.add(s)
    db.flush()
    return s


def point(db: Session, village_obj: Village, streams: list[WasteStream], collector: User | None = None,
          lat: float = 17.9, lng: float = 78.9, **kw) -> CollectionPoint:
    cp = CollectionPoint(code=_code("CP-"), qr_code=_code("PLT"), name="Test point", village_id=village_obj.id,
                         lat=lat, lng=lng, assigned_collector_id=collector.id if collector else None, streams=streams, **kw)
    db.add(cp)
    db.flush()
    return cp


def partner(db: Session, processor_org: Organization) -> ProcessingPartner:
    p = ProcessingPartner(organization_id=processor_org.id, display_name=processor_org.name,
                          supported_category_codes=["suspected_mlp", "flexible_plastic"], is_sample=True)
    db.add(p)
    db.flush()
    return p


def headers(u: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(u.id)[0]}"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def kg(value: str) -> Decimal:
    return Decimal(value)
