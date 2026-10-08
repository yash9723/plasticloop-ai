import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, bad_request, conflict, error_body, forbidden, not_found
from app.core.ratelimit import client_ip, limiter
from app.models import Household, Invitation, Organization, RefreshToken, User, UserMembership, Village
from app.models.enums import RoleKey
from app.schemas.auth import (
    AcceptInviteIn,
    ChangePasswordIn,
    InvitationIn,
    InvitationOut,
    InvitationPublic,
    LoginIn,
    MembershipOut,
    MeOut,
    RegisterIn,
    TokenOut,
)
from app.security.deps import DB, CurrentUser, Principal, require
from app.security.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.security.scope import build_scope
from app.security.tokens import create_access_token, new_opaque_token, sha256_hex, utcnow
from app.services.audit import audit

router = APIRouter()

REFRESH_COOKIE = "pl_refresh"
COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER_VALUE = "plasticloop"
ROTATION_GRACE_S = 20
INVITE_TTL = timedelta(days=7)

# Who may invite whom (scope ceilings). Super admins may invite any role.
INVITE_CEILING: dict[str, set[str]] = {
    RoleKey.GP_ADMIN: {RoleKey.COLLECTOR, RoleKey.DRIVER},
}


# ---------- helpers ----------

def build_me(db: Session, user: User) -> MeOut:
    scope = build_scope(db, user)
    org_ids = {m.organization_id for m in user.memberships}
    orgs = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))} if org_ids else {}
    household_id = db.scalar(select(Household.id).where(Household.user_id == user.id))
    return MeOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        full_name=user.full_name,
        preferred_language=user.preferred_language,
        roles=sorted(scope.roles),
        memberships=[
            MembershipOut(
                organization_id=m.organization_id,
                organization_name=orgs[m.organization_id].name if m.organization_id in orgs else None,
                organization_type=orgs[m.organization_id].org_type if m.organization_id in orgs else None,
                role=m.role_key,
                village_id=m.village_id,
                facility_id=m.facility_id,
            )
            for m in user.memberships
        ],
        household_id=household_id,
        village_ids=sorted(scope.village_ids | scope.household_village_ids, key=str),
        facility_ids=sorted(scope.facility_ids, key=str),
        read_only=scope.is_evaluator and not scope.is_super and len(scope.roles) == 1,
        demo_mode=settings.demo_enabled,
    )


def _csrf_check(request: Request) -> None:
    if request.headers.get("x-requested-with") != CSRF_HEADER_VALUE:
        raise AppError(403, "CSRF_CHECK_FAILED", "Missing anti-CSRF header")


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )


def _session_failure(code: str, message: str) -> JSONResponse:
    resp = JSONResponse(error_body(code, message), status_code=401)
    resp.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, secure=settings.cookie_secure, httponly=True, samesite="strict")
    return resp


def _issue_session(
    db: Session, user: User, request: Request, response: Response, family_id: uuid.UUID | None = None
) -> tuple[RefreshToken, TokenOut]:
    raw, token_hash = new_opaque_token()
    rt = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=token_hash,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        user_agent=(request.headers.get("user-agent") or "")[:255],
        ip=client_ip(request),
    )
    db.add(rt)
    db.flush()
    _set_refresh_cookie(response, raw)
    access, expires_in = create_access_token(user.id)
    return rt, TokenOut(access_token=access, expires_in=expires_in, user=build_me(db, user))


