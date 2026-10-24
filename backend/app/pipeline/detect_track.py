"""
Runs YOLO detection + ByteTrack tracking over a video, sampled at a fixed FPS
to keep runtime reasonable on CPU-only machines.

Yields one record per sampled frame:
{
  "frame_idx": int,        # index in the ORIGINAL video
  "t": float,               # seconds from video start
  "people": [{"track_id": int, "box": [x1,y1,x2,y2], "conf": float}, ...],
  "balls":  [{"box": [x1,y1,x2,y2], "conf": float}, ...],
}
Boxes are in pixel coordinates of the (resized) frame that was actually run
through the model — callers get back the resize scale to map to original px.
"""
from collections.abc import Iterator

import cv2
from ultralytics import YOLO

from app.config import YOLO_WEIGHTS, SAMPLE_FPS, FRAME_WIDTH, PERSON_CLASS, BALL_CLASS


def _jersey_color(frame, box_xyxy) -> list[float] | None:
    """Mean BGR color of a player's torso region, with pitch-green pixels masked out."""
    x1, y1, x2, y2 = [int(v) for v in box_xyxy]
    h, w = frame.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None

    box_h = y2 - y1
    torso_y1 = y1 + int(box_h * 0.15)
    torso_y2 = y1 + int(box_h * 0.55)
    crop = frame[torso_y1:torso_y2, x1:x2]
    if crop.size == 0:
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    keep = cv2.bitwise_not(green_mask)
    pixels = crop[keep > 0]
    if pixels.size == 0:
        pixels = crop.reshape(-1, 3)
    return pixels.mean(axis=0).tolist()


def track_video(video_path: str, progress_cb=None) -> Iterator[dict]:
    model = YOLO(YOLO_WEIGHTS)

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

        result = model.track(
            resized,
            persist=True,
            classes=[PERSON_CLASS, BALL_CLASS],
            tracker="bytetrack.yaml",
            verbose=False,
        )[0]

        people, balls = [], []
        if result.boxes is not None:
            for box in result.boxes:
                cls = int(box.cls[0])
                xyxy = [float(v) / scale for v in box.xyxy[0].tolist()]  # back to original px
                conf = float(box.conf[0])
                if cls == PERSON_CLASS:
                    tid = int(box.id[0]) if box.id is not None else -1
                    color = _jersey_color(frame, xyxy)
                    people.append({"track_id": tid, "box": xyxy, "conf": conf, "color": color})
                elif cls == BALL_CLASS:
                    balls.append({"box": xyxy, "conf": conf})

        yield {
            "frame_idx": frame_idx,
            "t": frame_idx / src_fps,
            "people": people,
            "balls": balls,
        }

        if progress_cb and total_frames:
            progress_cb(min(1.0, frame_idx / total_frames))

    cap.release()
