import shutil
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import cv2

from app import clips, edits, profiles, storage, jobs, review
from app.config import CLIP_WATERMARK, DEFAULT_PITCH_LENGTH_M, DEFAULT_PITCH_WIDTH_M
from app.pipeline.calibration import compute_homography
from app.pipeline.coach import coach_available, generate_coach_report
from app.pipeline.pitch_detect import suggest_corners


class CalibrationRequest(BaseModel):
    corners: list[list[float]]  # 4 panorama px points [x, y], in order TL, TR, BR, BL
    pitch_length_m: float = DEFAULT_PITCH_LENGTH_M
    pitch_width_m: float = DEFAULT_PITCH_WIDTH_M


class PlayerLabel(BaseModel):
    name: str = ""
    number: int | None = None


class LabelsRequest(BaseModel):
    title: str | None = None
    team_names: dict[str, str] | None = None
    player_names: dict[str, PlayerLabel] | None = None  # replaces all player labels when given


class EventEdits(BaseModel):
    removed: list[str] = []
    outcomes: dict[str, str] = {}
    added: list[dict] = []


class CorrectionsRequest(BaseModel):
    track_merges: dict[str, int] = {}
    event_edits: EventEdits = EventEdits()


class HighlightsRequest(BaseModel):
    format: str = "vertical"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    jobs.mark_interrupted()
    yield


app = FastAPI(title="Minifootball Stats", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    expose_headers=["Content-Disposition"],
    allow_headers=["*"],
)


@app.get("/api/features")
async def features():
    return {"coach_report": coach_available(), "clips": clips.clips_available(), "watermark": bool(CLIP_WATERMARK)}


@app.post("/api/matches")
async def create_match(video: UploadFile):
    match_id = storage.new_match_id()
    suffix = _suffix(video.filename)
    vpath = storage.video_path(match_id, suffix=suffix)
    with vpath.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    storage.save_meta(
        match_id,
        {
            "status": "queued",
            "video_filename": video.filename,
            "video_suffix": suffix,
            "pitch_length_m": DEFAULT_PITCH_LENGTH_M,
            "pitch_width_m": DEFAULT_PITCH_WIDTH_M,
        },
    )
    jobs.start_analysis(match_id)
    return {"match_id": match_id}


@app.get("/api/matches")
async def list_matches():
    return storage.list_matches()


@app.get("/api/matches/{match_id}")
async def get_match(match_id: str):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    return {"id": match_id, **_public(meta)}


@app.get("/api/matches/{match_id}/panorama")
async def get_panorama(match_id: str):
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    p = storage.panorama_path(match_id)
    if not p.exists():
        raise HTTPException(404, "panorama not ready")
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@app.post("/api/matches/{match_id}/calibrate")
async def calibrate_match(match_id: str, body: CalibrationRequest):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    if meta["status"] in jobs.ACTIVE_STATUSES:
        raise HTTPException(409, "match is still being processed")
    if not storage.frames_path(match_id).exists():
        raise HTTPException(409, "video has not been analyzed yet")
    if len(body.corners) != 4:
        raise HTTPException(400, "exactly 4 corner points are required (TL, TR, BR, BL)")

    try:
        h = compute_homography(body.corners, body.pitch_length_m, body.pitch_width_m)
    except ValueError as e:
        raise HTTPException(400, str(e))
    storage.update_meta(
        match_id,
        homography=h,
        corners=body.corners,
        pitch_length_m=body.pitch_length_m,
        pitch_width_m=body.pitch_width_m,
    )
    jobs.start_compute(match_id)
    return {"status": "computing"}


@app.post("/api/matches/{match_id}/retry")
async def retry_match(match_id: str):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    if meta["status"] in jobs.ACTIVE_STATUSES:
        raise HTTPException(409, "match is already being processed")
    if storage.frames_path(match_id).exists() and "homography" in meta:
        jobs.start_compute(match_id)
    else:
        jobs.start_analysis(match_id)
    return {"status": "ok"}


@app.get("/api/matches/{match_id}/results")
async def get_results(match_id: str):
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    results = storage.load_results(match_id)
    if results is None:
        raise HTTPException(404, "results not ready")
    meta = storage.load_meta(match_id)
    if "recording_tips" not in results and meta["status"] == "done" and storage.frames_path(match_id).exists():
        # computed by an older version: recompute once (seconds) to add per-player events, keys, tips
        try:
            await run_in_threadpool(jobs.compute_now, match_id)
            results, meta = storage.load_results(match_id), storage.load_meta(match_id)
        except Exception:
            pass  # fall back to the old results, filled in below
    for e in results.get("events", []):
        e.setdefault("key", edits.event_key(e))
    results.setdefault("removed_events", [])
    results.setdefault("recording_tips", [])
    return JSONResponse({**results, **_labels_and_corrections(meta)})


def _labels_and_corrections(meta: dict) -> dict:
    ev = meta.get("event_edits") or {}
    return {
        "labels": {
            "title": meta.get("title"),
            "team_names": meta.get("team_names") or {},
            "player_names": meta.get("player_names") or {},
        },
        "corrections": {
            "track_merges": meta.get("track_merges") or {},
            "event_edits": {"removed": ev.get("removed", []), "outcomes": ev.get("outcomes", {}), "added": ev.get("added", [])},
        },
    }


def _require_done(match_id: str) -> dict:
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    if meta["status"] in jobs.ACTIVE_STATUSES:
        raise HTTPException(409, "match is still being processed")
    if storage.load_results(match_id) is None:
        raise HTTPException(409, "results not ready")
    return meta


