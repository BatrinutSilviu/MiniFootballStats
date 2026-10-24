import shutil

import cv2
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import storage, jobs
from app.config import DEFAULT_PITCH_LENGTH_M, DEFAULT_PITCH_WIDTH_M
from app.pipeline.calibration import compute_homography


class CalibrationRequest(BaseModel):
    corners: list[list[float]]  # 4 points [x, y], in order TL, TR, BR, BL
    pitch_length_m: float = DEFAULT_PITCH_LENGTH_M
    pitch_width_m: float = DEFAULT_PITCH_WIDTH_M

app = FastAPI(title="Minifootball Stats")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/matches")
async def create_match(video: UploadFile):
    match_id = storage.new_match_id()
    vpath = storage.video_path(match_id, suffix=_suffix(video.filename))
    with vpath.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    frame = _extract_first_frame(str(vpath))
    if frame is None:
        shutil.rmtree(storage.match_dir(match_id))
        raise HTTPException(400, "could not read a frame from the uploaded video")
    cv2.imwrite(str(storage.first_frame_path(match_id)), frame)
    h, w = frame.shape[:2]

    storage.save_meta(
        match_id,
        {
            "status": "awaiting_calibration",
            "video_filename": video.filename,
            "video_suffix": vpath.suffix,
            "frame_width": w,
            "frame_height": h,
            "pitch_length_m": DEFAULT_PITCH_LENGTH_M,
            "pitch_width_m": DEFAULT_PITCH_WIDTH_M,
        },
    )
    return {"match_id": match_id}


@app.get("/api/matches")
async def list_matches():
    return storage.list_matches()


@app.get("/api/matches/{match_id}")
async def get_match(match_id: str):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    return {"id": match_id, **meta}


@app.get("/api/matches/{match_id}/first-frame")
async def get_first_frame(match_id: str):
    p = storage.first_frame_path(match_id)
    if not p.exists():
        raise HTTPException(404, "frame not found")
    return FileResponse(p)


@app.post("/api/matches/{match_id}/calibrate")
async def calibrate_match(match_id: str, body: CalibrationRequest):
    meta = storage.load_meta(match_id)
    if meta is None:
        raise HTTPException(404, "match not found")
    if len(body.corners) != 4:
        raise HTTPException(400, "exactly 4 corner points are required (TL, TR, BR, BL)")

    h = compute_homography(body.corners, body.pitch_length_m, body.pitch_width_m)
    meta["homography"] = h
    meta["corners"] = body.corners
    meta["pitch_length_m"] = body.pitch_length_m
    meta["pitch_width_m"] = body.pitch_width_m
    meta["status"] = "queued"
    storage.save_meta(match_id, meta)

    jobs.start_processing(match_id)
    return {"status": "queued"}


@app.get("/api/matches/{match_id}/results")
async def get_results(match_id: str):
    results = storage.load_results(match_id)
    if results is None:
        raise HTTPException(404, "results not ready")
    return JSONResponse(results)


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ".mp4"
    return "." + filename.rsplit(".", 1)[-1]


def _extract_first_frame(video_path: str):
    cap = cv2.VideoCapture(video_path)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None
