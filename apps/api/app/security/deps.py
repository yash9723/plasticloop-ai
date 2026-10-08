"""FastAPI dependencies: database session, authenticated principal, role checks."""

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden
from app.db.session import get_db
from app.models import User
from app.security.scope import AccessScope, build_scope
from app.security.tokens import decode_access_token

DB = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: User
    scope: AccessScope

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def label(self) -> str:
        return f"{self.user.full_name} <{self.user.email}>"


def get_principal(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Principal:
    if creds is None:
        raise AppError(401, "NOT_AUTHENTICATED", "Sign in required")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "Session expired, refresh required") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "INVALID_TOKEN", "Invalid access token") from exc
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except ValueError as exc:
        raise AppError(401, "INVALID_TOKEN", "Invalid access token") from exc
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AppError(401, "ACCOUNT_UNAVAILABLE", "Account is disabled or removed")
    return Principal(user=user, scope=build_scope(db, user))


CurrentUser = Annotated[Principal, Depends(get_principal)]


def require(*roles: str):
    """Allow super admins plus the listed roles. Evaluators are only allowed where explicitly listed."""

    def checker(principal: CurrentUser) -> Principal:
        if principal.scope.is_super or principal.scope.roles & set(roles):
            return principal
        if principal.scope.is_evaluator:
            raise forbidden("Evaluator accounts are read-only")
        raise forbidden()

    return checker
