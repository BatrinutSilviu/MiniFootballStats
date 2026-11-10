"""
Fine-tunes a small YOLO model to detect the ball, which COCO's generic
"sports ball" class does poorly on small, fast, blurred match footage.

1. Download a football ball dataset in "YOLOv8" format, e.g. from Roboflow
   Universe (search "football ball detection"; free account), and unzip it.
   Labeling ~200 frames of your own pitch with Roboflow/CVAT and adding them
   helps a lot, since lighting, ball color and camera height vary per venue.
2. Train (a free Colab/Kaggle GPU takes well under an hour; CPU works but is slow):

       .venv/bin/python tools/train_ball_model.py path/to/dataset/data.yaml --epochs 60

3. The best weights are copied to backend/models/ball.pt, which the pipeline
   picks up automatically on the next video (only classes named "*ball*" are used).
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultralytics import YOLO  # noqa: E402

from app.config import BALL_IMGSZ, BALL_WEIGHTS, MODELS_DIR  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", help="dataset data.yaml (YOLO format)")
    ap.add_argument("--base", default="yolov8s.pt", help="starting weights (yolov8n.pt is faster, yolov8s.pt more accurate)")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=BALL_IMGSZ)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default=None, help="e.g. 0 for the first GPU, cpu for CPU")
    args = ap.parse_args()

    model = YOLO(str(MODELS_DIR / args.base) if (MODELS_DIR / args.base).exists() else args.base)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(MODELS_DIR / "runs"),
        name="ball",
        exist_ok=True,
        mosaic=1.0,
        close_mosaic=10,
    )
    best = MODELS_DIR / "runs" / "ball" / "weights" / "best.pt"
    shutil.copy(best, BALL_WEIGHTS)
    print(f"saved {BALL_WEIGHTS}")


if __name__ == "__main__":
    main()
