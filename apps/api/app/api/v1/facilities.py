import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request, not_found
from app.models import Facility, FacilityIntake, MaterialBatch, MaterialCategory, Route, Vehicle, Village
from app.models.enums import BatchStatus, DataOrigin, FacilityType, RoleKey
from app.schemas.common import Kg, KgIn, Page
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.scope import AccessScope
from app.security.tokens import utcnow
from app.services import inventory
from app.services.audit import audit
from app.services.listing import PageParams, paginate

router = APIRouter()
READERS = (RoleKey.MRF_OPERATOR, RoleKey.GP_ADMIN, RoleKey.EVALUATOR)


class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    facility_type: FacilityType
    lat: float | None
    lng: float | None
    address: str | None
    capacity_kg_per_day: Kg | None
    storage_locations: list
    active: bool
    is_sample: bool
    stock_kg: Kg = Decimal("0")
    active_batches: int = 0
    village_names: list[str] = []


class FacilityIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    code: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    facility_type: FacilityType = FacilityType.MRF
    organization_id: uuid.UUID | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    address: str | None = Field(None, max_length=300)
    capacity_kg_per_day: KgIn | None = None
    storage_locations: list[str] = Field(default_factory=list, max_length=50)


class IntakeIn(BaseModel):
    gross_kg: KgIn
    tare_kg: KgIn
    received_at: AwareDatetime | None = None
    origin_village_id: uuid.UUID | None = None
    route_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    transporter_name: str | None = Field(None, max_length=160)
    declared_collected_kg: KgIn | None = None
    storage_location: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)


class IntakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    facility_id: uuid.UUID
    origin_village_id: uuid.UUID | None
    route_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    transporter_name: str | None
    received_at: datetime
    gross_kg: Kg
    tare_kg: Kg
    net_kg: Kg
    declared_collected_kg: Kg | None
    operator_id: uuid.UUID
    batch_id: uuid.UUID | None
    notes: str | None
    data_origin: DataOrigin
    village_name: str | None = None
    batch_code: str | None = None


class CategoryStock(BaseModel):
    category_code: str
    category_label: str
    is_mlp: bool
    stock_kg: Kg
    batches: int


class MassBalanceOut(BaseModel):
    facility_id: uuid.UUID
    start: datetime
    end: datetime
    opening_kg: Kg
    intake_kg: Kg
    transferred_out_kg: Kg
    returned_kg: Kg
    loss_kg: Kg
    disposed_kg: Kg
    adjustment_kg: Kg
    unexplained_processing_difference_kg: Kg
    closing_kg: Kg
    tolerance_kg: Kg
    flagged: bool
    declared_collected_kg: Kg | None
    collection_to_intake_gap_kg: Kg | None
    ledger_consistent: bool
    movements_by_type: dict[str, Kg]


def visible_facility_ids(db: Session, scope: AccessScope) -> set[uuid.UUID] | None:
    """None = all facilities. GP admins see the facility their villages deliver to (read-only)."""
    if scope.sees_all:
        return None
    ids = set(scope.facility_ids)
    if scope.village_ids:
        ids |= {f for f in db.scalars(select(Village.facility_id).where(Village.id.in_(scope.village_ids))) if f}
    return ids


def get_visible_facility(db: Session, facility_id: uuid.UUID, principal: Principal) -> Facility:
    visible = visible_facility_ids(db, principal.scope)
    f = db.get(Facility, facility_id)
    if f is None or f.deleted_at is not None or (visible is not None and f.id not in visible):
        raise not_found("Facility")
    return f


def operable_facility(db: Session, facility_id: uuid.UUID, principal: Principal) -> Facility:
    """Write access: MRF operators of that facility (and super admins)."""
    f = db.get(Facility, facility_id)
    if f is None or f.deleted_at is not None:
        raise not_found("Facility")
    principal.scope.ensure_facility(f.id, "Facility")
    return f


def _serialize(db: Session, facilities: list[Facility]) -> list[FacilityOut]:
    ids = [f.id for f in facilities]
    stock = {r[0]: (r[1], r[2]) for r in db.execute(
        select(MaterialBatch.facility_id, func.sum(MaterialBatch.current_weight_kg), func.count())
        .where(MaterialBatch.facility_id.in_(ids), MaterialBatch.status == BatchStatus.ACTIVE)
        .group_by(MaterialBatch.facility_id))}
    villages: dict[uuid.UUID, list[str]] = {}
    for fid, name in db.execute(select(Village.facility_id, Village.name).where(Village.facility_id.in_(ids)).order_by(Village.name)):
        villages.setdefault(fid, []).append(name)
    out = []
    for f in facilities:
        o = FacilityOut.model_validate(f)
        kg, n = stock.get(f.id, (Decimal("0"), 0))
        o.stock_kg, o.active_batches, o.village_names = kg or Decimal("0"), n, villages.get(f.id, [])
        out.append(o)
    return out


@router.get("", response_model=list[FacilityOut])
def list_facilities(db: DB, principal: Principal = Depends(require(*READERS))):
    stmt = select(Facility).where(Facility.deleted_at.is_(None)).order_by(Facility.name)
    visible = visible_facility_ids(db, principal.scope)
    if visible is not None:
        stmt = stmt.where(Facility.id.in_(visible or {uuid.UUID(int=0)}))
    return _serialize(db, list(db.scalars(stmt)))


