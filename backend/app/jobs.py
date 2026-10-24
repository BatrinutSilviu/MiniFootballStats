import threading
import traceback

from app import storage
from app.pipeline.pipeline import process_match


def start_processing(match_id: str) -> None:
    thread = threading.Thread(target=_run, args=(match_id,), daemon=True)
    thread.start()


def _run(match_id: str) -> None:
    meta = storage.load_meta(match_id)
    meta["status"] = "processing"
    meta["progress"] = 0.0
    meta.pop("error", None)
    storage.save_meta(match_id, meta)

    def progress_cb(p: float):
        m = storage.load_meta(match_id)
        m["progress"] = round(p, 3)
        storage.save_meta(match_id, m)

    try:
        process_match(match_id, progress_cb=progress_cb)
        meta = storage.load_meta(match_id)
        meta["status"] = "done"
        meta["progress"] = 1.0
        storage.save_meta(match_id, meta)
    except Exception as e:
        traceback.print_exc()
        meta = storage.load_meta(match_id)
        meta["status"] = "error"
        meta["error"] = str(e)
        storage.save_meta(match_id, meta)
