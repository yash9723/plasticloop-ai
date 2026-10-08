import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.errors import AppError, forbidden, not_found
from app.core.ratelimit import limiter
from app.models import MediaFile
from app.models.enums import MediaPurpose, RoleKey
from app.security.deps import DB, CurrentUser
from app.services.media import file_path, signed_url, store_upload, verify_signature

router = APIRouter()

HOUSEHOLD_PURPOSES = {MediaPurpose.COMPLAINT_PHOTO}


class MediaOut(BaseModel):
    id: uuid.UUID
    purpose: MediaPurpose
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    url: str
    created_at: datetime


def _out(m: MediaFile) -> MediaOut:
    return MediaOut(id=m.id, purpose=m.purpose, content_type=m.content_type, size_bytes=m.size_bytes,
                    width=m.width, height=m.height, url=signed_url(m.id), created_at=m.created_at)


@router.post("", response_model=MediaOut, status_code=201, summary="Upload a photo or document (≤ MAX_UPLOAD_MB)")
def upload(db: DB, principal: CurrentUser, file: UploadFile = File(...), purpose: MediaPurpose = Form(...)):
    scope = principal.scope
    if scope.is_evaluator and not scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    if scope.roles == {RoleKey.HOUSEHOLD} and purpose not in HOUSEHOLD_PURPOSES:
        raise forbidden("Households can only upload complaint photos")
    limiter.check(f"upload:{principal.id}", 120, 3600)
    media = store_upload(db, file, purpose, principal.id)
    db.commit()
    return _out(media)


@router.get("/{media_id}", response_model=MediaOut, summary="Metadata + a fresh short-lived URL")
def get_media(media_id: uuid.UUID, db: DB, principal: CurrentUser):
    m = db.get(MediaFile, media_id)
    if m is None:
        raise not_found("File")
    staff = principal.scope.sees_all or bool(principal.scope.roles - {RoleKey.HOUSEHOLD})
    if m.owner_user_id != principal.id and not staff:
        raise not_found("File")
    return _out(m)


@router.get("/{media_id}/content", summary="File bytes (requires a valid signed URL)", include_in_schema=True)
def media_content(media_id: uuid.UUID, exp: int, sig: str, db: DB):
    if not verify_signature(media_id, exp, sig):
        raise AppError(403, "INVALID_SIGNATURE", "This link has expired or is invalid")
    m = db.get(MediaFile, media_id)
    if m is None:
        raise not_found("File")
    path = file_path(m)
    if not path.exists():
        raise not_found("File")
    return FileResponse(
        path,
        media_type=m.content_type,
        headers={"Cache-Control": "private, max-age=600", "Content-Disposition": "inline"},
    )
