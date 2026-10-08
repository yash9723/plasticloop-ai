"""Optional: fine-tune a YOLO classification model on your own labelled photos.

    pip install ultralytics            # not in the default image (pulls PyTorch, ~1 GB)
    python -m app.ai.dataset split --raw data/vision/raw --out data/vision
    python -m app.ai.train_yolo --data data/vision --epochs 30
    python -m app.ai.evaluate --data data/vision/test

The base checkpoint (yolov8n-cls.pt) is downloaded by Ultralytics on first use. The trained weights are copied to
VISION_MODEL_PATH, where the API picks them up (VISION_MODE=auto). Report only the accuracy printed by app.ai.evaluate.
"""

import argparse
import importlib.util
import shutil
from pathlib import Path

from app.core.config import settings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, required=True, help="Folder containing train/ val/ test/ sub-folders")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--base", default="yolov8n-cls.pt")
    args = p.parse_args()
    if importlib.util.find_spec("ultralytics") is None:
        raise SystemExit("ultralytics is not installed: pip install ultralytics")
    if not (args.data / "train").is_dir() or not (args.data / "val").is_dir():
        raise SystemExit(f"Expected {args.data}/train and {args.data}/val (run app.ai.dataset split first)")
    from ultralytics import YOLO

    result = YOLO(args.base).train(data=str(args.data), epochs=args.epochs, imgsz=args.imgsz, seed=42, deterministic=True)
    best = Path(result.save_dir) / "weights" / "best.pt"
    settings.vision_model_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, settings.vision_model_path)
    print(f"copied {best} -> {settings.vision_model_path}. Now evaluate on the test split before quoting any accuracy.")


if __name__ == "__main__":
    main()
