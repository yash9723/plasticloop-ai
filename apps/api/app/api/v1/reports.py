"""CSV exports and a one-page PDF summary. Every file states the period, scope and whether synthetic data is included."""

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from fpdf import FPDF
from sqlalchemy import literal, select

from app.api.v1 import analytics, finance
from app.api.v1.analytics import date_range, event_scope, facility_scope
from app.models import (
    CollectionEvent,
    CollectionPoint,
    Expense,
    Facility,
    FacilityIntake,
    MaterialBatch,
    MaterialCategory,
    ProcessingOutcome,
    ProcessingPartner,
    ProcessingTransfer,
    Sale,
    Village,
    WasteStream,
)
from app.models.enums import RoleKey
from app.security.deps import DB, Principal, require
from app.security.tokens import utcnow
from app.services.audit import audit

router = APIRouter()
READERS = (RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR)
Kind = Literal["collections", "intakes", "inventory", "transfers", "outcomes", "finance"]


def _rows(db, kind: str, principal: Principal, start: datetime, end: datetime):
    scope = principal.scope
    if kind == "collections":
        yield ["collected_at", "village", "point", "stream", "weight_kg", "measurement_source", "data_origin", "offline_captured", "review_status"]
        q = (select(CollectionEvent.collected_at, Village.name, CollectionPoint.code, WasteStream.code, CollectionEvent.weight_kg,
                    CollectionEvent.measurement_source, CollectionEvent.data_origin, CollectionEvent.offline_captured, CollectionEvent.review_status)
             .join(Village, Village.id == CollectionEvent.village_id).join(CollectionPoint, CollectionPoint.id == CollectionEvent.collection_point_id)
             .join(WasteStream, WasteStream.id == CollectionEvent.waste_stream_id)
             .where(event_scope(scope), CollectionEvent.collected_at >= start, CollectionEvent.collected_at <= end).order_by(CollectionEvent.collected_at))
    elif kind == "intakes":
        yield ["code", "facility", "received_at", "village", "gross_kg", "tare_kg", "net_kg", "declared_collected_kg", "data_origin"]
        q = (select(FacilityIntake.code, Facility.name, FacilityIntake.received_at, Village.name, FacilityIntake.gross_kg, FacilityIntake.tare_kg,
                    FacilityIntake.net_kg, FacilityIntake.declared_collected_kg, FacilityIntake.data_origin)
             .join(Facility, Facility.id == FacilityIntake.facility_id).outerjoin(Village, Village.id == FacilityIntake.origin_village_id)
             .where(facility_scope(scope, FacilityIntake.facility_id), FacilityIntake.received_at >= start, FacilityIntake.received_at <= end)
             .order_by(FacilityIntake.received_at))
    elif kind == "inventory":
        yield ["batch", "facility", "category", "verification_status", "initial_kg", "current_kg", "status", "created_at", "data_origin"]
        q = (select(MaterialBatch.code, Facility.name, MaterialCategory.code, MaterialBatch.verification_status, MaterialBatch.initial_weight_kg,
                    MaterialBatch.current_weight_kg, MaterialBatch.status, MaterialBatch.created_at, MaterialBatch.data_origin)
             .join(Facility, Facility.id == MaterialBatch.facility_id).join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
             .where(facility_scope(scope, MaterialBatch.facility_id), MaterialBatch.created_at <= end).order_by(MaterialBatch.created_at))
    elif kind == "transfers":
        yield ["code", "facility", "partner", "batch", "category", "status", "allocated_kg", "received_kg", "discrepancy_kg", "accepted_kg",
               "rejected_kg", "dispatched_at", "data_origin"]
        q = (select(ProcessingTransfer.code, Facility.name, ProcessingPartner.display_name, MaterialBatch.code, MaterialCategory.code,
                    ProcessingTransfer.status, ProcessingTransfer.allocated_kg, ProcessingTransfer.received_kg, ProcessingTransfer.receipt_discrepancy_kg,
                    ProcessingTransfer.accepted_kg, ProcessingTransfer.rejected_kg, ProcessingTransfer.dispatched_at, ProcessingTransfer.data_origin)
             .join(Facility, Facility.id == ProcessingTransfer.source_facility_id).join(ProcessingPartner, ProcessingPartner.id == ProcessingTransfer.partner_id)
             .join(MaterialBatch, MaterialBatch.id == ProcessingTransfer.batch_id).join(MaterialCategory, MaterialCategory.id == MaterialBatch.category_id)
             .where(facility_scope(scope, ProcessingTransfer.source_facility_id), ProcessingTransfer.created_at >= start,
                    ProcessingTransfer.created_at <= end).order_by(ProcessingTransfer.created_at))
    elif kind == "outcomes":
        yield ["transfer", "partner", "outcome_type", "input_kg", "output_kg", "process_date", "evidence_status", "data_origin"]
        q = (select(ProcessingTransfer.code, ProcessingPartner.display_name, ProcessingOutcome.outcome_type, ProcessingOutcome.input_kg,
                    ProcessingOutcome.output_kg, ProcessingOutcome.process_date, ProcessingOutcome.evidence_status, ProcessingOutcome.data_origin)
             .join(ProcessingTransfer, ProcessingTransfer.id == ProcessingOutcome.transfer_id)
             .join(ProcessingPartner, ProcessingPartner.id == ProcessingTransfer.partner_id)
             .where(facility_scope(scope, ProcessingTransfer.source_facility_id), ProcessingOutcome.process_date >= start.date(),
                    ProcessingOutcome.process_date <= end.date()).order_by(ProcessingOutcome.process_date))
    else:
        yield ["type", "date", "category_or_buyer", "quantity_kg", "amount_inr", "is_estimate", "data_origin"]
        for s in db.scalars(select(Sale).where(facility_scope(scope, Sale.facility_id), Sale.sold_on >= start.date(), Sale.sold_on <= end.date())):
            yield ["sale", s.sold_on, s.buyer_org_id, s.quantity_kg, f"{s.total_paise / 100:.2f}", False, s.data_origin]
        q = (select(literal("expense"), Expense.incurred_on, Expense.category, literal(""), Expense.amount_paise / 100.0, Expense.is_estimate,
                    Expense.data_origin)
             .where(scope.org_clause(Expense.organization_id), Expense.incurred_on >= start.date(), Expense.incurred_on <= end.date()))
    for row in db.execute(q):
        yield [str(v) if v is not None else "" for v in row]


