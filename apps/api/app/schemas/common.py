from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")

# Decimal in the DB, plain JSON number on the wire (Pydantic would otherwise emit strings).
Kg = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
# Validated kilogram input: non-negative, gram precision.
KgIn = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]
PositiveKgIn = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Ok(BaseModel):
    ok: bool = True
    message: str | None = None