def _revoke_family(db: Session, family_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


def _revoke_all_for_user(db: Session, user_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


def _email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(func.lower(User.email) == email.lower())) is not None


# ---------- session endpoints ----------

@router.post("/login", response_model=TokenOut, summary="Sign in with email/phone + password")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    ident = body.identifier.strip().lower()
    limiter.check(f"login:id:{ident}", 10, 300)
    limiter.check(f"login:ip:{client_ip(request)}", 60, 300)

    user = db.scalar(
        select(User).where(or_(func.lower(User.email) == ident, User.phone == body.identifier.strip()), User.deleted_at.is_(None))
    )
    if user is None:
        verify_password(DUMMY_HASH, body.password)
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email/phone or password")
    if not verify_password(user.password_hash, body.password):
        user.failed_logins += 1
        db.commit()
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email/phone or password")
    if not user.is_active:
        raise AppError(403, "ACCOUNT_DISABLED", "This account is disabled")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.failed_logins = 0
    user.last_login_at = utcnow()
    _, out = _issue_session(db, user, request, response)
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return out


@router.post("/refresh", response_model=TokenOut, summary="Rotate the refresh cookie and get a new access token")
def refresh(request: Request, response: Response, db: DB):
    _csrf_check(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return _session_failure("NO_SESSION", "Not signed in")
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw)).with_for_update())
    if rt is None:
        return _session_failure("NO_SESSION", "Not signed in")

    now = utcnow()
    user = db.get(User, rt.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        _revoke_family(db, rt.family_id, "account_unavailable")
        db.commit()
        return _session_failure("ACCOUNT_UNAVAILABLE", "Account is disabled or removed")

    if rt.revoked_at is not None:
        if rt.revoked_reason == "rotated" and (now - rt.revoked_at).total_seconds() < ROTATION_GRACE_S:
            # ponytail: concurrent refresh from a second tab; the browser already holds the successor cookie,
            # so hand out an access token without rotating again. Window is short and the family stays intact.
            access, expires_in = create_access_token(user.id)
            return TokenOut(access_token=access, expires_in=expires_in, user=build_me(db, user))
        _revoke_family(db, rt.family_id, "reuse_detected")
        audit(db, user, "auth.refresh_reuse_detected", "user", user.id, after={"family_id": str(rt.family_id)})
        db.commit()
        return _session_failure("REFRESH_REUSED", "Session ended for security reasons. Please sign in again.")

    if rt.expires_at <= now:
        return _session_failure("SESSION_EXPIRED", "Session expired. Please sign in again.")

    new_rt, out = _issue_session(db, user, request, response, family_id=rt.family_id)
    rt.revoked_at = now
    rt.revoked_reason = "rotated"
    rt.replaced_by_id = new_rt.id
    db.commit()
    return out


@router.post("/logout", status_code=204, summary="Revoke this session")
def logout(request: Request, db: DB):
    _csrf_check(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw)))
        if rt is not None:
            _revoke_family(db, rt.family_id, "logout")
            db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, secure=settings.cookie_secure, httponly=True, samesite="strict")
    return resp


@router.get("/me", response_model=MeOut)
def me(principal: CurrentUser, db: DB):
    return build_me(db, principal.user)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, principal: CurrentUser, db: DB):
    user = principal.user
    limiter.check(f"chpw:{user.id}", 10, 300)
    if not verify_password(user.password_hash, body.current_password):
        raise AppError(400, "INVALID_CREDENTIALS", "Current password is incorrect")
    validate_password_strength(body.new_password, user.email)
    user.password_hash = hash_password(body.new_password)
    _revoke_all_for_user(db, user.id, "password_changed")
    audit(db, principal, "auth.password_changed", "user", user.id)
    db.commit()
    return Response(status_code=204)


# ---------- registration ----------

@router.post("/register", response_model=TokenOut, status_code=201, summary="Citizen self-registration (household role only)")
def register(body: RegisterIn, request: Request, response: Response, db: DB):
    limiter.check(f"register:ip:{client_ip(request)}", 10, 3600)
    validate_password_strength(body.password, body.email)
    village = db.get(Village, body.village_id)
    if village is None or village.deleted_at is not None:
        raise bad_request("UNKNOWN_VILLAGE", "Select a valid village")
    email = body.email.lower()
    if _email_taken(db, email):
        raise conflict("EMAIL_TAKEN", "An account with this email already exists")
    if body.phone and db.scalar(select(User.id).where(User.phone == body.phone)):
        raise conflict("PHONE_TAKEN", "An account with this phone number already exists")

    user = User(email=email, phone=body.phone, full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(UserMembership(user_id=user.id, organization_id=village.organization_id, role_key=RoleKey.HOUSEHOLD))
    db.add(
        Household(
            village_id=village.id,
            user_id=user.id,
            household_code=f"{village.code}-HH-{secrets.token_hex(3).upper()}",
            head_name=user.full_name,
            phone=body.phone,
            address_line=body.address_line,
            consent_at=utcnow(),
        )
    )
    db.flush()
    db.expire(user, ["memberships"])
    audit(db, user, "auth.register_household", "user", user.id, after={"village_id": village.id})
    _, out = _issue_session(db, user, request, response)
    db.commit()
    return out


# ---------- invitations (staff accounts) ----------

def _invite_out(inv: Invitation, token: str | None = None) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role_key,
        organization_id=inv.organization_id,
        village_id=inv.village_id,
        facility_id=inv.facility_id,
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        revoked_at=inv.revoked_at,
        created_at=inv.created_at,
        token=token,
        invite_path=f"/register?invite={token}" if token else None,
    )


