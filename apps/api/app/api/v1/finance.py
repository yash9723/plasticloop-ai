"""Revenue, payments and expenses (all money in paise). Estimated expenses are kept separate from recorded ones."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.analytics import date_range, event_scope, facility_scope
from app.core.errors import bad_request, conflict, not_found
from app.models import CollectionEvent, Expense, Facility, Organization, Payment, Sale, Village
from app.models.enums import DataOrigin, ExpenseCategory, PaymentStatus, RoleKey
from app.schemas.common import Kg, Page
from app.security.deps import DB, Principal, require
from app.services.audit import audit
from app.services.listing import PageParams, paginate

router = APIRouter()
VIEWERS = (RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR, RoleKey.EVALUATOR)


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    facility_id: uuid.UUID
    batch_id: uuid.UUID
    buyer_org_id: uuid.UUID
    quantity_kg: Kg
    unit_price_paise: int
    total_paise: int
    sold_on: date
    invoice_number: str | None
    payment_status: PaymentStatus
    data_origin: DataOrigin
    buyer_name: str = ""
    facility_name: str = ""
    paid_paise: int = 0


class PaymentIn(BaseModel):
    amount_paise: int = Field(gt=0, le=10**12)
    paid_on: date
    method: str = Field(pattern=r"^(bank_transfer|upi|cheque|cash|other)$")
    reference: str | None = Field(None, max_length=60)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    category: ExpenseCategory
    amount_paise: int
    incurred_on: date
    description: str | None
    village_id: uuid.UUID | None
    facility_id: uuid.UUID | None
    is_estimate: bool
    assumption_note: str | None
    data_origin: DataOrigin
    created_at: datetime


class ExpenseIn(BaseModel):
    category: ExpenseCategory
    amount_paise: int = Field(gt=0, le=10**12)
    incurred_on: date
    description: str | None = Field(None, max_length=500)
    village_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None
    is_estimate: bool = False
    assumption_note: str | None = Field(None, max_length=500)


def _paid(db: Session, sale_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not sale_ids:
        return {}
    return dict(db.execute(select(Payment.sale_id, func.sum(Payment.amount_paise)).where(Payment.sale_id.in_(sale_ids)).group_by(Payment.sale_id)).all())


def _sales_out(db: Session, sales: list[Sale]) -> list[SaleOut]:
    paid = _paid(db, [s.id for s in sales])
    buyers = dict(db.execute(select(Organization.id, Organization.name).where(Organization.id.in_({s.buyer_org_id for s in sales}))).all()) if sales else {}
    facs = dict(db.execute(select(Facility.id, Facility.name).where(Facility.id.in_({s.facility_id for s in sales}))).all()) if sales else {}
    out = []
    for s in sales:
        o = SaleOut.model_validate(s)
        o.buyer_name, o.facility_name, o.paid_paise = buyers.get(s.buyer_org_id, ""), facs.get(s.facility_id, ""), int(paid.get(s.id) or 0)
        out.append(o)
    return out


@router.get("/summary", summary="Revenue, receipts, receivables and expenses for a period")
def summary(db: DB, date_from: datetime | None = None, date_to: datetime | None = None, principal: Principal = Depends(require(*VIEWERS))):
    scope = principal.scope
    start, end = date_range(date_from, date_to)
    sale_where = (facility_scope(scope, Sale.facility_id), Sale.sold_on >= start.date(), Sale.sold_on <= end.date())
    revenue, sold_kg = db.execute(select(func.coalesce(func.sum(Sale.total_paise), 0), func.coalesce(func.sum(Sale.quantity_kg), 0)).where(*sale_where)).one()
    received = db.scalar(select(func.coalesce(func.sum(Payment.amount_paise), 0)).join(Sale, Sale.id == Payment.sale_id).where(*sale_where))
    exp_where = (scope.org_clause(Expense.organization_id), Expense.incurred_on >= start.date(), Expense.incurred_on <= end.date())
    by_cat = [{"category": str(c), "estimate": est, "amount_paise": int(a)} for c, est, a in db.execute(
        select(Expense.category, Expense.is_estimate, func.sum(Expense.amount_paise)).where(*exp_where)
        .group_by(Expense.category, Expense.is_estimate).order_by(Expense.category))]
    recorded = sum(x["amount_paise"] for x in by_cat if not x["estimate"])
    estimated = sum(x["amount_paise"] for x in by_cat if x["estimate"])
    collected = float(db.scalar(select(func.coalesce(func.sum(CollectionEvent.weight_kg), 0)).where(
        event_scope(scope), CollectionEvent.collected_at >= start, CollectionEvent.collected_at <= end)))
    synthetic = db.scalar(select(func.count()).where(*sale_where, Sale.data_origin != DataOrigin.LIVE)) or 0
    return {
        "range": {"from": start, "to": end},
        "revenue_paise": int(revenue), "sold_kg": float(sold_kg), "received_paise": int(received),
        "receivable_paise": int(revenue) - int(received),
        "expenses_recorded_paise": recorded, "expenses_estimated_paise": estimated, "expenses_by_category": by_cat,
        "operating_balance_paise": int(revenue) - recorded,
        "collected_kg": collected,
        "recorded_cost_per_kg_paise": round(recorded / collected) if collected else None,
        "includes_synthetic_records": bool(synthetic),
        "notes": ["Operating balance uses recorded expenses only; estimates are shown separately.",
                  "Cost per kg = recorded expenses ÷ kg collected in the same period."],
    }


@router.get("/sales", response_model=Page[SaleOut])
def list_sales(db: DB, params: PageParams = Depends(), principal: Principal = Depends(require(*VIEWERS))):
    page = paginate(db, select(Sale).where(facility_scope(principal.scope, Sale.facility_id)), params,
                    {"date": Sale.sold_on, "total": Sale.total_paise}, "-date")
    page["items"] = _sales_out(db, page["items"])
    return page


@router.post("/sales/{sale_id}/payments", response_model=SaleOut, status_code=201, summary="Record a payment received (no money moves here)")
def add_payment(sale_id: uuid.UUID, body: PaymentIn, db: DB, principal: Principal = Depends(require(RoleKey.MRF_OPERATOR))):
    sale = db.scalar(select(Sale).where(Sale.id == sale_id).with_for_update())
    if sale is None:
        raise not_found("Sale")
    principal.scope.ensure_facility(sale.facility_id, "Sale")
    paid = int(_paid(db, [sale.id]).get(sale.id) or 0)
    if paid + body.amount_paise > sale.total_paise:
        raise conflict("OVERPAYMENT", f"Only ₹{(sale.total_paise - paid) / 100:.2f} is outstanding")
    db.add(Payment(sale_id=sale.id, amount_paise=body.amount_paise, paid_on=body.paid_on, method=body.method, reference=body.reference,
                   recorded_by=principal.id, data_origin=sale.data_origin))
    sale.payment_status = PaymentStatus.PAID if paid + body.amount_paise == sale.total_paise else PaymentStatus.PARTIALLY_PAID
    audit(db, principal, "payment.recorded", "sale", sale.id, after={"amount_paise": body.amount_paise})
    db.commit()
    return _sales_out(db, [sale])[0]


@router.get("/expenses", response_model=Page[ExpenseOut])
def list_expenses(db: DB, params: PageParams = Depends(), category: ExpenseCategory | None = None,
                  principal: Principal = Depends(require(*VIEWERS))):
    stmt = select(Expense).where(principal.scope.org_clause(Expense.organization_id))
    if category:
        stmt = stmt.where(Expense.category == category)
    return paginate(db, stmt, params, {"date": Expense.incurred_on, "amount": Expense.amount_paise}, "-date")


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def add_expense(body: ExpenseIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN, RoleKey.MRF_OPERATOR))):
    scope = principal.scope
    if len(scope.org_ids) != 1 and not scope.is_super:
        raise bad_request("ORGANIZATION_REQUIRED", "Expenses belong to exactly one organisation")
    if body.is_estimate and not body.assumption_note:
        raise bad_request("ASSUMPTION_REQUIRED", "Explain how an estimated expense was calculated")
    if body.village_id:
        scope.ensure_village(body.village_id, "Village")
    if body.facility_id:
        scope.ensure_facility(body.facility_id, "Facility")
    org_id = next(iter(scope.org_ids)) if scope.org_ids else db.get(Village, body.village_id).organization_id if body.village_id else None
    if org_id is None:
        raise bad_request("ORGANIZATION_REQUIRED", "Choose a village or facility")
    e = Expense(organization_id=org_id, recorded_by=principal.id, **body.model_dump())
    db.add(e)
    db.flush()
    audit(db, principal, "expense.recorded", "expense", e.id, after={"amount_paise": e.amount_paise, "estimate": e.is_estimate})
    db.commit()
    db.refresh(e)
    return e