@app.patch("/api/matches/{match_id}/labels")
async def update_labels(match_id: str, body: LabelsRequest):
    """Names only — no recompute needed."""
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    fields = {}
    if body.title is not None:
        fields["title"] = body.title.strip()[:120] or None
    if body.team_names is not None:
        fields["team_names"] = {t: n.strip()[:40] for t, n in body.team_names.items() if t in ("team_a", "team_b") and n.strip()}
    if body.player_names is not None:
        fields["player_names"] = {
            tid: {"name": p.name.strip()[:40], "number": p.number}
            for tid, p in body.player_names.items()
            if tid.lstrip("-").isdigit() and (p.name.strip() or p.number is not None)
        }
    if fields:
        storage.update_meta(match_id, **fields)  # a None title removes it
    return _labels_and_corrections(storage.load_meta(match_id))["labels"]


@app.put("/api/matches/{match_id}/corrections")
async def update_corrections(match_id: str, body: CorrectionsRequest):
    """Track merges and event fixes; recomputes the stats and returns the new results."""
    meta = _require_done(match_id)
    try:
        added = [edits.validate_added_event(e) for e in body.event_edits.added]
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    if any(o not in edits.SHOT_OUTCOMES for o in body.event_edits.outcomes.values()):
        raise HTTPException(400, f"outcomes must be one of {edits.SHOT_OUTCOMES}")
    merges = {k: v for k, v in body.track_merges.items() if k.lstrip("-").isdigit() and int(k) != v}

    # a name given to a track that is now merged away moves to the track it was merged into
    names = dict(meta.get("player_names") or {})
    for src, dst in edits.resolve_merges(merges).items():
        if str(src) in names and str(dst) not in names:
            names[str(dst)] = names.pop(str(src))

    storage.update_meta(
        match_id,
        track_merges=merges,
        event_edits={"removed": body.event_edits.removed, "outcomes": body.event_edits.outcomes, "added": added},
        player_names=names,
    )
    try:
        await run_in_threadpool(jobs.compute_now, match_id)
    except Exception as e:
        raise HTTPException(500, f"recompute failed: {e}")
    return await get_results(match_id)


@app.get("/api/matches/{match_id}/suggested-corners")
async def suggested_corners(match_id: str):
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    p = storage.panorama_path(match_id)
    if not p.exists():
        raise HTTPException(404, "panorama not ready")
    img = await run_in_threadpool(cv2.imread, str(p))
    corners = await run_in_threadpool(suggest_corners, img) if img is not None else None
    return {"corners": corners}


@app.get("/api/matches/{match_id}/clip.mp4")
async def get_clip(match_id: str, t: float, format: str = "vertical", download: bool = False):
    _require_done(match_id)
    try:
        path = await run_in_threadpool(clips.render_clip, match_id, t, format)
    except clips.ClipError as e:
        raise HTTPException(400, str(e))
    name = f"moment-{int(t // 60)}m{int(t % 60):02d}s-{format}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@app.post("/api/matches/{match_id}/highlights")
async def create_highlights(match_id: str, body: HighlightsRequest):
    meta = _require_done(match_id)
    if (meta.get("highlights") or {}).get("status") == "rendering":
        raise HTTPException(409, "a highlight reel is already being rendered")
    if not clips.clips_available():
        raise HTTPException(503, "ffmpeg is not installed")
    try:
        clips.start_reel(match_id, body.format)
    except clips.ClipError as e:
        raise HTTPException(400, str(e))
    return storage.load_meta(match_id)["highlights"]


@app.get("/api/matches/{match_id}/highlights.mp4")
async def get_highlights(match_id: str, format: str = "vertical", download: bool = False):
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    if format not in clips.FORMATS:
        raise HTTPException(400, "unknown format")
    p = clips.reel_path(match_id, format)
    if not p.exists():
        raise HTTPException(404, "no highlight reel yet")
    return FileResponse(p, media_type="video/mp4", filename=f"highlights-{format}.mp4" if download else None,
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "no-cache"})


@app.delete("/api/matches/{match_id}")
async def delete_match(match_id: str):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    if meta["status"] in jobs.ACTIVE_STATUSES or (meta.get("highlights") or {}).get("status") == "rendering":
        raise HTTPException(409, "wait until processing has finished before deleting")
    storage.delete_match(match_id)
    return {"deleted": match_id}


@app.get("/api/players")
async def list_players():
    return await run_in_threadpool(profiles.build_profiles)


@app.get("/api/matches/{match_id}/review/{index}.jpg")
async def review_frame(match_id: str, index: int):
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    jpg = await run_in_threadpool(review.render_frame, match_id, index)
    if jpg is None:
        raise HTTPException(404, "frame not available")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/matches/{match_id}/coach-report")
async def create_coach_report(match_id: str):
    if not coach_available():
        raise HTTPException(503, "coach report is disabled: set ANTHROPIC_API_KEY and install the anthropic package")
    if storage.load_meta(match_id) is None:
        raise HTTPException(404, "match not found")
    results = storage.load_results(match_id)
    if results is None:
        raise HTTPException(404, "results not ready")
    try:
        report = await run_in_threadpool(generate_coach_report, results)
    except anthropic.APIError as e:
        raise HTTPException(502, f"Claude API error: {e}")
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    results["coach_report"] = report
    storage.save_results(match_id, results)
    return report


def _public(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if k != "homography"}


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ".mp4"
    return "." + filename.rsplit(".", 1)[-1].lower()
