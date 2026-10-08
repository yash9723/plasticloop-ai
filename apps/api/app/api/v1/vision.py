import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.adapters import active_adapter_info, get_adapter
from app.ai.evaluate import REPORT_PATH
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.ratelimit import limiter
from app.models import Facility, MaterialBatch, User, VisionPrediction, VisionReview
from app.models.enums import VISION_LABELS, DataOrigin, MediaPurpose, RoleKey
from app.schemas.common import Page
from app.security.deps import DB, Principal, require
from app.services import system_settings
from app.services.audit import audit
from app.services.listing import PageParams, paginate
from app.services.media import file_path, signed_url, store_upload

router = APIRouter()
USERS = (RoleKey.MRF_OPERATOR, RoleKey.GP_ADMIN, RoleKey.COLLECTOR)
FinalLabel = Literal["rigid_plastic", "flexible_plastic", "suspected_multilayer_packaging", "paper_cardboard", "metal", "other_unknown"]
# Suggested material category for each label. MLP stays "suspected" until a batch-level evidence review.
CATEGORY_HINT = {"rigid_plastic": "rigid_plastic", "flexible_plastic": "flexible_plastic", "suspected_multilayer_packaging": "suspected_mlp",
                 "paper_cardboard": "paper_cardboard", "metal": "metal", "other_unknown": None}


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    final_label: str
    agrees_with_model: bool | None
    notes: str | None
    created_at: datetime
    reviewer_name: str | None = None


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_id: uuid.UUID
    facility_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    adapter: str
    model_name: str
    model_version: str
    candidates: list[dict[str, Any]]
    top_label: str | None
    top_score: float | None
    threshold: float
    low_confidence: bool
    inference_ms: float | None
    data_origin: DataOrigin
    created_at: datetime
    image_url: str | None = None
    category_hint: str | None = None
    review: ReviewOut | None = None


class ReviewIn(BaseModel):
    final_label: FinalLabel
    notes: str | None = Field(None, max_length=500)


def _serialize(db: Session, preds: list[VisionPrediction]) -> list[PredictionOut]:
    reviews = {r.prediction_id: r for r in db.scalars(select(VisionReview).where(VisionReview.prediction_id.in_([p.id for p in preds])))} if preds else {}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_({r.reviewer_id for r in reviews.values()}))).all()) if reviews else {}
    out = []
    for p in preds:
        o = PredictionOut.model_validate(p)
        o.image_url = signed_url(p.media_id)
        o.category_hint = CATEGORY_HINT.get(p.top_label) if p.top_label and not p.low_confidence else None
        r = reviews.get(p.id)
        if r:
            o.review = ReviewOut.model_validate(r)
            o.review.reviewer_name = names.get(r.reviewer_id)
        out.append(o)
    return out


def _visible_clause(principal: Principal):
    scope = principal.scope
    if scope.sees_all:
        return None
    if scope.facility_ids:
        return VisionPrediction.facility_id.in_(scope.facility_ids) | (VisionPrediction.requested_by == principal.id)
    return VisionPrediction.requested_by == principal.id


def _get(db: Session, prediction_id: uuid.UUID, principal: Principal) -> VisionPrediction:
    stmt = select(VisionPrediction).where(VisionPrediction.id == prediction_id)
    clause = _visible_clause(principal)
    if clause is not None:
        stmt = stmt.where(clause)
    p = db.scalar(stmt)
    if p is None:
        raise not_found("Prediction")
    return p


@router.get("/status", summary="Which classifier is active, and any measured evaluation")
def status(principal: Principal = Depends(require(*USERS, RoleKey.EVALUATOR))):
    report = None
    if REPORT_PATH.exists():
        data = json.loads(REPORT_PATH.read_text())
        report = {k: data.get(k) for k in ("generated_at", "samples", "accuracy", "macro_f1", "per_class", "confusion_columns", "confusion", "labels")}
        report["adapter_name"] = data.get("adapter", {}).get("name")
    return {"adapter": active_adapter_info(), "evaluation": report,
            "evaluation_notice": None if report else "No evaluation has been run on a labelled test set; no accuracy is claimed."}


