"""Evaluate the active adapter on a held-out test split and write an honest report.

    python -m app.ai.evaluate --data data/vision/test

Writes models/eval_report.json (shown on /waste-classification) and models/confusion_matrix.csv.
Only numbers computed here may be quoted as accuracy; nothing is estimated or extrapolated.
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from app.ai.adapters import active_adapter_info, get_adapter
from app.ai.dataset import list_images
from app.core.config import API_DIR
from app.models.enums import VISION_LABELS

REPORT_PATH = API_DIR / "models" / "eval_report.json"
CONFUSION_PATH = API_DIR / "models" / "confusion_matrix.csv"


def metrics(pairs: list[tuple[str, str]], labels: list[str]) -> dict:
    """pairs = [(true, predicted)]. Predicted may be '(none)' when the adapter gave no suggestion."""
    index = {label: i for i, label in enumerate(labels)}
    cols = labels + ["(none)"]
    confusion = [[0] * len(cols) for _ in labels]
    for true, pred in pairs:
        confusion[index[true]][cols.index(pred) if pred in cols else len(labels)] += 1
    per_class = []
    for i, label in enumerate(labels):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(len(labels))) - tp
        fn = sum(confusion[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({"label": label, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
                          "support": sum(confusion[i])})
    supported = [c for c in per_class if c["support"]]
    correct = sum(confusion[i][i] for i in range(len(labels)))
    return {
        "samples": len(pairs),
        "accuracy": round(correct / len(pairs), 4) if pairs else None,
        "macro_f1": round(sum(c["f1"] for c in supported) / len(supported), 4) if supported else None,
        "per_class": per_class,
        "confusion_columns": cols,
        "confusion": confusion,
    }


def run(test_dir: Path) -> dict:
    adapter = get_adapter()
    images = list_images(test_dir)
    pairs, errors = [], []
    for true, files in images.items():
        for f in files:
            try:
                pred = adapter.predict(f.read_bytes())
            except ValueError:
                errors.append({"file": str(f), "true": true, "pred": "(unreadable)", "score": None})
                continue
            label = pred.top["label"] if pred.top else "(none)"
            pairs.append((true, label))
            if label != true:
                errors.append({"file": str(f.relative_to(test_dir)), "true": true, "pred": label,
                               "score": pred.top["score"] if pred.top else None})
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "adapter": active_adapter_info(),
        "test_dir": str(test_dir),
        "labels": list(VISION_LABELS),
        **metrics(pairs, list(VISION_LABELS)),
        "errors": errors[:500],
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, required=True, help="Test split folder with one sub-folder per label")
    args = p.parse_args()
    report = run(args.data)
    if not report["samples"]:
        raise SystemExit(f"No test images found under {args.data}. Nothing was evaluated and no report was written.")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    with CONFUSION_PATH.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["true \\ predicted", *report["confusion_columns"]])
        for label, row in zip(report["labels"], report["confusion"], strict=True):
            w.writerow([label, *row])
    print(f"{report['adapter']['name']}: accuracy={report['accuracy']} macro_f1={report['macro_f1']} on {report['samples']} images")
    print(f"wrote {REPORT_PATH} and {CONFUSION_PATH}")


if __name__ == "__main__":
    main()
