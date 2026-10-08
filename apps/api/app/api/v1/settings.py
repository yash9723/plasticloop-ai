import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import bad_request, conflict, not_found
from app.models import MaterialCategory, SystemSetting, WasteStream
from app.schemas.collection import WasteStreamIn, WasteStreamOut, WasteStreamPatch
from app.schemas.common import ORM
from app.security.deps import DB, CurrentUser, Principal, require
from app.services import system_settings
from app.services.audit import audit, snapshot

router = APIRouter()


class MaterialCategoryOut(ORM):
    id: uuid.UUID
    code: str
    label: str
    labels: dict[str, Any]
    description: str | None
    is_mlp: bool
    is_unsorted: bool
    recoverable: bool
    requires_evidence_for_verification: bool
    sort_order: int


class SystemSettingItem(BaseModel):
    key: str
    value: Any
    default: Any
    description: str


@router.get("/waste-streams", response_model=list[WasteStreamOut])
def list_streams(db: DB, _: CurrentUser, include_inactive: bool = False):
    stmt = select(WasteStream).order_by(WasteStream.sort_order, WasteStream.label)
    if not include_inactive:
        stmt = stmt.where(WasteStream.active.is_(True))
    return db.scalars(stmt).all()


@router.post("/waste-streams", response_model=WasteStreamOut, status_code=201)
def create_stream(body: WasteStreamIn, db: DB, principal: Principal = Depends(require())):
    if db.scalar(select(WasteStream.id).where(WasteStream.code == body.code)):
        raise conflict("CODE_TAKEN", "Stream code already exists")
    stream = WasteStream(**body.model_dump(), is_demo_config=False)
    db.add(stream)
    db.flush()
    audit(db, principal, "waste_stream.created", "waste_stream", stream.id, after=body.model_dump())
    db.commit()
    db.refresh(stream)
    return stream


@router.patch("/waste-streams/{stream_id}", response_model=WasteStreamOut)
def update_stream(stream_id: uuid.UUID, body: WasteStreamPatch, db: DB, principal: Principal = Depends(require())):
    stream = db.get(WasteStream, stream_id)
    if stream is None:
        raise not_found("Waste stream")
    data = body.model_dump(exclude_unset=True)
    before = snapshot(stream, *data.keys())
    for k, v in data.items():
        setattr(stream, k, v)
    audit(db, principal, "waste_stream.updated", "waste_stream", stream.id, before, data)
    db.commit()
    db.refresh(stream)
    return stream


@router.get("/material-categories", response_model=list[MaterialCategoryOut])
def list_categories(db: DB, _: CurrentUser):
    return db.scalars(select(MaterialCategory).order_by(MaterialCategory.sort_order)).all()


@router.get("/system", response_model=list[SystemSettingItem])
def get_system(db: DB, _: CurrentUser):
    values = system_settings.get_all(db)
    return [
        SystemSettingItem(key=k, value=values[k], default=spec[0], description=spec[1])
        for k, spec in system_settings.SETTINGS_SPEC.items()
    ]


@router.patch("/system", response_model=list[SystemSettingItem])
def update_system(body: dict[str, Any], db: DB, principal: Principal = Depends(require())):
    unknown = set(body) - set(system_settings.SETTINGS_SPEC)
    if unknown:
        raise bad_request("UNKNOWN_SETTING", f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in body.items():
        default = system_settings.SETTINGS_SPEC[key][0]
        if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
            raise bad_request("INVALID_SETTING", f"{key} must be a non-negative number")
        if isinstance(default, int) and not isinstance(default, bool):
            value = type(default)(value)
        row = db.get(SystemSetting, key)
        before = row.value if row else default
        if row is None:
            db.add(SystemSetting(key=key, value=value, description=system_settings.SETTINGS_SPEC[key][1], updated_by=principal.id))
        else:
            row.value = value
            row.updated_by = principal.id
        audit(db, principal, "system_setting.updated", "system_setting", key, {"value": before}, {"value": value})
    db.commit()
    return get_system(db, principal)