@router.post("/classify", response_model=PredictionOut, status_code=201, summary="Get a SUGGESTED label for a packaging photo")
def classify(db: DB, principal: Principal = Depends(require(*USERS)), file: UploadFile = File(...),
             facility_id: uuid.UUID | None = Form(None), batch_id: uuid.UUID | None = Form(None)):
    limiter.check(f"vision:{principal.id}", 60, 600)
    if batch_id:
        batch = db.get(MaterialBatch, batch_id)
        if batch is None:
            raise not_found("Batch")
        facility_id = batch.facility_id
    if facility_id:
        if db.get(Facility, facility_id) is None:
            raise not_found("Facility")
        principal.scope.ensure_facility(facility_id, "Facility")
    elif len(principal.scope.facility_ids) == 1:
        facility_id = next(iter(principal.scope.facility_ids))
    media = store_upload(db, file, MediaPurpose.VISION_SAMPLE, principal.id)
    adapter = get_adapter()
    try:
        pred = adapter.predict(file_path(media).read_bytes())
    except ValueError as exc:
        raise bad_request("UNREADABLE_IMAGE", "Could not read that image") from exc
    threshold = float(system_settings.get_value(db, "vision_confidence_threshold"))
    top = pred.top
    p = VisionPrediction(media_id=media.id, requested_by=principal.id, facility_id=facility_id, batch_id=batch_id, adapter=adapter.kind,
                         model_name=adapter.name, model_version=adapter.version, candidates=pred.candidates,
                         top_label=top["label"] if top else None, top_score=top["score"] if top else None, threshold=threshold,
                         low_confidence=top is None or top["score"] < threshold, inference_ms=round(pred.inference_ms, 2),
                         meta=pred.meta)
    db.add(p)
    db.flush()
    audit(db, principal, "vision.classified", "vision_prediction", p.id, after={"adapter": adapter.kind, "top": p.top_label})
    db.commit()
    db.refresh(p)
    return _serialize(db, [p])[0]


@router.get("/predictions", response_model=Page[PredictionOut], summary="Review queue (low-confidence first)")
def list_predictions(db: DB, params: PageParams = Depends(), reviewed: bool | None = None, low_confidence: bool | None = None,
                     principal: Principal = Depends(require(*USERS, RoleKey.EVALUATOR))):
    stmt = select(VisionPrediction)
    clause = _visible_clause(principal)
    if clause is not None:
        stmt = stmt.where(clause)
    reviewed_ids = select(VisionReview.prediction_id)
    if reviewed is True:
        stmt = stmt.where(VisionPrediction.id.in_(reviewed_ids))
    elif reviewed is False:
        stmt = stmt.where(VisionPrediction.id.not_in(reviewed_ids))
    if low_confidence is not None:
        stmt = stmt.where(VisionPrediction.low_confidence.is_(low_confidence))
    page = paginate(db, stmt, params, {"created": VisionPrediction.created_at, "score": VisionPrediction.top_score}, "-created")
    page["items"] = _serialize(db, page["items"])
    return page


@router.post("/predictions/{prediction_id}/review", response_model=PredictionOut, summary="Record the human-verified label")
def review(prediction_id: uuid.UUID, body: ReviewIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR, RoleKey.GP_ADMIN))):
    p = _get(db, prediction_id, principal)
    if principal.scope.is_evaluator and not principal.scope.is_super:
        raise forbidden("Evaluator accounts are read-only")
    if db.scalar(select(VisionReview.id).where(VisionReview.prediction_id == p.id)):
        raise conflict("ALREADY_REVIEWED", "This image already has a reviewed label")
    db.add(VisionReview(prediction_id=p.id, reviewer_id=principal.id, final_label=body.final_label,
                        agrees_with_model=(body.final_label == p.top_label) if p.top_label else None, notes=body.notes))
    audit(db, principal, "vision.reviewed", "vision_prediction", p.id, after={"final": body.final_label, "model": p.top_label})
    db.commit()
    return _serialize(db, [p])[0]


@router.get("/agreement", summary="How often reviewers agreed with suggestions (reviewed samples only; not an accuracy figure)")
def agreement(db: DB, principal: Principal = Depends(require(*USERS, RoleKey.EVALUATOR))):
    rows = db.execute(
        select(VisionPrediction.adapter, VisionReview.agrees_with_model, func.count())
        .join(VisionReview, VisionReview.prediction_id == VisionPrediction.id)
        .group_by(VisionPrediction.adapter, VisionReview.agrees_with_model)
    ).all()
    out: dict[str, dict[str, int]] = {}
    for adapter, agrees, n in rows:
        bucket = out.setdefault(str(adapter), {"reviewed": 0, "agreed": 0, "no_suggestion": 0})
        bucket["reviewed"] += n
        if agrees is True:
            bucket["agreed"] += n
        elif agrees is None:
            bucket["no_suggestion"] += n
    return {"by_adapter": out, "notice": "Agreement on reviewed images is not model accuracy: reviewers saw the suggestion, and samples are not a random test set."}


@router.get("/labels")
def labels(_: Principal = Depends(require(*USERS, RoleKey.EVALUATOR))):
    return [{"label": label, "category_hint": CATEGORY_HINT[label]} for label in VISION_LABELS]
