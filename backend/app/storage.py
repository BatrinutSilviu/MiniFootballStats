import json
import uuid
from datetime import datetime, timezone

from app.config import MATCHES_DIR


def new_match_id() -> str:
    return uuid.uuid4().hex[:12]


def match_dir(match_id: str):
    d = MATCHES_DIR / match_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def meta_path(match_id: str):
    return match_dir(match_id) / "meta.json"


def results_path(match_id: str):
    return match_dir(match_id) / "results.json"


def video_path(match_id: str, suffix: str = ".mp4"):
    return match_dir(match_id) / f"video{suffix}"


def first_frame_path(match_id: str):
    return match_dir(match_id) / "first_frame.jpg"


def save_meta(match_id: str, meta: dict) -> None:
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta_path(match_id).write_text(json.dumps(meta, indent=2))


def load_meta(match_id: str) -> dict | None:
    p = meta_path(match_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save_results(match_id: str, results: dict) -> None:
    results_path(match_id).write_text(json.dumps(results, indent=2))


def load_results(match_id: str) -> dict | None:
    p = results_path(match_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_matches() -> list[dict]:
    out = []
    if not MATCHES_DIR.exists():
        return out
    for d in sorted(MATCHES_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        m = load_meta(d.name)
        if m:
            out.append({"id": d.name, **m})
    return out
