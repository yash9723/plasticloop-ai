"""Dataset conventions and a reproducible stratified split.

Layout (one folder per label from VISION_LABELS):

    data/vision/raw/<label>/*.jpg          your labelled photos (collect locally; none are shipped)
    data/vision/{train,val,test}/<label>/   produced by:  python -m app.ai.dataset split --raw data/vision/raw --out data/vision

The split is stratified per label and seeded, so re-running it gives the same files in each split.
"""

import argparse
import random
import shutil
from pathlib import Path

from app.models.enums import VISION_LABELS

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def list_images(root: Path) -> dict[str, list[Path]]:
    return {label: sorted(p for p in (root / label).glob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
            for label in VISION_LABELS if (root / label).is_dir()}


def split(raw: Path, out: Path, seed: int = 42, ratios: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> dict[str, dict[str, int]]:
    if abs(sum(ratios) - 1) > 1e-6:
        raise ValueError("ratios must sum to 1")
    rng = random.Random(seed)
    counts: dict[str, dict[str, int]] = {}
    for label, files in list_images(raw).items():
        files = files[:]
        rng.shuffle(files)
        n = len(files)
        n_train = round(n * ratios[0])
        n_val = round(n * ratios[1]) if n - n_train > 1 else 0
        parts = {"train": files[:n_train], "val": files[n_train:n_train + n_val], "test": files[n_train + n_val:]}
        counts[label] = {}
        for name, items in parts.items():
            dest = out / name / label
            dest.mkdir(parents=True, exist_ok=True)
            for f in items:
                shutil.copy2(f, dest / f.name)
            counts[label][name] = len(items)
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--raw", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    counts = split(args.raw, args.out, args.seed)
    if not counts:
        raise SystemExit(f"No labelled images found under {args.raw} (expected sub-folders named {', '.join(VISION_LABELS)})")
    for label, c in counts.items():
        print(f"{label:<32} train={c['train']:<4} val={c['val']:<4} test={c['test']}")


if __name__ == "__main__":
    main()
