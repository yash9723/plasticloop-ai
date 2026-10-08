"""Packaging-image classification adapters.

* trained        — an Ultralytics YOLO classification model (`VISION_MODEL_PATH`), used only when the weights file exists
                   AND the `ultralytics` package is installed. Its accuracy is whatever `python -m app.ai.evaluate` measured.
* demo_heuristic — hand-written OpenCV colour/texture rules. NOT A TRAINED MODEL; accuracy has not been measured.
                   Exists so the human-review workflow can be demonstrated without a dataset.
* manual_only    — no suggestion; every image goes straight to human labelling.

Every output is a suggestion. Final labels come only from a human review (vision_reviews), and nothing here can mark
material as verified multilayer plastic.
"""

import importlib.util
import math
import time
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np

from app.core.config import settings
from app.models.enums import VISION_LABELS, VisionAdapterKind


@dataclass
class Prediction:
    candidates: list[dict]  # [{"label", "score"}] sorted by score desc
    inference_ms: float
    meta: dict = field(default_factory=dict)

    @property
    def top(self) -> dict | None:
        return self.candidates[0] if self.candidates else None


class ManualOnlyAdapter:
    kind = VisionAdapterKind.MANUAL_ONLY
    name = "manual-only"
    version = "n/a"
    notice = "No automatic suggestion is configured. A person labels every image."

    def predict(self, image: bytes) -> Prediction:
        return Prediction([], 0.0, {"reason": "manual_only"})


class DemoHeuristicAdapter:
    kind = VisionAdapterKind.DEMO_HEURISTIC
    name = "opencv-colour-texture-heuristic"
    version = "0.1"
    notice = ("DEMO HEURISTIC — NOT A TRAINED MODEL. Simple colour/texture rules; accuracy has not been measured. "
              "Use only to demonstrate the review workflow.")

    def features(self, img: np.ndarray) -> dict[str, float]:
        h, w = img.shape[:2]
        scale = 256 / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hue, sat, val = hsv[..., 0], hsv[..., 1].astype(np.float32), hsv[..., 2].astype(np.float32)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return {
            "saturation": float(sat.mean() / 255),
            "specular": float(((val > 235) & (sat < 40)).mean()),  # bright unsaturated glints: foil / metal
            "edges": float(cv2.Canny(gray, 80, 160).mean() / 255),  # crinkles, print, folds
            "brown": float(((hue >= 8) & (hue <= 25) & (sat > 60) & (val > 60) & (val < 220)).mean()),
            "texture": float(min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 2000)),
        }

    def predict(self, image: bytes) -> Prediction:
        start = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Not a readable image")
        f = self.features(img)
        raw = {
            "suspected_multilayer_packaging": 3.0 * f["specular"] + 1.2 * f["saturation"] * f["edges"] * 4 + 0.6 * f["texture"],
            "metal": 3.5 * f["specular"] * (1 - f["saturation"]),
            "paper_cardboard": 4.0 * f["brown"],
            "flexible_plastic": 2.0 * f["edges"] + 0.5 * f["texture"],
            "rigid_plastic": 1.5 * f["saturation"] * (1 - min(1.0, f["edges"] * 4)),
            "other_unknown": 0.35,
        }
        exp = {k: math.exp(4 * v) for k, v in raw.items()}  # softmax, temperature chosen by eye (not tuned on data)
        total = sum(exp.values())
        candidates = sorted(({"label": k, "score": round(v / total, 4)} for k, v in exp.items()), key=lambda c: -c["score"])
        return Prediction(candidates, (time.perf_counter() - start) * 1000, {"features": {k: round(v, 4) for k, v in f.items()}})


class TrainedYoloAdapter:
    kind = VisionAdapterKind.TRAINED
    name = "yolo-classification"
    notice = "Trained classification model. See the evaluation report for measured accuracy on the held-out test set."

    def __init__(self, path):
        from ultralytics import YOLO  # optional dependency

        self.model = YOLO(str(path))
        self.version = path.stem

    def predict(self, image: bytes) -> Prediction:
        start = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Not a readable image")
        res = self.model.predict(img, verbose=False)[0]
        names = res.names
        probs = res.probs.data.tolist()
        candidates = sorted(({"label": names[i], "score": round(float(p), 4)} for i, p in enumerate(probs)), key=lambda c: -c["score"])
        unknown = [c for c in candidates if c["label"] not in VISION_LABELS]
        return Prediction(candidates, (time.perf_counter() - start) * 1000, {"unmapped_labels": [c["label"] for c in unknown]})


def _trained_available() -> bool:
    return settings.vision_model_path.exists() and importlib.util.find_spec("ultralytics") is not None


@lru_cache(maxsize=1)
def get_adapter():
    mode = settings.vision_mode
    if mode == "manual":
        return ManualOnlyAdapter()
    if mode in ("auto", "trained") and _trained_available():
        return TrainedYoloAdapter(settings.vision_model_path)
    if mode == "trained":
        return ManualOnlyAdapter()  # explicitly asked for a model that is not there: never fall back silently to the heuristic
    return DemoHeuristicAdapter()


def active_adapter_info() -> dict:
    adapter = get_adapter()
    return {
        "kind": adapter.kind,
        "name": adapter.name,
        "version": adapter.version,
        "is_trained_model": adapter.kind == VisionAdapterKind.TRAINED,
        "notice": adapter.notice,
        "configured_mode": settings.vision_mode,
        "model_file_present": settings.vision_model_path.exists(),
        "ultralytics_installed": importlib.util.find_spec("ultralytics") is not None,
        "labels": list(VISION_LABELS),
    }
