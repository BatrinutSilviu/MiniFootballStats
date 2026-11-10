import gzip
import shutil
import json
import re
import threading
import uuid
from datetime import datetime, timezone

from app.config import MATCHES_DIR

_meta_lock = threading.Lock()


def new_match_id() -> str:
    return uuid.uuid4().hex[:12]


_ID_RE = re.compile(r"^[0-9a-z_]{1,64}$")


def match_dir(match_id: str, create: bool = False):
    if not _ID_RE.match(match_id):
        raise KeyError(f"invalid match id: {match_id!r}")
    d = MATCHES_DIR / match_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def meta_path(match_id: str):
    return match_dir(match_id) / "meta.json"


def results_path(match_id: str):
    return match_dir(match_id) / "results.json"


def frames_path(match_id: str):
    return match_dir(match_id) / "frames.json.gz"


def video_path(match_id: str, suffix: str | None = None):
    if suffix is None:
        meta = load_meta(match_id) or {}
        suffix = meta.get("video_suffix", ".mp4")
    return match_dir(match_id, create=True) / f"video{suffix}"


def panorama_path(match_id: str):
    return match_dir(match_id) / "panorama.jpg"


def _write_json_atomic(path, data, compress=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    raw = json.dumps(data, indent=None if compress else 2).encode()
    tmp.write_bytes(gzip.compress(raw) if compress else raw)
    tmp.replace(path)


def save_meta(match_id: str, meta: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    _write_json_atomic(meta_path(match_id), meta)


def load_meta(match_id: str) -> dict | None:
    try:
        p = meta_path(match_id)
    except KeyError:
        return None
    if not p.exists():
        return None
    return json.loads(p.read_text())


def update_meta(match_id: str, **fields) -> dict:
    """Atomic read-modify-write, safe to call from the worker thread and request handlers."""
    with _meta_lock:
        meta = load_meta(match_id) or {}
        for k, v in fields.items():
            if v is None:
                meta.pop(k, None)
            else:
                meta[k] = v
        save_meta(match_id, meta)
        return meta


def save_results(match_id: str, results: dict) -> None:
    _write_json_atomic(results_path(match_id), results)


def load_results(match_id: str) -> dict | None:
    p = results_path(match_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save_frames(match_id: str, frames: dict) -> None:
    _write_json_atomic(frames_path(match_id), frames, compress=True)


def load_frames(match_id: str) -> dict | None:
    p = frames_path(match_id)
    if not p.exists():
        return None
    return json.loads(gzip.decompress(p.read_bytes()))


def delete_match(match_id: str) -> None:
    """Removes the video and everything derived from it (privacy: nothing is kept)."""
    d = match_dir(match_id)
    if d.exists():
        shutil.rmtree(d)


def list_matches() -> list[dict]:
    out = []
    if not MATCHES_DIR.exists():
        return out
    for d in MATCHES_DIR.iterdir():
        if not d.is_dir():
            continue
        m = load_meta(d.name)
        if m:
            out.append({"id": d.name, **m})
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out
