"""
Shareable video clips of key moments, and a highlight reel of the match.

Clips are cut from the original video at its full frame rate, with a banner
(what happened, the score, the clock) and a watermark. The "vertical" format
is a 9:16 crop that follows the ball, ready for Instagram / TikTok stories;
"wide" keeps the original framing.

Encoding goes through ffmpeg (H.264 + AAC, playable in every browser and
phone). Rendered files are cached per match and thrown away when the stats
are recomputed.
"""
import hashlib
import shutil
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app import storage
from app.config import CLIP_WATERMARK

FORMATS = ("vertical", "wide")
CLIP_BEFORE_S = 5.0
CLIP_AFTER_S = 3.0
REEL_MAX_S = 120.0
_OUT_SIZE = {"vertical": (720, 1280), "wide": (1280, 720)}
_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)
_reel_lock = threading.Lock()

EVENT_TITLES = {"goal": "GOAL!", "saved": "SAVE", "blocked": "BLOCKED SHOT", "off_target": "SHOT", "unknown": "SHOT ON TARGET"}


class ClipError(RuntimeError):
    pass


def ffmpeg_binary() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def clips_available() -> bool:
    return ffmpeg_binary() is not None


# ---------------------------------------------------------------- labels

def _results_version(match_id: str) -> str:
    p = storage.results_path(match_id)
    return str(int(p.stat().st_mtime)) if p.exists() else "0"


def team_label(meta: dict, team: str | None) -> str:
    names = meta.get("team_names") or {}
    default = {"team_a": "Team A", "team_b": "Team B"}
    return names.get(team) or default.get(team, "")


def player_label(meta: dict, tid) -> str | None:
    if tid is None:
        return None
    p = (meta.get("player_names") or {}).get(str(tid))
    if not p or not p.get("name"):
        return None
    return f"{p['name']}" + (f" #{p['number']}" if p.get("number") is not None else "")


def score_at(events: list[dict], t: float) -> dict:
    s = {"team_a": 0, "team_b": 0}
    for e in events:
        if e["type"] == "shot" and e["outcome"] == "goal" and e["t"] <= t + 1e-6 and e.get("team") in s:
            s[e["team"]] += 1
    return s


