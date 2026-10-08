"""Pagination + whitelisted sorting shared by list endpoints."""

from dataclasses import dataclass
from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import bad_request


@dataclass
class PageParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(25, ge=1, le=200)
    sort: str | None = Query(None, description="Field name; prefix with '-' for descending")


def paginate(
    db: Session,
    stmt: Select,
    params: PageParams,
    sort_map: dict[str, Any],
    default_sort: str,
    scalars: bool = True,
) -> dict:
    key = params.sort or default_sort
    column = sort_map.get(key.lstrip("-"))
    if column is None:
        raise bad_request("INVALID_SORT", f"Sort must be one of: {', '.join(sorted(sort_map))}")
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    ordered = stmt.order_by(column.desc().nulls_last() if key.startswith("-") else column.asc().nulls_last())
    page_stmt = ordered.limit(params.page_size).offset((params.page - 1) * params.page_size)
    rows = db.scalars(page_stmt).all() if scalars else db.execute(page_stmt).all()
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}
