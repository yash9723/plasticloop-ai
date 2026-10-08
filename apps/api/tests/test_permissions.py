"""Role permissions and tenant (organisation / village) isolation enforced by the backend."""

import pytest

from tests import factories as f


@pytest.fixture
def two_tenants(db):
    gp_a, gp_b = f.org(db, name="GP A"), f.org(db, name="GP B")
    va, vb = f.village(db, gp_a), f.village(db, gp_b)
    s = f.stream(db)
    return {
        "gp_a": gp_a, "gp_b": gp_b, "va": va, "vb": vb, "stream": s,
        "admin_a": f.user(db, "gp_admin", gp_a),
        "admin_b": f.user(db, "gp_admin", gp_b),
        "collector_a": f.user(db, "collector", gp_a),
        "evaluator": f.user(db, "evaluator", f.org(db)),
        "cp_b": f.point(db, vb, [s]),
    }


def test_unauthenticated_requests_rejected(client):
    r = client.get("/api/v1/villages")
    assert r.status_code == 401 and r.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert r.json()["error"]["request_id"]


def test_village_listing_is_scoped(client, two_tenants):
    t = two_tenants
    ids = {v["id"] for v in client.get("/api/v1/villages", headers=f.headers(t["admin_a"])).json()["items"]}
    assert str(t["va"].id) in ids and str(t["vb"].id) not in ids


def test_cross_tenant_reads_and_writes_return_404(client, two_tenants):
    t = two_tenants
    h = f.headers(t["admin_a"])
    assert client.get(f"/api/v1/villages/{t['vb'].id}", headers=h).status_code == 404
    assert client.get(f"/api/v1/collection-points/{t['cp_b'].id}", headers=h).status_code == 404
    assert client.patch(f"/api/v1/collection-points/{t['cp_b'].id}", headers=h, json={"name": "hijacked"}).status_code == 404
    r = client.post("/api/v1/collection-points", headers=h,
                    json={"village_id": str(t["vb"].id), "name": "Point X", "stream_ids": [str(t["stream"].id)]})
    assert r.status_code == 404


def test_collector_cannot_administer(client, two_tenants):
    t = two_tenants
    h = f.headers(t["collector_a"])
    r = client.post("/api/v1/villages", headers=h, json={"organization_id": str(t["gp_a"].id), "name": "New", "code": "NEW-1"})
    assert r.status_code == 403
    assert client.get("/api/v1/users", headers=h).status_code == 403


def test_evaluator_reads_everything_but_cannot_write(client, two_tenants):
    t = two_tenants
    h = f.headers(t["evaluator"])
    ids = {v["id"] for v in client.get("/api/v1/villages", headers=h).json()["items"]}
    assert {str(t["va"].id), str(t["vb"].id)} <= ids
    r = client.post("/api/v1/collection-points", headers=h,
                    json={"village_id": str(t["va"].id), "name": "Point X", "stream_ids": [str(t["stream"].id)]})
    assert r.status_code == 403 and "read-only" in r.json()["error"]["message"].lower()


def test_user_directory_is_scoped_to_own_organisation(client, two_tenants):
    t = two_tenants
    emails = {u["email"] for u in client.get("/api/v1/users", headers=f.headers(t["admin_a"])).json()["items"]}
    assert t["collector_a"].email in emails and t["admin_b"].email not in emails


def test_household_sees_only_own_records(client, db, two_tenants):
    t = two_tenants
    owner = f.user(db, "household", t["gp_a"])
    mine, theirs = f.household(db, t["va"], owner), f.household(db, t["va"])
    h = f.headers(owner)
    listed = client.get("/api/v1/households", headers=h).json()["items"]
    assert [x["id"] for x in listed] == [str(mine.id)]
    assert client.get(f"/api/v1/households/{theirs.id}", headers=h).status_code == 404
    assert client.post("/api/v1/sync/batch", headers=h, json={"events": [{"event_id": "8a0f6b8e-1f7e-4a65-9d59-1d5b6d3b1a11", "payload": {}}]}).status_code == 403


def test_household_pii_redacted_for_evaluator(client, db, two_tenants):
    t = two_tenants
    hh = f.household(db, t["va"])
    data = client.get(f"/api/v1/households/{hh.id}", headers=f.headers(t["evaluator"])).json()["household"]
    assert data["redacted"] is True and data["phone"] is None and data["address_line"] is None and data["lat"] is None
