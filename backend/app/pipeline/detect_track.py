"""
Runs YOLO detection + BoT-SORT tracking + camera-motion estimation over a
video, sampled at a fixed FPS to keep runtime reasonable on CPU-only machines.

One YOLO pass per sampled frame produces both people and ball candidates.
People go through BoT-SORT (whose global motion compensation keeps IDs stable
while the camera pans); ball candidates are kept even at low confidence and
filtered later by the ball tracker (ball.py), once roles and the pitch are known.

Produces one record per sampled frame:
{
  "frame_idx": int,         # index in the ORIGINAL video
  "t": float,               # seconds from video start
  "H": 3x3 | None,          # frame px -> mosaic px (None = camera registration failed)
  "people": [{"track_id": int, "box": [x1,y1,x2,y2], "conf": float, "color": [L,a,b] | None}, ...],
  "balls":  [{"box": [x1,y1,x2,y2], "conf": float}, ...],
}
Boxes are in ORIGINAL video pixel coordinates.
"""
from collections.abc import Iterator

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.trackers.bot_sort import BOTSORT
from ultralytics.utils import IterableSimpleNamespace, yaml_load
from ultralytics.utils.checks import check_yaml

from app.config import (
    YOLO_WEIGHTS,
    SAMPLE_FPS,
    FRAME_WIDTH,
    PERSON_CLASS,
    BALL_CLASS,
    PERSON_MIN_CONF,
    BALL_MIN_CONF,
    BALL_WEIGHTS,
    BALL_IMGSZ,
)
from app.pipeline.camera import CameraTracker


def _jersey_color(frame, box_xyxy) -> list[float] | None:
    """Mean Lab color of a player's torso region, with pitch-green pixels masked out.
    Lab makes euclidean distances roughly match perceived color differences."""
    x1, y1, x2, y2 = [int(v) for v in box_xyxy]
    h, w = frame.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None

    box_h, box_w = y2 - y1, x2 - x1
    torso_y1 = y1 + int(box_h * 0.15)
    torso_y2 = y1 + int(box_h * 0.55)
    torso_x1 = x1 + int(box_w * 0.2)
    torso_x2 = x2 - int(box_w * 0.2)
    crop = frame[torso_y1:torso_y2, torso_x1:torso_x2]
    if crop.size == 0:
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    keep = cv2.bitwise_not(green_mask)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    pixels = lab[keep > 0]
    if len(pixels) < 10:
        pixels = lab.reshape(-1, 3)
    return np.median(pixels, axis=0).astype(float).tolist()


def _make_tracker() -> BOTSORT:
    cfg = IterableSimpleNamespace(**yaml_load(check_yaml("botsort.yaml")))
    return BOTSORT(args=cfg, frame_rate=30)


def track_video(video_path: str, camera: CameraTracker, progress_cb=None) -> Iterator[dict]:
    model = YOLO(YOLO_WEIGHTS)
    ball_model = YOLO(str(BALL_WEIGHTS)) if BALL_WEIGHTS.exists() else None
    # football datasets often also label players/referees; only use the ball class(es)
    ball_classes = None
    if ball_model:
        ball_classes = [k for k, v in ball_model.names.items() if "ball" in v.lower()] or None
    tracker = _make_tracker()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_step = max(1, round(src_fps / SAMPLE_FPS))

    frame_idx = -1
    while True:
        ok = cap.grab()
        if not ok:
            break
        frame_idx += 1
        if frame_idx % frame_step != 0:
            continue
        ok, frame = cap.retrieve()
        if not ok:
            break

        h, w = frame.shape[:2]
        scale = FRAME_WIDTH / w
        resized = cv2.resize(frame, (FRAME_WIDTH, int(h * scale)))

        classes = [PERSON_CLASS] if ball_model else [PERSON_CLASS, BALL_CLASS]
        result = model.predict(
            resized, classes=classes, conf=min(PERSON_MIN_CONF, BALL_MIN_CONF), imgsz=FRAME_WIDTH, verbose=False
        )[0]
        boxes = result.boxes.cpu().numpy()

        person_mask = (boxes.cls == PERSON_CLASS) & (boxes.conf >= PERSON_MIN_CONF)
        person_dets = boxes[person_mask]
        tracks = tracker.update(person_dets, resized)  # called on empty frames too, so lost tracks age out

        people = []
        for x1, y1, x2, y2, tid, conf, _cls, _idx in tracks:
            xyxy = [float(v) / scale for v in (x1, y1, x2, y2)]  # back to original px
            people.append(
                {"track_id": int(tid), "box": xyxy, "conf": float(conf), "color": _jersey_color(frame, xyxy)}
            )

        if ball_model:
            bres = ball_model.predict(
                resized, classes=ball_classes, conf=BALL_MIN_CONF, imgsz=BALL_IMGSZ, verbose=False
            )[0]
            ball_boxes = bres.boxes.cpu().numpy()
        else:
            ball_boxes = boxes[(boxes.cls == BALL_CLASS) & (boxes.conf >= BALL_MIN_CONF)]
        all_person_px = [[float(v) / scale for v in b] for b in person_dets.xyxy]
        # every candidate is kept, even on heads: whether a ball "on a head" is a
        # bald head or a keeper holding the ball up is decided later, once roles are known
        balls = [
            {"box": [float(v) / scale for v in xyxy], "conf": float(conf)}
            for xyxy, conf in zip(ball_boxes.xyxy, ball_boxes.conf)
        ]

        H = camera.update(frame, all_person_px)

        yield {
            "frame_idx": frame_idx,
            "t": frame_idx / src_fps,
            "H": H,
            "people": people,
            "balls": balls,
        }

        if progress_cb and total_frames:
            progress_cb(min(1.0, frame_idx / total_frames))

    cap.release()
