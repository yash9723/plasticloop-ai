import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.errors import bad_request, conflict, not_found
from app.models import User, Vehicle
from app.models.enums import RoleKey, VehicleType
from app.schemas.common import Kg
from app.security.deps import DB, Principal, require
from app.services.audit import audit, snapshot

router = APIRouter()


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    registration_no: str
    name: str
    vehicle_type: VehicleType
    capacity_kg: Kg
    depot_name: str | None
    depot_lat: float
    depot_lng: float
    cost_per_km_paise: int
    driver_id: uuid.UUID | None
    driver_name: str | None = None
    active: bool
    is_sample: bool


class VehicleIn(BaseModel):
    registration_no: str = Field(min_length=4, max_length=20)
    name: str = Field(min_length=2, max_length=80)
    vehicle_type: VehicleType = VehicleType.AUTO_RICKSHAW
    capacity_kg: Decimal = Field(gt=0, le=20000)
    depot_name: str | None = Field(None, max_length=120)
    depot_lat: float = Field(ge=-90, le=90)
    depot_lng: float = Field(ge=-180, le=180)
    cost_per_km_paise: int = Field(0, ge=0, le=10_000_00)
    driver_id: uuid.UUID | None = None


class VehiclePatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=80)
    capacity_kg: Decimal | None = Field(None, gt=0, le=20000)
    depot_name: str | None = Field(None, max_length=120)
    depot_lat: float | None = Field(None, ge=-90, le=90)
    depot_lng: float | None = Field(None, ge=-180, le=180)
    cost_per_km_paise: int | None = Field(None, ge=0, le=10_000_00)
    driver_id: uuid.UUID | None = None
    clear_driver: bool = False
    active: bool | None = None


def _out(db, vehicles: list[Vehicle]) -> list[VehicleOut]:
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({v.driver_id for v in vehicles if v.driver_id}))).all())
    out = []
    for v in vehicles:
        o = VehicleOut.model_validate(v)
        o.driver_name = names.get(v.driver_id)
        out.append(o)
    return out


def _check_driver(db, driver_id: uuid.UUID, org_id: uuid.UUID) -> None:
    user = db.get(User, driver_id)
    if user is None or not any(m.role_key == RoleKey.DRIVER and m.organization_id == org_id for m in user.memberships):
        raise bad_request("NOT_A_DRIVER", "Choose a driver from the same organisation")


def get_vehicle(db, vehicle_id: uuid.UUID, principal: Principal) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if v is None or v.deleted_at is not None:
        raise not_found("Vehicle")
    principal.scope.ensure_org(v.organization_id, "Vehicle")
    return v


@router.get("", response_model=list[VehicleOut])
def list_vehicles(db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.DRIVER, RoleKey.EVALUATOR)),
                  active: bool | None = None):
    stmt = select(Vehicle).where(Vehicle.deleted_at.is_(None), principal.scope.org_clause(Vehicle.organization_id)).order_by(Vehicle.name)
    if active is not None:
        stmt = stmt.where(Vehicle.active.is_(active))
    return _out(db, list(db.scalars(stmt)))


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    orgs = principal.scope.org_ids
    if len(orgs) != 1:
        raise bad_request("ORGANIZATION_REQUIRED", "Vehicles belong to exactly one panchayat organisation")
    org_id = next(iter(orgs))
    reg = body.registration_no.strip().upper()
    if db.scalar(select(Vehicle.id).where(Vehicle.registration_no == reg)):
        raise conflict("REGISTRATION_EXISTS", f"Vehicle {reg} is already registered")
    if body.driver_id:
        _check_driver(db, body.driver_id, org_id)
    v = Vehicle(organization_id=org_id, **body.model_dump(exclude={"registration_no"}), registration_no=reg)
    db.add(v)
    db.flush()
    audit(db, principal, "vehicle.created", "vehicle", v.id)
    db.commit()
    db.refresh(v)
    return _out(db, [v])[0]


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: uuid.UUID, body: VehiclePatch, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    v = get_vehicle(db, vehicle_id, principal)
    before = snapshot(v, "capacity_kg", "driver_id", "active")
    data = body.model_dump(exclude_unset=True, exclude={"clear_driver"})
    if body.driver_id:
        _check_driver(db, body.driver_id, v.organization_id)
    for k, val in data.items():
        if val is not None:
            setattr(v, k, val)
    if body.clear_driver:
        v.driver_id = None
    audit(db, principal, "vehicle.updated", "vehicle", v.id, before=before, after=snapshot(v, "capacity_kg", "driver_id", "active"))
    db.commit()
    db.refresh(v)
    return _out(db, [v])[0]