@router.post("/invitations", response_model=InvitationOut, status_code=201, summary="Invite a staff user (scope-limited)")
def create_invitation(body: InvitationIn, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    scope = principal.scope
    if not scope.is_super:
        allowed = set().union(*(INVITE_CEILING.get(r, set()) for r in scope.roles))
        if body.role not in allowed:
            raise forbidden(f"You cannot invite users with role '{body.role}'")
        scope.ensure_org(body.organization_id, "Organization")
        if body.village_id:
            scope.ensure_village(body.village_id, "Village")
    if db.get(Organization, body.organization_id) is None:
        raise not_found("Organization")
    if _email_taken(db, body.email):
        raise conflict("EMAIL_TAKEN", "An account with this email already exists")

    raw, token_hash = new_opaque_token()
    inv = Invitation(
        token_hash=token_hash,
        email=body.email.lower(),
        role_key=body.role,
        organization_id=body.organization_id,
        village_id=body.village_id,
        facility_id=body.facility_id,
        invited_by=principal.id,
        expires_at=utcnow() + INVITE_TTL,
    )
    db.add(inv)
    db.flush()
    audit(db, principal, "auth.invitation_created", "invitation", inv.id, after={"email": inv.email, "role": inv.role_key})
    db.commit()
    db.refresh(inv)
    return _invite_out(inv, raw)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    stmt = select(Invitation).order_by(Invitation.created_at.desc()).limit(200)
    if not principal.scope.is_super:
        stmt = stmt.where(principal.scope.org_clause(Invitation.organization_id))
    return [_invite_out(i) for i in db.scalars(stmt)]


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, db: DB, principal: Principal = Depends(require(RoleKey.GP_ADMIN))):
    inv = db.get(Invitation, invitation_id)
    if inv is None:
        raise not_found("Invitation")
    principal.scope.ensure_org(inv.organization_id, "Invitation")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = utcnow()
        audit(db, principal, "auth.invitation_revoked", "invitation", inv.id)
        db.commit()
    return Response(status_code=204)


def _valid_invitation(db: Session, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == sha256_hex(token)))
    if inv is None or inv.revoked_at or inv.accepted_at or inv.expires_at <= utcnow():
        raise AppError(404, "INVITATION_INVALID", "This invitation is invalid, used or expired")
    return inv


@router.get("/invitations/lookup/{token}", response_model=InvitationPublic, summary="Public: show what an invite is for")
def lookup_invitation(token: str, request: Request, db: DB):
    limiter.check(f"invite-lookup:{client_ip(request)}", 30, 300)
    inv = _valid_invitation(db, token)
    org = db.get(Organization, inv.organization_id)
    return InvitationPublic(email=inv.email, role=inv.role_key, organization_name=org.name if org else "", expires_at=inv.expires_at)


@router.post("/invitations/accept", response_model=TokenOut, status_code=201)
def accept_invitation(body: AcceptInviteIn, request: Request, response: Response, db: DB):
    limiter.check(f"invite-accept:{client_ip(request)}", 20, 3600)
    inv = _valid_invitation(db, body.token)
    validate_password_strength(body.password, inv.email)
    if _email_taken(db, inv.email):
        raise conflict("EMAIL_TAKEN", "An account with this email already exists. Sign in instead.")
    if body.phone and db.scalar(select(User.id).where(User.phone == body.phone)):
        raise conflict("PHONE_TAKEN", "An account with this phone number already exists")
    user = User(email=inv.email, phone=body.phone, full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(
        UserMembership(
            user_id=user.id,
            organization_id=inv.organization_id,
            role_key=inv.role_key,
            village_id=inv.village_id,
            facility_id=inv.facility_id,
        )
    )
    inv.accepted_at = utcnow()
    inv.accepted_user_id = user.id
    db.flush()
    db.expire(user, ["memberships"])
    audit(db, user, "auth.invitation_accepted", "invitation", inv.id, after={"role": inv.role_key})
    _, out = _issue_session(db, user, request, response)
    db.commit()
    return out
