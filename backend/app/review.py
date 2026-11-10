"""
Renders one sampled frame with what the pipeline saw drawn on top — people
by role/team, the chosen ball and its state — so a user can check the
automatic ball states against the actual video.
"""
from functools import lru_cache

import cv2

from app import storage

STATE_COLORS_BGR = {
    "keeper": (0, 165, 255),
    "ground": (80, 200, 80),
    "air": (255, 160, 60),
    "out": (60, 60, 230),
    "unknown": (160, 160, 160),
}
STATE_TEXT = {
    "keeper": "KEEPER HAS THE BALL",
    "ground": "IN PLAY - ON THE GROUND",
    "air": "IN PLAY - IN THE AIR",
    "out": "OUT OF PLAY",
    "unknown": "BALL NOT FOUND",
}
_MAX_WIDTH = 1280


@lru_cache(maxsize=4)
def _frames(match_id: str, mtime: float) -> list[dict]:
    return storage.load_frames(match_id)["frames"]


def _hex_to_bgr(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def render_frame(match_id: str, i: int) -> bytes | None:
    fp = storage.frames_path(match_id)
    results = storage.load_results(match_id)
    if not fp.exists() or results is None:
        return None
    frames = _frames(match_id, fp.stat().st_mtime)
    if not 0 <= i < len(frames):
        return None
    f = frames[i]

    cap = cv2.VideoCapture(str(storage.video_path(match_id)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f["frame_idx"])
    ok, img = cap.read()
    cap.release()
    if not ok:
        return None

    roles = results.get("roles", {})
    colors = {t: _hex_to_bgr(c) for t, c in results.get("team_colors", {}).items()}
    thick = max(2, img.shape[1] // 640)
    for p in f["people"]:
        r = roles.get(str(p["track_id"]), {"role": "other", "team": None})
        x1, y1, x2, y2 = (int(v) for v in p["box"])
        color = colors.get(r["team"], (200, 200, 200)) if r["role"] != "other" else (120, 120, 120)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
        label = f"GK {p['track_id']}" if r["role"] == "goalkeeper" else str(p["track_id"])
        cv2.putText(img, label, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * thick, color, thick)

    b = results["ball_track"][i] if i < len(results["ball_track"]) else None
    state = b["state"] if b else "unknown"
    sc = STATE_COLORS_BGR[state]
    for cand in f["balls"]:  # every candidate the detector proposed, faint
        x1, y1, x2, y2 = (int(v) for v in cand["box"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (180, 180, 180), 1)
    if b and b.get("box"):
        x1, y1, x2, y2 = (int(v) for v in b["box"])
        cx, cy, rad = (x1 + x2) // 2, (y1 + y2) // 2, max(8, (x2 - x1)) + 6
        cv2.circle(img, (cx, cy), rad, sc, thick + 1)

    text = STATE_TEXT[state] + ("  (inferred: ball not visible)" if b and b["src"] == "inferred" else "")
    t = f["t"]
    banner = f"{int(t // 60)}:{int(t % 60):02d}  {text}"
    (tw, th), _ = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * thick / 2, thick)
    cv2.rectangle(img, (0, 0), (tw + 20, th + 20), (0, 0, 0), -1)
    cv2.putText(img, banner, (10, th + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * thick / 2, sc, thick)

    if img.shape[1] > _MAX_WIDTH:
        s = _MAX_WIDTH / img.shape[1]
        img = cv2.resize(img, (_MAX_WIDTH, int(img.shape[0] * s)))
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return jpg.tobytes() if ok else None
