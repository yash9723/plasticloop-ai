"""Dashboard analytics. Every figure is a live aggregate of persisted records, broken down by data origin."""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import Date, case, cast, func, select

from app.models import (
    BatchMovement,
    CollectionEvent,
    Complaint,
    Device,
    Expense,
    MaterialBatch,
    MaterialCategory,
    PickupRequest,
    ProcessingOutcome,
    ProcessingTransfer,
    Sale,
    Village,
    WasteStream,
)
from app.models.enums import (
    ComplaintStatus,
    ConnectionStatus,
    EvidenceStatus,
    MovementType,
    OutcomeType,
    PickupStatus,
    ReviewStatus,
    TransferStatus,
    VerificationStatus,
)
from app.security.deps import DB, CurrentUser
from app.security.scope import AccessScope
from app.security.tokens import utcnow

router = APIRouter()

RECOVERED_OUTCOMES = (OutcomeType.RECYCLED_WITH_EVIDENCE, OutcomeType.RECOVERED_DOCUMENTED_PROCESS)
_NONE = {uuid.UUID(int=0)}


def date_range(date_from: datetime | None, date_to: datetime | None, days: int = 30) -> tuple[datetime, datetime]:
    end = date_to or utcnow()
    return (date_from or end - timedelta(days=days)), end


def event_scope(scope: AccessScope):
    if scope.sees_all or scope.village_ids:
        return scope.village_clause(CollectionEvent.village_id)
    return CollectionEvent.id.is_(None)  # households & processors get no village-wide totals


def facility_scope(scope: AccessScope, column):
    """Super/evaluator: all. MRF operators: their facilities. GP admins: facilities serving their villages."""
    if scope.sees_all:
        return column.isnot(None)
    served = select(Village.facility_id).where(Village.id.in_(scope.village_ids or _NONE))
    return column.in_(scope.facility_ids or _NONE) | column.in_(served)


@router.get("/public-impact", summary="Public, aggregate-only impact figures (no personal data)")
def public_impact(db: DB):
    from app.core.config import settings
    from app.models import CollectionPoint
    from app.models.enums import DataOrigin

    by_origin = {
        str(o): float(w) for o, w in db.execute(select(CollectionEvent.data_origin, func.sum(CollectionEvent.weight_kg)).group_by(CollectionEvent.data_origin))
    }
    total = sum(by_origin.values())
    synthetic = by_origin.get(DataOrigin.DEMO_SEED, 0.0) + by_origin.get(DataOrigin.SIMULATED, 0.0)
    mlp = db.scalar(
        select(func.coalesce(func.sum(BatchMovement.quantity_kg), 0))
        .join(MaterialBatch, MaterialBatch.id == BatchMovement.batch_id)
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(MaterialCategory.is_mlp.is_(True), BatchMovement.movement_type == MovementType.SORT_IN)
    )
    recovered = db.scalar(
        select(func.coalesce(func.sum(ProcessingOutcome.output_kg), 0)).where(
            ProcessingOutcome.outcome_type.in_(RECOVERED_OUTCOMES), ProcessingOutcome.evidence_status == EvidenceStatus.REVIEWED_ACCEPTED
        )
    )
    return {
        "villages": db.scalar(select(func.count()).where(Village.deleted_at.is_(None))),
        "collection_points": db.scalar(select(func.count()).where(CollectionPoint.deleted_at.is_(None))),
        "collected_kg": total,
        "suspected_mlp_received_kg": float(mlp or 0),
        "recovered_evidence_reviewed_kg": float(recovered or 0),
        "share_synthetic_percent": round(synthetic / total * 100, 1) if total else 0.0,
        "demo_mode": settings.demo_enabled,
    }