@router.post("", response_model=FacilityOut, status_code=201)
def create_facility(body: FacilityIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    org_id = body.organization_id
    if not principal.scope.is_super:
        if len(principal.scope.org_ids) != 1:
            raise bad_request("ORGANIZATION_REQUIRED", "Choose the operating organisation")
        org_id = next(iter(principal.scope.org_ids))
    if org_id is None:
        raise bad_request("ORGANIZATION_REQUIRED", "Choose the operating organisation")
    if db.scalar(select(Facility.id).where(Facility.code == body.code)):
        raise bad_request("CODE_TAKEN", f"Facility code {body.code} is already used")
    f = Facility(organization_id=org_id, **body.model_dump(exclude={"organization_id"}))
    db.add(f)
    db.flush()
    audit(db, principal, "facility.created", "facility", f.id)
    db.commit()
    db.refresh(f)
    return _serialize(db, [f])[0]


@router.get("/{facility_id}", response_model=FacilityOut)
def get_facility(facility_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*READERS))):
    return _serialize(db, [get_visible_facility(db, facility_id, principal)])[0]


@router.get("/{facility_id}/stock", response_model=list[CategoryStock], summary="Current stock by material category")
def stock(facility_id: uuid.UUID, db: DB, principal: Principal = Depends(require(*READERS))):
    f = get_visible_facility(db, facility_id, principal)
    rows = db.execute(
        select(MaterialCategory.code, MaterialCategory.label, MaterialCategory.is_mlp,
               func.coalesce(func.sum(MaterialBatch.current_weight_kg), 0), func.count(MaterialBatch.id))
        .join(MaterialBatch, (MaterialBatch.category_id == MaterialCategory.id) & (MaterialBatch.facility_id == f.id)
              & (MaterialBatch.status == BatchStatus.ACTIVE), isouter=True)
        .group_by(MaterialCategory.id).order_by(MaterialCategory.sort_order)
    ).all()
    return [CategoryStock(category_code=c, category_label=lbl, is_mlp=mlp, stock_kg=kg, batches=n) for c, lbl, mlp, kg, n in rows]


@router.get("/{facility_id}/intakes", response_model=Page[IntakeOut])
def list_intakes(facility_id: uuid.UUID, db: DB, params: PageParams = Depends(),
                 principal: Principal = Depends(require(*READERS))):
    f = get_visible_facility(db, facility_id, principal)
    page = paginate(db, select(FacilityIntake).where(FacilityIntake.facility_id == f.id),
                    params, {"received": FacilityIntake.received_at, "net": FacilityIntake.net_kg}, "-received")
    items = page["items"]
    names = dict(db.execute(select(Village.id, Village.name).where(Village.id.in_({i.origin_village_id for i in items if i.origin_village_id}))).all()) if items else {}
    codes = dict(db.execute(select(MaterialBatch.id, MaterialBatch.code).where(MaterialBatch.id.in_({i.batch_id for i in items if i.batch_id}))).all()) if items else {}
    out = []
    for i in items:
        o = IntakeOut.model_validate(i)
        o.village_name, o.batch_code = names.get(i.origin_village_id), codes.get(i.batch_id)
        out.append(o)
    page["items"] = out
    return page


@router.post("/{facility_id}/intakes", response_model=IntakeOut, status_code=201,
             summary="Weigh in a delivery: creates a mixed/unsorted batch and an INTAKE ledger movement")
def create_intake(facility_id: uuid.UUID, body: IntakeIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    f = operable_facility(db, facility_id, principal)
    if body.origin_village_id:
        v = db.get(Village, body.origin_village_id)
        if v is None or v.facility_id != f.id:
            raise bad_request("VILLAGE_NOT_SERVED", "That village does not deliver to this facility")
    if body.route_id:
        route = db.get(Route, body.route_id)
        if route is None or route.facility_id not in (None, f.id):
            raise bad_request("ROUTE_MISMATCH", "That route does not unload at this facility")
    if body.vehicle_id and db.get(Vehicle, body.vehicle_id) is None:
        raise not_found("Vehicle")
    received = body.received_at or utcnow()
    if received > datetime.now(UTC) + timedelta(minutes=5):
        raise bad_request("FUTURE_TIMESTAMP", "Receipt time is in the future")
    intake = inventory.record_intake(
        db, f, principal.id, gross_kg=body.gross_kg, tare_kg=body.tare_kg, received_at=received,
        origin_village_id=body.origin_village_id, route_id=body.route_id, vehicle_id=body.vehicle_id,
        transporter_name=body.transporter_name, declared_collected_kg=body.declared_collected_kg,
        storage_location=body.storage_location, notes=body.notes,
        origin=DataOrigin.DEMO_SEED if f.is_sample else DataOrigin.LIVE)
    audit(db, principal, "intake.recorded", "facility_intake", intake.id, after={"net_kg": str(intake.net_kg)})
    db.commit()
    db.refresh(intake)
    out = IntakeOut.model_validate(intake)
    out.batch_code = db.get(MaterialBatch, intake.batch_id).code
    return out


@router.get("/{facility_id}/mass-balance", response_model=MassBalanceOut)
def get_mass_balance(facility_id: uuid.UUID, db: DB, start: datetime | None = None, end: datetime | None = None,
                     principal: Principal = Depends(require(*READERS))):
    f = get_visible_facility(db, facility_id, principal)
    end = end or utcnow() + timedelta(seconds=1)
    start = start or end - timedelta(days=30)
    if start >= end:
        raise bad_request("INVALID_PERIOD", "Start must be before end")
    return inventory.mass_balance(db, f.id, start, end)


@router.get("/{facility_id}/villages", summary="Villages that deliver to this facility")
def facility_villages(facility_id: uuid.UUID, db: DB, principal: CurrentUser):
    f = get_visible_facility(db, facility_id, principal)
    return [{"id": v.id, "name": v.name, "code": v.code} for v in db.scalars(select(Village).where(Village.facility_id == f.id).order_by(Village.name))]
