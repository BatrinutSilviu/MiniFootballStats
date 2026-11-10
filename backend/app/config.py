import os
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
FRAME_WIDTH = 960  # frames are resized to this width before inference (also used as the model's imgsz)

PERSON_CLASS = 0
BALL_CLASS = 32  # COCO "sports ball" — imperfect for a small fast ball, see BALL_WEIGHTS below
PERSON_MIN_CONF = 0.1  # low-score people still help the tracker's second association pass
BALL_MIN_CONF = 0.05  # keep weak ball candidates; the ball tracker filters them over time

# Optional dedicated ball detector (e.g. YOLO fine-tuned on a football dataset, see
# backend/tools/train_ball_model.py). When the file exists it replaces COCO's ball class.
BALL_WEIGHTS = MODELS_DIR / "ball.pt"
BALL_IMGSZ = 1280

DEFAULT_PITCH_LENGTH_M = 40.0  # typical mini-football / futsal court, editable per match at calibration time
DEFAULT_PITCH_WIDTH_M = 20.0
GOAL_WIDTH_M = 3.0
GOAL_AREA_DEPTH_M = 6.0  # zone in front of each goal where the keeper may handle the ball

# camera motion (moving / panning camera support)
CAMERA_WORK_WIDTH = 640  # frames are downscaled to this width for feature matching
CAMERA_MIN_INLIERS = 40  # fewer RANSAC inliers than this = registration failed for that frame
KEYFRAME_MIN_INLIERS = 150  # when matches to the keyframe drop below this, the frame becomes a new keyframe
PANORAMA_MAX_WIDTH = 2400

# player kinematics
MAX_PLAUSIBLE_SPEED_KMH = 36.0  # faster segments are tracking/projection noise, not real running

# ball tracking / possession / events heuristics
BALL_DIAMETER_M = 0.21  # size 4 futsal ball ~0.20 m, size 5 ~0.22 m
BALL_MAX_SPEED_MS = 35.0
# A ball that looks this much bigger than a ground ball at its projected spot is in the air.
# (It is closer to the camera than its ground projection, so it appears larger.)
AIR_SIZE_RATIO = 1.3
OUT_MARGIN_M = 0.5  # the whole ball must cross the line; allows for corner-click error too
KEEPER_HOLD_MAX_S = 8.0  # a keeper hiding the ball against their body keeps "holding" it this long
BALL_MAX_INTERP_S = 1.5  # gaps in ball detection up to this long are linearly interpolated
BALL_POSSESSION_RADIUS_M = 2.0  # a player within this distance of the ball is considered "in possession"
POSSESSION_MAX_BALL_SPEED_MS = 7.0  # a ball flying past faster than this is not under anyone's control
SHOT_MIN_SPEED_MS = 9.0
SHOT_MAX_DIST_M = 20.0  # shots are only considered from within this distance of the goal
SHOT_OUTCOME_WINDOW_S = 3.0

# shareable clips: text burned into the corner of every exported clip / highlight reel.
# Set CLIP_WATERMARK="" to remove it (e.g. as a paid-plan perk).
CLIP_WATERMARK = os.environ.get("CLIP_WATERMARK", "minifootball stats")

# optional Claude-written coaching report (only enabled when an API key is present)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
COACH_MODEL = os.environ.get("COACH_MODEL", "claude-opus-5-5")
