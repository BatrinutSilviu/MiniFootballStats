"""
Turns raw (tracked-detections + team-labels + homography) into match stats:
per-player distance/speed/heatmap, team possession %, and pass/turnover counts.
"""
from collections import defaultdict

from app.config import MAX_PLAYER_JUMP_M
from app.pipeline.calibration import pixel_to_pitch
from app.pipeline.events import possessor_sequence, detect_passes

HEATMAP_COLS = 20
HEATMAP_ROWS = 10


def _build_player_pitch_positions(frames, h) -> dict[int, dict[int, tuple[float, float]]]:
    """{track_id: {frame_index: (X, Y)}} using the bottom-center of each box as foot position."""
    positions: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    for i, f in enumerate(frames):
        for p in f["people"]:
            tid = p["track_id"]
            if tid < 0:
                continue
            x1, y1, x2, y2 = p["box"]
            fx, fy = (x1 + x2) / 2, y2
            positions[tid][i] = pixel_to_pitch(h, fx, fy)
    return positions


def _player_kinematics(
    pos_by_frame: dict[int, tuple[float, float]],
    frame_dt_s: float,
    pitch_length_m: float,
    pitch_width_m: float,
):
    """Distance covered (m), avg/max speed (km/h), and a normalized heatmap grid,
    from a sparse {frame_index: (X,Y)} track for one player.
    """
    indices = sorted(pos_by_frame.keys())
    distance_m = 0.0
    speeds_kmh = []
    heat = [[0] * HEATMAP_COLS for _ in range(HEATMAP_ROWS)]

    for idx in indices:
        x, y = pos_by_frame[idx]
        col = min(HEATMAP_COLS - 1, max(0, int(x / max(1e-6, pitch_length_m) * HEATMAP_COLS)))
        row = min(HEATMAP_ROWS - 1, max(0, int(y / max(1e-6, pitch_width_m) * HEATMAP_ROWS)))
        heat[row][col] += 1

    for a, b in zip(indices, indices[1:]):
        (x1, y1), (x2, y2) = pos_by_frame[a], pos_by_frame[b]
        dt = (b - a) * frame_dt_s
        if dt <= 0:
            continue
        d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if d > MAX_PLAYER_JUMP_M:
            continue  # treat as tracking-noise teleport, not real movement
        distance_m += d
        speeds_kmh.append((d / dt) * 3.6)

    max_cell = max((max(row) for row in heat), default=0) or 1
    heat_norm = [[round(c / max_cell, 3) for c in row] for row in heat]

    return {
        "distance_m": round(distance_m, 1),
        "avg_speed_kmh": round(sum(speeds_kmh) / len(speeds_kmh), 1) if speeds_kmh else 0.0,
        "max_speed_kmh": round(max(speeds_kmh), 1) if speeds_kmh else 0.0,
        "sample_count": len(indices),
        "heatmap": heat_norm,
    }


def compute_match_stats(
    frames: list[dict],
    h: list[list[float]],
    team_map: dict[int, str],
    pitch_length_m: float,
    pitch_width_m: float,
) -> dict:
    frame_dt_s = (frames[1]["t"] - frames[0]["t"]) if len(frames) > 1 else 0.25

    duration_s = frames[-1]["t"] if frames else 0.0
    player_pitch_pos = _build_player_pitch_positions(frames, h)

    players = []
    team_distance = defaultdict(float)
    for tid, pos_by_frame in player_pitch_pos.items():
        team = team_map.get(tid, "unassigned")
        kin = _player_kinematics(pos_by_frame, frame_dt_s, pitch_length_m, pitch_width_m)
        team_distance[team] += kin["distance_m"]
        players.append({"track_id": tid, "team": team, **kin})
    players.sort(key=lambda p: (p["team"], -p["distance_m"]))

    seq = possessor_sequence(frames, player_pitch_pos, h)
    pass_stats = detect_passes(seq, team_map)

    possessed = [s for s in seq if s is not None and team_map.get(s["track_id"]) is not None]
    possession_counts = defaultdict(int)
    for s in possessed:
        possession_counts[team_map[s["track_id"]]] += 1
    total_possessed = sum(possession_counts.values()) or 1

    teams = {}
    for team in ("team_a", "team_b"):
        teams[team] = {
            "possession_pct": round(100 * possession_counts.get(team, 0) / total_possessed, 1),
            "distance_m": round(team_distance.get(team, 0.0), 1),
            "passes": pass_stats["passes"].get(team, 0),
            "turnovers": pass_stats["turnovers"].get(team, 0),
        }

    possession_timeline = [
        {"t": f["t"], "team": team_map.get(s["track_id"]) if s else None}
        for f, s in zip(frames, seq)
    ]

    return {
        "pitch": {"length_m": pitch_length_m, "width_m": pitch_width_m},
        "duration_s": round(duration_s, 1),
        "frame_sample_count": len(frames),
        "teams": teams,
        "players": players,
        "possession_timeline": possession_timeline,
        "events": pass_stats["events"],
    }
