"""Upload validation (size, magic bytes, image re-encode to strip EXIF/GPS) and HMAC-signed media URLs."""

import hashlib
import hmac
import io
import re
import time
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, bad_request
from app.models import MediaFile
from app.models.enums import DataOrigin, MediaPurpose
from app.security.tokens import utcnow

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
MAX_DIMENSION = 2048
PDF_PURPOSES = {
    MediaPurpose.TRANSFER_RECEIPT,
    MediaPurpose.OUTCOME_EVIDENCE,
    MediaPurpose.VERIFICATION_EVIDENCE,
    MediaPurpose.PROCESSOR_DOCUMENT,
    MediaPurpose.INVOICE,
}
_PIL_FORMATS = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def sniff(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf", "pdf"
    return None


def _safe_name(name: str | None) -> str | None:
    if not name:
        return None
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[-120:]


def _reencode_image(data: bytes, ext: str) -> tuple[bytes, int, int]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
            if ext == "jpg" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            params = {"quality": 85} if ext in ("jpg", "webp") else {"optimize": True}
            img.save(buf, format=_PIL_FORMATS[ext], **params)  # no exif= → metadata (incl. GPS) is dropped
            return buf.getvalue(), img.width, img.height
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise AppError(415, "INVALID_IMAGE", "The image could not be read") from exc


def store_bytes(
    db: Session,
    data: bytes,
    purpose: MediaPurpose,
    owner_id: uuid.UUID | None,
    filename: str | None = None,
    origin: DataOrigin = DataOrigin.LIVE,
) -> MediaFile:
    limit = settings.max_upload_mb * 1024 * 1024
    if not data:
        raise bad_request("EMPTY_FILE", "The file is empty")
    if len(data) > limit:
        raise AppError(413, "FILE_TOO_LARGE", f"Maximum upload size is {settings.max_upload_mb} MB")
    kind = sniff(data)
    allowed = "JPEG, PNG, WebP" + (", PDF" if purpose in PDF_PURPOSES else "")
    if kind is None or (kind[1] == "pdf" and purpose not in PDF_PURPOSES):
        raise AppError(415, "UNSUPPORTED_FILE_TYPE", f"Allowed file types: {allowed}")
    content_type, ext = kind
    width = height = None
    if content_type.startswith("image/"):
        data, width, height = _reencode_image(data, ext)

    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(MediaFile).where(MediaFile.owner_user_id == owner_id, MediaFile.sha256 == digest, MediaFile.purpose == purpose)
    )
    if existing is not None:  # idempotent retries from the offline queue
        return existing

    rel = f"{utcnow():%Y/%m}/{uuid.uuid4().hex}.{ext}"
    path = settings.upload_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    media = MediaFile(
        owner_user_id=owner_id,
        purpose=purpose,
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        storage_path=rel,
        original_filename=_safe_name(filename),
        width=width,
        height=height,
        data_origin=origin,
    )
    db.add(media)
    db.flush()
    return media


def store_upload(db: Session, upload: UploadFile, purpose: MediaPurpose, owner_id, origin=DataOrigin.LIVE) -> MediaFile:
    data = upload.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    return store_bytes(db, data, purpose, owner_id, upload.filename, origin)


def _signing_key() -> bytes:
    return hashlib.sha256(b"plasticloop-media-url:" + settings.jwt_secret.encode()).digest()


def _signature(media_id: uuid.UUID, exp: int) -> str:
    return hmac.new(_signing_key(), f"{media_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def signed_url(media_id: uuid.UUID | None) -> str | None:
    if media_id is None:
        return None
    exp = int(time.time()) + settings.media_url_ttl_s
    return f"/api/v1/media/{media_id}/content?exp={exp}&sig={_signature(media_id, exp)}"


def verify_signature(media_id: uuid.UUID, exp: int, sig: str) -> bool:
    return exp >= int(time.time()) and hmac.compare_digest(_signature(media_id, exp), sig)


def file_path(media: MediaFile) -> Path:
    root = settings.upload_dir.resolve()
    path = (root / media.storage_path).resolve()
    if root not in path.parents:
        raise AppError(404, "NOT_FOUND", "File not found")
    return path
