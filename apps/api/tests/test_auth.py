from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.models import Household, Invitation, RefreshToken, UserMembership
from app.security.passwords import hash_password
from app.security.tokens import sha256_hex
from tests import factories as f
from tests.conftest import CSRF, cookie_client


def _login(client, user):
    r = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": f.PASSWORD})
    assert r.status_code == 200, r.text
    return r


def test_password_hashing_uses_argon2id():
    assert hash_password("Abcdefgh12").startswith("$argon2id$")


def test_login_returns_access_token_and_httponly_refresh_cookie(client, db):
    u = f.user(db, "gp_admin", f.org(db))
    r = _login(client, u)
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["roles"] == ["gp_admin"]
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie and "path=/api/v1/auth" in set_cookie
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code == 200


def test_invalid_credentials_are_indistinguishable(client, db):
    u = f.user(db, "collector", f.org(db))
    wrong = client.post("/api/v1/auth/login", json={"identifier": u.email, "password": "nope-nope-1"})
    unknown = client.post("/api/v1/auth/login", json={"identifier": "ghost@test.example", "password": "nope-nope-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_refresh_requires_csrf_header(client, db):
    raw = _login(client, f.user(db, "collector", f.org(db))).cookies["pl_refresh"]
    r = cookie_client(pl_refresh=raw).post("/api/v1/auth/refresh")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_CHECK_FAILED"


def test_refresh_rotates_and_reuse_revokes_family(client, db):
    raw1 = _login(client, f.user(db, "collector", f.org(db))).cookies["pl_refresh"]

    r2 = cookie_client(pl_refresh=raw1).post("/api/v1/auth/refresh", headers=CSRF)
    assert r2.status_code == 200, r2.text
    raw2 = r2.cookies["pl_refresh"]
    assert raw2 != raw1

    # Within the grace window (concurrent tab), replaying the old token yields an access token without rotation.
    grace = cookie_client(pl_refresh=raw1).post("/api/v1/auth/refresh", headers=CSRF)
    assert grace.status_code == 200 and "pl_refresh" not in grace.cookies

    # After the grace window, replay = suspected theft: the whole family is revoked.
    old = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw1)))
    old.revoked_at = datetime.now(UTC) - timedelta(minutes=5)
    db.flush()
    replay = cookie_client(pl_refresh=raw1).post("/api/v1/auth/refresh", headers=CSRF)
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "REFRESH_REUSED"
    assert cookie_client(pl_refresh=raw2).post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_logout_revokes_refresh_token(client, db):
    raw = _login(client, f.user(db, "driver", f.org(db))).cookies["pl_refresh"]
    assert cookie_client(pl_refresh=raw).post("/api/v1/auth/logout", headers=CSRF).status_code == 204
    assert cookie_client(pl_refresh=raw).post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_expired_access_token_is_rejected_with_refreshable_code(client, db):
    u = f.user(db, "collector", f.org(db))
    past = datetime.now(UTC) - timedelta(minutes=30)
    token = jwt.encode({"sub": str(u.id), "type": "access", "iss": "plasticloop", "iat": past, "exp": past + timedelta(minutes=1)},
                       settings.jwt_secret, algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_tampered_token_rejected(client, db):
    u = f.user(db, "collector", f.org(db))
    forged = jwt.encode({"sub": str(u.id), "type": "access", "iss": "plasticloop", "exp": datetime.now(UTC) + timedelta(hours=1)},
                        "not-the-secret-not-the-secret-123", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).json()["error"]["code"] == "INVALID_TOKEN"


def test_citizen_registration_creates_household_only(client, db):
    v = f.village(db, f.org(db))
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Lakshmi Devi", "email": "lakshmi@test.example", "password": "Plastic2026x", "village_id": str(v.id),
        "consent": True, "role": "super_admin",  # extra fields cannot escalate privileges
    })
    assert r.status_code == 201, r.text
    assert r.json()["user"]["roles"] == ["household"]
    uid = r.json()["user"]["id"]
    assert db.scalar(select(Household).where(Household.user_id == uid)) is not None


def test_registration_requires_consent_and_strong_password(client, db):
    v = f.village(db, f.org(db))
    base = {"full_name": "A B", "email": "ab@test.example", "village_id": str(v.id)}
    assert client.post("/api/v1/auth/register", json={**base, "password": "Plastic2026x", "consent": False}).status_code == 422
    weak = client.post("/api/v1/auth/register", json={**base, "password": "aaaaaaaaaaaa", "consent": True})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "WEAK_PASSWORD"


def test_invitation_ceiling_and_acceptance(client, db):
    gp = f.org(db)
    admin = f.user(db, "gp_admin", gp)
    h = f.headers(admin)
    denied = client.post("/api/v1/auth/invitations", headers=h,
                         json={"email": "boss@test.example", "role": "super_admin", "organization_id": str(gp.id)})
    assert denied.status_code == 403
    other = f.org(db)
    cross = client.post("/api/v1/auth/invitations", headers=h,
                        json={"email": "x@test.example", "role": "collector", "organization_id": str(other.id)})
    assert cross.status_code == 404

    ok = client.post("/api/v1/auth/invitations", headers=h,
                     json={"email": "newcollector@test.example", "role": "collector", "organization_id": str(gp.id)})
    assert ok.status_code == 201, ok.text
    token = ok.json()["token"]
    assert db.scalar(select(Invitation.token_hash).where(Invitation.id == ok.json()["id"])) != token  # only hash stored

    accept = client.post("/api/v1/auth/invitations/accept", json={"token": token, "full_name": "New Collector", "password": "Collect2026x"})
    assert accept.status_code == 201, accept.text
    assert accept.json()["user"]["roles"] == ["collector"]
    member = db.scalar(select(UserMembership).where(UserMembership.user_id == accept.json()["user"]["id"]))
    assert member.organization_id == gp.id
    assert client.post("/api/v1/auth/invitations/accept", json={"token": token, "full_name": "Again", "password": "Collect2026x"}).status_code == 404


def test_login_rate_limited(client, db):
    u = f.user(db, "collector", f.org(db))
    codes = [client.post("/api/v1/auth/login", json={"identifier": u.email, "password": "wrong-pass-1"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
