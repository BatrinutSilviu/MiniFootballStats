"""
Two phases, so calibration happens on the stitched panorama and can be redone cheaply:

1. analyze_video   (slow, right after upload) — detection, tracking, camera motion
                   for every sampled frame, saved to frames.json.gz, plus a
                   panorama of everything the camera saw.
2. compute_results (fast, after calibration)  — projects everything onto the
                   pitch and computes stats, events and coaching insights.
"""
import cv2

from app import storage
from app.edits import apply_merges
from app.pipeline.camera import CameraTracker
from app.pipeline.detect_track import track_video
from app.pipeline.stats import compute_match_stats


def analyze_video(match_id: str, progress_cb=None) -> None:
    camera = CameraTracker()
    video_path = str(storage.video_path(match_id))
    frames = list(track_video(video_path, camera, progress_cb=progress_cb))
    if not frames:
        raise RuntimeError("no frames could be read from the video")

    pano = camera.build_panorama()
    if pano is None:
        raise RuntimeError("could not follow the camera in any frame (too dark, too blurry, or no texture)")
    image, mosaic_to_pano = pano
    cv2.imwrite(str(storage.panorama_path(match_id)), image, [cv2.IMWRITE_JPEG_QUALITY, 90])

    storage.save_frames(
        match_id,
        {"frames": frames, "camera": {"mosaic_to_panorama": mosaic_to_pano, **camera.quality()}},
    )
    h, w = image.shape[:2]
    storage.update_meta(match_id, panorama_width=w, panorama_height=h, camera=camera.quality())


def compute_results(match_id: str) -> None:
    meta = storage.load_meta(match_id)
    data = storage.load_frames(match_id)
    if meta is None or data is None:
        raise RuntimeError("video has not been analyzed yet")
    if "homography" not in meta:
        raise RuntimeError("match has not been calibrated yet")

    previous = storage.load_results(match_id) or {}
    results = compute_match_stats(
        frames=apply_merges(data["frames"], meta.get("track_merges")),
        camera=data["camera"],
        calibration={"homography": meta["homography"]},
        pitch_length_m=meta["pitch_length_m"],
        pitch_width_m=meta["pitch_width_m"],
        event_edits=meta.get("event_edits"),
        video_info=_video_info(match_id),
    )
    if "coach_report" in previous:
        # kept, but flagged: it was written about the stats before this recompute
        results["coach_report"] = {**previous["coach_report"], "stale": True}
    storage.save_results(match_id, results)


def _video_info(match_id: str) -> dict:
    cap = cv2.VideoCapture(str(storage.video_path(match_id)))
    try:
        if not cap.isOpened():
            return {}
        return {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0) or None,
        }
    finally:
        cap.release()
