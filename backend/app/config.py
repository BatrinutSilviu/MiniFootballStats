from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
MATCHES_DIR = DATA_DIR / "matches"
MODELS_DIR = BACKEND_DIR / "models"

MATCHES_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# CPU-friendly defaults. Bump SAMPLE_FPS / FRAME_WIDTH up if a GPU is available.
YOLO_WEIGHTS = str(MODELS_DIR / "yolov8n.pt")  # auto-downloaded by ultralytics on first use, free/open weights
SAMPLE_FPS = 4  # how many frames per second of source video we actually run detection on
FRAME_WIDTH = 960  # frames are resized to this width before inference

PERSON_CLASS = 0
BALL_CLASS = 32  # COCO "sports ball" — imperfect for a fast-moving mini-football, flagged in README

DEFAULT_PITCH_LENGTH_M = 40.0  # typical mini-football / futsal court, editable per match at calibration time
DEFAULT_PITCH_WIDTH_M = 20.0

# possession / passing heuristics
BALL_POSSESSION_RADIUS_M = 2.0  # a player within this distance of the ball is considered "in possession"
MAX_PLAYER_JUMP_M = 3.0  # per-sample-frame; larger deltas are treated as tracking noise and clipped