@router.get("/{kind}.csv", summary="Download a CSV export for the period")
def export_csv(kind: Kind, db: DB, date_from: datetime | None = None, date_to: datetime | None = None,
               principal: Principal = Depends(require(*READERS))):
    start, end = date_range(date_from, date_to)
    audit(db, principal, "report.exported", "report", None, after={"kind": kind})
    db.commit()

    # Built in memory before responding: exports are small and the DB session must not outlive the request.
    buf = io.StringIO()
    buf.write(f"# PlasticLoop AI export: {kind} | {start:%Y-%m-%d} to {end:%Y-%m-%d} | rows with data_origin != live are synthetic\n")
    csv.writer(buf).writerows(_rows(db, kind, principal, start, end))

    filename = f"plasticloop-{kind}-{start:%Y%m%d}-{end:%Y%m%d}.csv"
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _ascii(text: str) -> str:
    return text.replace("₹", "INR ").replace("–", "-").replace("—", "-").encode("latin-1", "replace").decode("latin-1")


@router.get("/summary.pdf", summary="One-page PDF summary for the period")
def summary_pdf(db: DB, date_from: datetime | None = None, date_to: datetime | None = None,
                principal: Principal = Depends(require(*READERS))):
    start, end = date_range(date_from, date_to)
    ov = analytics.overview(db, principal, start, end, None)
    ops = analytics.operations(db, principal, start, end)
    fin = finance.summary(db, start, end, principal)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "PlasticLoop AI - operations summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _ascii(f"Period {start:%d %b %Y} - {end:%d %b %Y} | generated {utcnow():%d %b %Y %H:%M} UTC | {principal.label}"),
             new_x="LMARGIN", new_y="NEXT")
    synthetic = any(k != "live" for k in ov["collected_kg_by_origin"]) or fin["includes_synthetic_records"]
    if synthetic:
        pdf.set_text_color(160, 90, 0)
        pdf.multi_cell(0, 6, "Includes SYNTHETIC demo data. These figures demonstrate the system and are not real-world results.",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    def section(title: str, rows: list[tuple[str, str]]):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for label, value in rows:
            pdf.cell(95, 6, _ascii(label))
            pdf.cell(0, 6, _ascii(value), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    section("Collection", [("Collected (collector records)", f"{ov['collected_kg']:.1f} kg"), ("Collections", str(ov["collections"])),
                           ("Active collectors", str(ov["active_collectors"])), ("Flagged for review", str(ov["flagged_collections"]))]
            + [(f"  by origin: {k}", f"{v:.1f} kg") for k, v in ov["collected_kg_by_origin"].items()])
    section("Material flow", [(s["stage"].replace("_", " "), f"{s['kg']:.1f} kg") for s in ops["funnel"]]
            + [("Note", "Dispatched is not recycled; only evidence-reviewed outcomes count as recovered.")])
    r = ops["routes"]
    section("Routes", [("Routes / completed", f"{r['count']} / {r['completed']}"),
                       ("Planned distance", f"{r['planned_distance_m'] / 1000:.1f} km ({', '.join(r['distance_basis']) or '-'})"),
                       ("Fixed-order baseline (same stops)", f"{r['baseline_distance_m'] / 1000:.1f} km on {r['comparable_routes']} routes")])
    section("Finance", [("Revenue (sales)", f"INR {fin['revenue_paise'] / 100:,.2f}"), ("Received", f"INR {fin['received_paise'] / 100:,.2f}"),
                        ("Recorded expenses", f"INR {fin['expenses_recorded_paise'] / 100:,.2f}"),
                        ("Estimated expenses (not in balance)", f"INR {fin['expenses_estimated_paise'] / 100:,.2f}"),
                        ("Operating balance", f"INR {fin['operating_balance_paise'] / 100:,.2f}")])
    devices = ops["devices"]
    section("Devices", [("Devices", str(len(devices))), ("Simulated", str(sum(1 for d in devices if d["simulated"])))])
    audit(db, principal, "report.exported", "report", None, after={"kind": "summary.pdf"})
    db.commit()
    return Response(bytes(pdf.output()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="plasticloop-summary-{start:%Y%m%d}-{end:%Y%m%d}.pdf"'})