def _clock(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def describe_moment(meta: dict, results: dict, t: float) -> tuple[str, str]:
    """(headline, sub-line) for the banner of a clip centered at t."""
    events = results["events"]
    near = [e for e in events if abs(e["t"] - t) <= 0.6 and e["type"] in ("shot", "keeper_handling", "out")]
    e = min(near, key=lambda e: (e["type"] != "shot", abs(e["t"] - t)), default=None)
    sc = score_at(events, t)
    score = f"{team_label(meta, 'team_a')} {sc['team_a']}-{sc['team_b']} {team_label(meta, 'team_b')}"
    if e is None:
        return "HIGHLIGHT", f"{score}  ·  {_clock(t)}"
    if e["type"] == "shot":
        title = EVENT_TITLES.get(e["outcome"], "SHOT")
        who = player_label(meta, e.get("shooter")) or team_label(meta, e.get("team"))
        head = f"{title}  {who}".strip()
    elif e["type"] == "keeper_handling":
        head = ("SAVE  " if e["save"] else "KEEPER  ") + (player_label(meta, e.get("keeper")) or team_label(meta, e.get("team")))
    else:
        head = "BALL OUT"
    return head, f"{score}  ·  {_clock(t)}"


# ---------------------------------------------------------------- drawing

@lru_cache(maxsize=8)
def _font(size: int):
    for p in _FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _overlay(w: int, h: int, head: str, sub: str) -> tuple[np.ndarray, np.ndarray]:
    """Pre-rendered RGBA banner + watermark: (bgr, alpha 0..1) arrays the size of the output frame."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    unit = min(w, h) / 720
    fh, fs, fw = _font(int(44 * unit)), _font(int(26 * unit)), _font(int(22 * unit))
    pad = int(18 * unit)
    top = int(h * 0.06) if h > w else pad
    hb = d.textbbox((0, 0), head, font=fh)
    sb = d.textbbox((0, 0), sub, font=fs)
    bw = max(hb[2], sb[2]) + 2 * pad
    bh = (hb[3] - hb[1]) + (sb[3] - sb[1]) + 3 * pad
    x0 = (w - bw) // 2
    d.rounded_rectangle((x0, top, x0 + bw, top + bh), radius=int(14 * unit), fill=(10, 20, 30, 200))
    d.rectangle((x0, top, x0 + int(8 * unit), top + bh), fill=(79, 179, 255, 255))
    d.text((x0 + pad, top + pad - hb[1]), head, font=fh, fill=(255, 255, 255, 255))
    d.text((x0 + pad, top + 2 * pad + (hb[3] - hb[1]) - sb[1]), sub, font=fs, fill=(200, 225, 240, 255))
    if CLIP_WATERMARK:
        wb = d.textbbox((0, 0), CLIP_WATERMARK, font=fw)
        d.text((w - wb[2] - pad, h - wb[3] - pad), CLIP_WATERMARK, font=fw, fill=(255, 255, 255, 170))
    arr = np.asarray(img).astype(np.float32)
    bgr = arr[:, :, 2::-1]
    alpha = arr[:, :, 3:4] / 255.0
    return bgr, alpha


def _ball_centers(results: dict, frames_t: list[float], width: int) -> np.ndarray:
    """Smoothed ball x position (original px) for every output frame time, for the vertical crop."""
    pts = [(b["t"], (b["box"][0] + b["box"][2]) / 2) for b in results["ball_track"] if b and b.get("box")]
    if not pts:
        return np.full(len(frames_t), width / 2)
    ts, xs = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    raw = np.interp(frames_t, ts, xs)
    out, cur = np.empty_like(raw), raw[0]
    for i, x in enumerate(raw):  # exponential smoothing: no jitter, follows the ball within ~0.5 s
        cur += (x - cur) * 0.08
        out[i] = cur
    return out


# ---------------------------------------------------------------- encoding

def _render_segment(match_id: str, meta: dict, results: dict, t: float, fmt: str, out_path: Path) -> None:
    exe = ffmpeg_binary()
    if exe is None:
        raise ClipError("ffmpeg is not installed (install it, or `pip install imageio-ffmpeg`)")
    src = str(storage.video_path(match_id))
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise ClipError("could not open the match video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    vw, vh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 10**9
    f0, f1 = max(0, int((t - CLIP_BEFORE_S) * fps)), min(total - 1, int((t + CLIP_AFTER_S) * fps))
    if f1 <= f0:
        cap.release()
        raise ClipError("this moment is outside the video")

    ow, oh = _OUT_SIZE[fmt]
    if fmt == "wide":  # keep the aspect ratio of the source, fit to 1280 wide
        ow, oh = min(1280, vw - vw % 2), int(min(1280, vw) * vh / vw) // 2 * 2
    crop_w = min(vw, int(vh * ow / oh))
    head, sub = describe_moment(meta, results, t)
    obgr, oalpha = _overlay(ow, oh, head, sub)
    centers = _ball_centers(results, [(f0 + k) / fps for k in range(f1 - f0 + 1)], vw)

    cmd = [
        exe, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}", "-r", f"{fps:.3f}", "-i", "-",
        "-ss", f"{f0 / fps:.3f}", "-t", f"{(f1 - f0 + 1) / fps:.3f}", "-i", src,
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
        for k in range(f1 - f0 + 1):
            ok, frame = cap.read()
            if not ok:
                break
            if crop_w < vw:
                x0 = int(np.clip(centers[k] - crop_w / 2, 0, vw - crop_w))
                frame = frame[:, x0:x0 + crop_w]
            frame = cv2.resize(frame, (ow, oh), interpolation=cv2.INTER_AREA)
            frame = (frame * (1 - oalpha) + obgr * oalpha).astype(np.uint8)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise ClipError(f"ffmpeg failed: {err[-500:]}")
    except BrokenPipeError:
        proc.wait()
        raise ClipError(f"ffmpeg failed: {proc.stderr.read().decode(errors='replace')[-500:]}")
    finally:
        cap.release()


def _clips_dir(match_id: str, version: str) -> Path:
    d = storage.match_dir(match_id) / "clips"
    d.mkdir(exist_ok=True)
    for old in d.iterdir():  # clips of earlier stats carry outdated scores / labels
        if not old.name.startswith(f"v{version}_"):
            old.unlink(missing_ok=True)
    return d


def render_clip(match_id: str, t: float, fmt: str) -> Path:
    if fmt not in FORMATS:
        raise ClipError(f"format must be one of {FORMATS}")
    meta, results = storage.load_meta(match_id), storage.load_results(match_id)
    if meta is None or results is None:
        raise ClipError("results not ready")
    version = _results_version(match_id)
    names_tag = hashlib.sha1(repr((meta.get("team_names"), meta.get("player_names"), CLIP_WATERMARK)).encode()).hexdigest()[:8]
    out = _clips_dir(match_id, version) / f"v{version}_{fmt}_{int(t * 100)}_{names_tag}.mp4"
    if not out.exists():
        tmp = out.with_suffix(".tmp.mp4")
        _render_segment(match_id, meta, results, t, fmt, tmp)
        tmp.replace(out)
    return out


# ---------------------------------------------------------------- highlight reel

def reel_moments(results: dict) -> list[float]:
    """Times of the moments worth showing, best first, within REEL_MAX_S of total footage."""
    def priority(e):
        if e["type"] == "shot":
            return {"goal": 0, "saved": 1, "unknown": 2, "blocked": 3, "off_target": 4}.get(e["outcome"], 5)
        if e["type"] == "keeper_handling" and e["save"]:
            return 1
        return None

    cands = [(priority(e), e["t"]) for e in results["events"]]
    cands = sorted((p, t) for p, t in cands if p is not None)
    chosen, budget = [], REEL_MAX_S
    for _, t in cands:
        if budget < CLIP_BEFORE_S + CLIP_AFTER_S:
            break
        if any(abs(t - c) < CLIP_BEFORE_S + CLIP_AFTER_S for c in chosen):
            continue  # overlaps a moment already in the reel (a save right after a shot)
        chosen.append(t)
        budget -= CLIP_BEFORE_S + CLIP_AFTER_S
    return sorted(chosen)


def reel_path(match_id: str, fmt: str) -> Path:
    return storage.match_dir(match_id) / f"highlights_{fmt}.mp4"


def start_reel(match_id: str, fmt: str) -> None:
    if fmt not in FORMATS:
        raise ClipError(f"format must be one of {FORMATS}")
    storage.update_meta(match_id, highlights={"status": "rendering", "format": fmt, "progress": 0.0})
    threading.Thread(target=_build_reel, args=(match_id, fmt), daemon=True).start()


def _build_reel(match_id: str, fmt: str) -> None:
    with _reel_lock:
        try:
            results = storage.load_results(match_id)
            moments = reel_moments(results)
            if not moments:
                raise ClipError("no shots, goals or saves were detected to put in a highlight reel")
            parts = []
            for k, t in enumerate(moments):
                parts.append(render_clip(match_id, t, fmt))
                storage.update_meta(match_id, highlights={"status": "rendering", "format": fmt, "progress": round((k + 1) / len(moments), 3)})
            lst = storage.match_dir(match_id) / "clips" / "reel.txt"
            lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
            out = reel_path(match_id, fmt)
            tmp = out.with_suffix(".tmp.mp4")
            r = subprocess.run(
                [ffmpeg_binary(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", "-movflags", "+faststart", str(tmp)],
                capture_output=True,
            )
            if r.returncode != 0:
                raise ClipError(f"ffmpeg failed: {r.stderr.decode(errors='replace')[-500:]}")
            tmp.replace(out)
            storage.update_meta(match_id, highlights={
                "status": "done", "format": fmt, "progress": 1.0, "moments": len(moments), "version": str(int(time.time())),
            })
        except Exception as e:
            storage.update_meta(match_id, highlights={"status": "error", "format": fmt, "error": str(e)})
