"""Vision: adapters are suggestions only, human review is stored separately, metrics are computed honestly."""

import io

import numpy as np
import pytest
from PIL import Image

from app.ai import adapters
from app.ai.dataset import split
from app.ai.evaluate import metrics
from app.core.config import settings
from tests import factories as f

API = "/api/v1"


def png(color=(40, 160, 60), size=(64, 48), noise=False) -> bytes:
    arr = np.full((size[1], size[0], 3), color, np.uint8)
    if noise:
        arr = np.random.default_rng(1).integers(0, 255, arr.shape, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def test_metrics_confusion_and_f1():
    labels = ["a", "b"]
    m = metrics([("a", "a"), ("a", "b"), ("b", "b"), ("b", "(none)")], labels)
    assert m["accuracy"] == 0.5 and m["confusion"] == [[1, 1, 0], [0, 1, 1]]
    a, b = m["per_class"]
    assert (a["precision"], a["recall"]) == (1.0, 0.5) and (b["precision"], b["recall"]) == (0.5, 0.5)
    assert m["macro_f1"] == round((a["f1"] + b["f1"]) / 2, 4)
    assert metrics([], labels)["accuracy"] is None


def test_split_is_stratified_and_reproducible(tmp_path):
    for label in ("metal", "paper_cardboard"):
        (tmp_path / "raw" / label).mkdir(parents=True)
        for i in range(10):
            (tmp_path / "raw" / label / f"{i}.png").write_bytes(png())
    a = split(tmp_path / "raw", tmp_path / "out1", seed=7)
    b = split(tmp_path / "raw", tmp_path / "out2", seed=7)
    assert a == b and a["metal"] == {"train": 7, "val": 2, "test": 1}
    assert sorted(p.name for p in (tmp_path / "out1/test/metal").iterdir()) == sorted(p.name for p in (tmp_path / "out2/test/metal").iterdir())


def test_demo_heuristic_is_labelled_and_returns_distribution():
    h = adapters.DemoHeuristicAdapter()
    pred = h.predict(png(noise=True))
    assert len(pred.candidates) == 6 and abs(sum(c["score"] for c in pred.candidates) - 1) < 0.01
    assert "NOT A TRAINED MODEL" in h.notice
    with pytest.raises(ValueError):
        h.predict(b"not an image")


def test_trained_mode_without_weights_never_falls_back_to_heuristic(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vision_mode", "trained")
    monkeypatch.setattr(settings, "vision_model_path", tmp_path / "missing.pt")
    adapters.get_adapter.cache_clear()
    try:
        info = adapters.active_adapter_info()
        assert info["kind"] == "manual_only" and info["is_trained_model"] is False
    finally:
        adapters.get_adapter.cache_clear()


@pytest.fixture
def mrf(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    op_org = f.org(db, "mrf_operator")
    fac = f.facility(db, op_org)
    return {"facility": fac, "operator": f.user(db, "mrf_operator", op_org, facility_obj=fac)}


def test_classify_then_review_keeps_suggestion_and_final_label_separate(mrf, client):
    h = f.headers(mrf["operator"])
    r = client.post(f"{API}/vision/classify", headers=h, files={"file": ("bag.png", png(noise=True), "image/png")})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["adapter"] == "demo_heuristic" and p["facility_id"] == str(mrf["facility"].id)
    assert len(p["candidates"]) == 6 and p["low_confidence"] == (p["top_score"] < p["threshold"])
    queue = client.get(f"{API}/vision/predictions", headers=h, params={"reviewed": False}).json()
    assert [x["id"] for x in queue["items"]] == [p["id"]]
    rv = client.post(f"{API}/vision/predictions/{p['id']}/review", headers=h, json={"final_label": "suspected_multilayer_packaging"})
    assert rv.status_code == 200 and rv.json()["review"]["final_label"] == "suspected_multilayer_packaging"
    assert rv.json()["top_label"] == p["top_label"]  # the model's suggestion is never overwritten
    again = client.post(f"{API}/vision/predictions/{p['id']}/review", headers=h, json={"final_label": "metal"})
    assert again.status_code == 409


def test_vision_permissions(mrf, client, db):
    evaluator = f.user(db, "evaluator", f.org(db))
    r = client.post(f"{API}/vision/classify", headers=f.headers(evaluator), files={"file": ("x.png", png(), "image/png")})
    assert r.status_code == 403
    status = client.get(f"{API}/vision/status", headers=f.headers(evaluator)).json()
    assert status["adapter"]["is_trained_model"] is False and (status["evaluation"] is None) == (status["evaluation_notice"] is not None)
    p = client.post(f"{API}/vision/classify", headers=f.headers(mrf["operator"]), files={"file": ("x.png", png(), "image/png")}).json()
    other = f.user(db, "mrf_operator", f.org(db, "mrf_operator"))
    assert client.post(f"{API}/vision/predictions/{p['id']}/review", headers=f.headers(other), json={"final_label": "metal"}).status_code == 404


def test_rejects_non_image(mrf, client):
    r = client.post(f"{API}/vision/classify", headers=f.headers(mrf["operator"]), files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code in (400, 415)