@router.get("/overview", summary="KPI cards + collection time series")
def overview(
    db: DB,
    principal: CurrentUser,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    village_id: uuid.UUID | None = None,
):
    scope = principal.scope
    start, end = date_range(date_from, date_to)
    ev = [event_scope(scope), CollectionEvent.collected_at >= start, CollectionEvent.collected_at <= end]
    if village_id:
        scope.ensure_village(village_id, "Village")
        ev.append(CollectionEvent.village_id == village_id)

    kg, n, collectors, flagged = db.execute(
        select(
            func.coalesce(func.sum(CollectionEvent.weight_kg), 0),
            func.count(CollectionEvent.id),
            func.count(func.distinct(CollectionEvent.collector_id)),
            func.coalesce(func.sum(case((CollectionEvent.review_status == ReviewStatus.FLAGGED, 1), else_=0)), 0),
        ).where(*ev)
    ).one()

    by_origin = {
        str(o): float(w)
        for o, w in db.execute(select(CollectionEvent.data_origin, func.sum(CollectionEvent.weight_kg)).where(*ev).group_by(CollectionEvent.data_origin))
    }
    by_stream = [
        {"stream_id": sid, "code": code, "label": label, "labels": labels, "color": color, "kg": float(w)}
        for sid, code, label, labels, color, w in db.execute(
            select(WasteStream.id, WasteStream.code, WasteStream.label, WasteStream.labels, WasteStream.color, func.sum(CollectionEvent.weight_kg))
            .join(CollectionEvent, CollectionEvent.waste_stream_id == WasteStream.id)
            .where(*ev)
            .group_by(WasteStream.id)
            .order_by(func.sum(CollectionEvent.weight_kg).desc())
        )
    ]
    day = cast(func.timezone("Asia/Kolkata", CollectionEvent.collected_at), Date)
    series = [
        {"date": d.isoformat(), "kg": float(w), "events": c}
        for d, w, c in db.execute(select(day, func.sum(CollectionEvent.weight_kg), func.count()).where(*ev).group_by(day).order_by(day))
    ]

    staff = scope.sees_all or bool(scope.village_ids)
    pending_pickups = db.scalar(
        select(func.count()).where(
            scope.village_clause(PickupRequest.village_id) if staff else PickupRequest.household_id.in_(scope.household_ids or _NONE),
            PickupRequest.status.in_([PickupStatus.SUBMITTED, PickupStatus.ASSIGNED, PickupStatus.IN_PROGRESS]),
        )
    )
    open_complaints = db.scalar(
        select(func.count()).where(
            scope.village_clause(Complaint.village_id) if staff else Complaint.raised_by == principal.id,
            Complaint.status.in_([ComplaintStatus.OPEN, ComplaintStatus.ASSIGNED, ComplaintStatus.UNDER_REVIEW]),
        )
    )
    devices = {
        str(s): c
        for s, c in db.execute(
            select(Device.connection_status, func.count())
            .where(scope.org_clause(Device.organization_id), Device.deleted_at.is_(None))
            .group_by(Device.connection_status)
        )
    }

    fac = facility_scope(scope, MaterialBatch.facility_id)
    mlp_received = db.scalar(
        select(func.coalesce(func.sum(BatchMovement.quantity_kg), 0))
        .join(MaterialBatch, MaterialBatch.id == BatchMovement.batch_id)
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(fac, MaterialCategory.is_mlp.is_(True), BatchMovement.movement_type == MovementType.SORT_IN,
               BatchMovement.occurred_at >= start, BatchMovement.occurred_at <= end)
    )
    mlp_verified = db.scalar(
        select(func.coalesce(func.sum(MaterialBatch.current_weight_kg), 0))
        .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
        .where(fac, MaterialCategory.is_mlp.is_(True), MaterialBatch.verification_status == VerificationStatus.VERIFIED_WITH_EVIDENCE)
    )

    tfac = facility_scope(scope, ProcessingTransfer.source_facility_id) | scope.partner_clause(ProcessingTransfer.partner_id)
    recovered = {
        str(s): float(w)
        for s, w in db.execute(
            select(ProcessingOutcome.evidence_status, func.sum(ProcessingOutcome.output_kg))
            .join(ProcessingTransfer, ProcessingTransfer.id == ProcessingOutcome.transfer_id)
            .where(tfac, ProcessingOutcome.outcome_type.in_(RECOVERED_OUTCOMES), ProcessingOutcome.process_date >= start.date())
            .group_by(ProcessingOutcome.evidence_status)
        )
    }
    pending_transfers = db.scalar(
        select(func.count()).where(tfac, ProcessingTransfer.status.in_([TransferStatus.ALLOCATED, TransferStatus.DISPATCHED, TransferStatus.RECEIVED]))
    )

    revenue = db.scalar(
        select(func.coalesce(func.sum(Sale.total_paise), 0)).where(
            facility_scope(scope, Sale.facility_id), Sale.sold_on >= start.date(), Sale.sold_on <= end.date()
        )
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_paise), 0)).where(
            scope.org_clause(Expense.organization_id), Expense.incurred_on >= start.date(), Expense.incurred_on <= end.date()
        )
    )

    return {
        "range": {"from": start, "to": end},
        "collected_kg": float(kg),
        "collections": n,
        "active_collectors": collectors,
        "flagged_collections": int(flagged),
        "collected_kg_by_origin": by_origin,
        "by_stream": by_stream,
        "series": series,
        "pending_pickups": pending_pickups,
        "open_complaints": open_complaints,
        "devices": {
            "total": sum(devices.values()),
            "online": devices.get(ConnectionStatus.ONLINE, 0),
            "stale": devices.get(ConnectionStatus.STALE, 0),
            "offline": devices.get(ConnectionStatus.OFFLINE, 0),
            "never_seen": devices.get(ConnectionStatus.NEVER_SEEN, 0),
        },
        "suspected_mlp_received_kg": float(mlp_received or 0),
        "verified_mlp_in_stock_kg": float(mlp_verified or 0),
        "recovered_kg": {
            "evidence_reviewed": recovered.get(EvidenceStatus.REVIEWED_ACCEPTED, 0.0),
            "evidence_submitted": recovered.get(EvidenceStatus.SUBMITTED, 0.0),
            "self_reported": recovered.get(EvidenceStatus.NONE, 0.0),
        },
        "pending_transfers": pending_transfers,
        "revenue_paise": int(revenue or 0),
        "expenses_paise": int(expenses or 0),
        "operating_balance_paise": int((revenue or 0) - (expenses or 0)),
    }


