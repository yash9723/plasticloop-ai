"""Seeds the full synthetic demo inside the test transaction, then runs the 12-step guided demo through the API."""

from sqlalchemy import select

from app.models import User, Village
from app.scripts.seed_demo import DEMO_ACCOUNTS, DOMAIN, REGION, VILLAGES, Seeder
from tests import factories as f

API = "/api/v1"


def test_seed_and_full_walkthrough(db, client):
    summary = Seeder(db).run()
    assert summary["villages"] == len(VILLAGES)
    assert summary["collection_points"] == sum(v[7] for v in VILLAGES) and summary["devices"] == 4 and summary["transfers"] >= 1
    # Every demo village is in the Bengaluru area (Karnataka) and has a panchayat admin that is listed on the login page.
    karnataka = {v.code: v for v in db.scalars(select(Village).where(Village.state == "Karnataka"))}
    assert set(karnataka) == set(REGION) == {v[0] for v in VILLAGES} == {"DVH", "HSK", "NLM", "ANK", "DBP", "SRP", "BDI"}
    listed = {email for email, _, _ in DEMO_ACCOUNTS}
    for name in ("devanahalli", "hoskote", "nelamangala", "anekal", "doddaballapur", "sarjapur", "bidadi"):
        email = f"gp.{name}@{DOMAIN}"
        assert email in listed and db.scalar(select(User.id).where(User.email == email)) is not None
    # Field staff and households default to Kannada; admins and the platform default to English.
    assert db.scalar(select(User.preferred_language).where(User.email == f"collector1@{DOMAIN}")) == "kn"
    assert db.scalar(select(User.preferred_language).where(User.email == f"gp.devanahalli@{DOMAIN}")) == "en"
    evaluator = db.scalar(select(User).where(User.email == f"evaluator@{DOMAIN}"))
    h = f.headers(evaluator)
    assert client.post(f"{API}/demo/walkthrough/2", headers=h).json()["error"]["code"] == "PREVIOUS_STEP_PENDING"
    results = {}
    for n in range(1, 13):
        r = client.post(f"{API}/demo/walkthrough/{n}", headers=h)
        assert r.status_code == 200, (n, r.text)
        results[r.json()["key"]] = r.json()["result"]
    assert results["offline_collection"] == {"first_sync": "accepted", "retry": "duplicate", "weight_kg": 5.4}
    assert results["sorting"]["mlp_status"] == "suspected" and results["sorting"]["difference_kg"] == 0.5
    assert results["vision_review"]["final_label"] == "suspected_multilayer_packaging"
    assert results["dispatch"]["counted_as_recycled"] is False
    assert results["outcome_evidence"]["evidence_status_before_review"] == "submitted"
    assert results["outcome_evidence"]["evidence_status"] == "reviewed_accepted"
    assert client.post(f"{API}/demo/walkthrough/3", headers=h).status_code == 409  # already done
    steps = client.get(f"{API}/demo/walkthrough", headers=h).json()["steps"]
    assert all(s["done"] for s in steps)
    client.post(f"{API}/demo/walkthrough/reset", headers=h)
    assert not any(s["done"] for s in client.get(f"{API}/demo/walkthrough", headers=h).json()["steps"])
    collector = db.scalar(select(User).where(User.email == f"collector1@{DOMAIN}"))
    assert client.post(f"{API}/demo/walkthrough/1", headers=f.headers(collector)).status_code == 403
