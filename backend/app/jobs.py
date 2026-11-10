import threading
import traceback

from app import storage
from app.pipeline.pipeline import analyze_video, compute_results

# Video analysis is CPU-heavy; running several at once just makes all of them slow.
_analysis_slot = threading.Semaphore(1)

ACTIVE_STATUSES = ("queued", "analyzing", "computing")


def start_analysis(match_id: str) -> None:
    storage.update_meta(match_id, status="queued", progress=0.0, error=None)
    threading.Thread(target=_run_analysis, args=(match_id,), daemon=True).start()


def start_compute(match_id: str) -> None:
    storage.update_meta(match_id, status="computing", error=None)
    threading.Thread(target=_run_compute, args=(match_id,), daemon=True).start()


def compute_now(match_id: str) -> None:
    """Synchronous recompute (a few seconds), used after the user corrects the analysis."""
    storage.update_meta(match_id, status="computing", error=None)
    try:
        compute_results(match_id)
        storage.update_meta(match_id, status="done")
    except Exception as e:
        traceback.print_exc()
        storage.update_meta(match_id, status="error", error=str(e))
        raise


def mark_interrupted() -> None:
    """Jobs run in-process; after a restart any active job is gone for good."""
    for m in storage.list_matches():
        if m.get("status") in ACTIVE_STATUSES:
            storage.update_meta(m["id"], status="error", error="interrupted by a server restart — press retry")
        if (m.get("highlights") or {}).get("status") == "rendering":
            storage.update_meta(m["id"], highlights={"status": "error", "error": "interrupted by a server restart"})


def _run_analysis(match_id: str) -> None:
    with _analysis_slot:
        storage.update_meta(match_id, status="analyzing", progress=0.0)
        try:
            analyze_video(match_id, progress_cb=lambda p: storage.update_meta(match_id, progress=round(p, 3)))
            storage.update_meta(match_id, status="awaiting_calibration", progress=1.0)
        except Exception as e:
            traceback.print_exc()
            storage.update_meta(match_id, status="error", error=str(e))


def _run_compute(match_id: str) -> None:
    try:
        compute_results(match_id)
        storage.update_meta(match_id, status="done")
    except Exception as e:
        traceback.print_exc()
        storage.update_meta(match_id, status="error", error=str(e))
