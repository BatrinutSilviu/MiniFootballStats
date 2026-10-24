from app import storage
from app.pipeline.detect_track import track_video
from app.pipeline.teams import assign_teams
from app.pipeline.stats import compute_match_stats


def process_match(match_id: str, progress_cb=None) -> None:
    meta = storage.load_meta(match_id)
    if meta is None:
        raise RuntimeError(f"unknown match {match_id}")
    if "homography" not in meta:
        raise RuntimeError("match has not been calibrated yet")

    video_path = str(storage.video_path(match_id))
    frames = list(track_video(video_path, progress_cb=progress_cb))
    if not frames:
        raise RuntimeError("no frames could be read from the video")

    team_map = assign_teams(frames)

    results = compute_match_stats(
        frames=frames,
        h=meta["homography"],
        team_map=team_map,
        pitch_length_m=meta["pitch_length_m"],
        pitch_width_m=meta["pitch_width_m"],
    )
    storage.save_results(match_id, results)
