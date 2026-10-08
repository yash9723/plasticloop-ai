"""Audit trail for sensitive mutations. Rows are added to the caller's transaction (no commit here)."""

import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.models import AuditLog


def snapshot(obj: Any, *fields: str) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in fields}


def audit(
    db: Session,
    actor: Any,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """`actor` is a Principal, a User, or None (system)."""
    user = getattr(actor, "user", actor)
    actor_id: uuid.UUID | None = getattr(user, "id", None)
    label = f"{user.full_name} <{user.email}>" if user is not None and hasattr(user, "email") else "system"
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            actor_label=label,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=jsonable_encoder(before) if before is not None else None,
            after=jsonable_encoder(after) if after is not None else None,
            request_id=request_id_ctx.get(),
        )
    )
