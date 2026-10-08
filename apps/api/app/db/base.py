import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Double, MetaData, Numeric, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Weights: kilograms with gram precision. Money: integer paise (BIGINT) — never floats.
Weight = Numeric(12, 3)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        Decimal: Weight,
        float: Double(),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
    }


class Geography(UserDefinedType):
    """PostGIS geography column. Only used as a generated column from lat/lng (read via SQL functions)."""

    cache_ok = True

    def __init__(self, geom: str = "Point") -> None:
        self.geom = geom

    def get_col_spec(self, **kw: Any) -> str:
        return f"geography({self.geom},4326)"


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SoftDelete:
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


def enum_col(enum_cls: type[Enum], default: Enum | None = None, **kw: Any):
    return mapped_column(
        SAEnum(
            enum_cls,
            native_enum=False,
            length=40,
            values_callable=lambda e: [m.value for m in e],
            validate_strings=True,
            create_constraint=True,
            name=enum_cls.__name__.lower(),
        ),
        default=default,
        **kw,
    )


def flag(default: bool) -> Any:
    return mapped_column(Boolean, default=default, server_default=text("true" if default else "false"))


LOCATION_SQL = "(ST_SetSRID(ST_MakePoint(lng, lat), 4326))::geography"