@router.get("/operations", summary="Funnel, per-village / per-collector totals, device data quality, routes and inventory ageing")
def operations(db: DB, principal: CurrentUser, date_from: datetime | None = None, date_to: datetime | None = None):
    from app.models import DeviceReading, FacilityIntake, Route, User

    scope = principal.scope
    start, end = date_range(date_from, date_to)
    ev = [event_scope(scope), CollectionEvent.collected_at >= start, CollectionEvent.collected_at <= end]

    by_village = [
        {"village_id": vid, "village": name, "kg": float(kg), "collections": n}
        for vid, name, kg, n in db.execute(
            select(Village.id, Village.name, func.sum(CollectionEvent.weight_kg), func.count(CollectionEvent.id))
            .join(Village, Village.id == CollectionEvent.village_id).where(*ev).group_by(Village.id).order_by(Village.name)
        )
    ]
    by_collector = [
        {"collector": name, "kg": float(kg), "collections": n, "offline_share": round(float(off or 0) / n * 100, 1) if n else 0}
        for name, kg, n, off in db.execute(
            select(User.full_name, func.sum(CollectionEvent.weight_kg), func.count(CollectionEvent.id),
                   func.sum(case((CollectionEvent.offline_captured.is_(True), 1), else_=0)))
            .join(User, User.id == CollectionEvent.collector_id).where(*ev).group_by(User.full_name)
            .order_by(func.sum(CollectionEvent.weight_kg).desc()).limit(20)
        )
    ]

    fac = facility_scope(scope, BatchMovement.facility_id)
    period = (BatchMovement.occurred_at >= start, BatchMovement.occurred_at <= end)
    moved = {str(t): float(q) for t, q in db.execute(
        select(BatchMovement.movement_type, func.sum(BatchMovement.quantity_kg)).where(fac, *period).group_by(BatchMovement.movement_type))}
    tfac = facility_scope(scope, ProcessingTransfer.source_facility_id) | scope.partner_clause(ProcessingTransfer.partner_id)
    accepted = db.scalar(select(func.coalesce(func.sum(ProcessingTransfer.accepted_kg), 0)).where(
        tfac, ProcessingTransfer.decided_at >= start, ProcessingTransfer.decided_at <= end))
    recovered = {str(s): float(w) for s, w in db.execute(
        select(ProcessingOutcome.evidence_status, func.sum(ProcessingOutcome.output_kg))
        .join(ProcessingTransfer, ProcessingTransfer.id == ProcessingOutcome.transfer_id)
        .where(tfac, ProcessingOutcome.outcome_type.in_(RECOVERED_OUTCOMES), ProcessingOutcome.process_date >= start.date(),
               ProcessingOutcome.process_date <= end.date())
        .group_by(ProcessingOutcome.evidence_status))}
    collected = float(db.scalar(select(func.coalesce(func.sum(CollectionEvent.weight_kg), 0)).where(*ev)))
    funnel = [
        {"stage": "collected", "kg": collected, "note": "collector records"},
        {"stage": "received", "kg": moved.get(MovementType.INTAKE, 0.0), "note": "weighed at facility"},
        {"stage": "sorted", "kg": moved.get(MovementType.SORT_IN, 0.0), "note": "sorted fractions"},
        {"stage": "dispatched", "kg": -moved.get(MovementType.TRANSFER_OUT, 0.0), "note": "sent to processors (not yet recycled)"},
        {"stage": "accepted", "kg": float(accepted or 0), "note": "accepted by processors"},
        {"stage": "recovered_reviewed", "kg": recovered.get(EvidenceStatus.REVIEWED_ACCEPTED, 0.0), "note": "recycled/recovered with reviewed evidence"},
    ]

    dev_rows = db.execute(
        select(Device.device_id, Device.is_simulated, Device.connection_status,
               func.count(DeviceReading.id), func.sum(case((DeviceReading.quality == "ok", 1), else_=0)))
        .join(DeviceReading, DeviceReading.device_pk == Device.id, isouter=True)
        .where(Device.deleted_at.is_(None), (DeviceReading.device_timestamp >= start) | DeviceReading.id.is_(None),
               scope.org_clause(Device.organization_id) if not scope.sees_all else Device.id.isnot(None))
        .group_by(Device.id).order_by(Device.device_id)
    ).all()
    devices = [{"device_id": d, "simulated": sim, "status": str(st), "readings": n, "ok_share": round(float(ok or 0) / n * 100, 1) if n else None}
               for d, sim, st, n, ok in dev_rows]

    route_rows = db.execute(
        select(Route.planned_date, Route.status, Route.distance_m, Route.baseline_distance_m, Route.load_kg, Route.actual_load_kg,
               Route.distance_basis)
        .where(scope.org_clause(Route.organization_id), Route.planned_date >= start.date(), Route.planned_date <= end.date())
        .order_by(Route.planned_date)
    ).all()
    routes = {
        "count": len(route_rows),
        "completed": sum(1 for r in route_rows if r.status == "completed"),
        "planned_distance_m": sum(r.distance_m for r in route_rows),
        "baseline_distance_m": sum(r.baseline_distance_m for r in route_rows if r.baseline_distance_m),
        "comparable_routes": sum(1 for r in route_rows if r.baseline_distance_m),
        "distance_basis": sorted({r.distance_basis for r in route_rows}),
        "expected_load_kg": float(sum(r.load_kg for r in route_rows)),
        "actual_load_kg": float(sum(r.actual_load_kg for r in route_rows if r.actual_load_kg is not None)),
    }

    age_days = func.extract("epoch", utcnow() - MaterialBatch.created_at) / 86400
    bucket = case((age_days < 7, "0-7"), (age_days < 30, "7-30"), else_="30+")
    aging = [
        {"category": label, "bucket": b, "kg": float(kg)}
        for label, b, kg in db.execute(
            select(MaterialCategory.label, bucket, func.sum(MaterialBatch.current_weight_kg))
            .join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
            .where(facility_scope(scope, MaterialBatch.facility_id), MaterialBatch.status == "active")
            .group_by(MaterialCategory.label, bucket).order_by(MaterialCategory.label)
        )
    ]
    intake_gap = db.execute(
        select(func.sum(FacilityIntake.declared_collected_kg), func.sum(FacilityIntake.net_kg))
        .where(facility_scope(scope, FacilityIntake.facility_id), FacilityIntake.received_at >= start, FacilityIntake.received_at <= end,
               FacilityIntake.declared_collected_kg.isnot(None))
    ).one()
    return {
        "range": {"from": start, "to": end},
        "funnel": funnel,
        "by_village": by_village,
        "by_collector": by_collector,
        "devices": devices,
        "routes": routes,
        "inventory_aging": aging,
        "declared_vs_weighed": {"declared_kg": float(intake_gap[0] or 0), "weighed_kg": float(intake_gap[1] or 0)},
        "notes": [
            "Dispatched material is not counted as recycled; only outcomes with reviewed evidence are.",
            "Device data quality = share of readings that passed range/clock/sensor checks.",
        ],
    }
