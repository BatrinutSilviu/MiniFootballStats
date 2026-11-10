"""
Turns raw (tracked detections + camera homographies + calibration) into match
stats: per-player distance/speed/heatmap, team possession, passing, shots,
goalkeeper actions, shape and territory — plus the coaching insights built
from them (see insights.py).

With a moving camera, players are only measured while they are in view, so
running stats are also reported per minute observed, which stays comparable
between players and teams regardless of where the camera was pointing.
"""
from collections import defaultdict

import numpy as np

from app.config import MAX_PLAUSIBLE_SPEED_KMH
from app.pipeline.ball import track_ball
from app.pipeline.calibration import frame_to_pitch_matrices, pixel_to_pitch
from app.pipeline.events import (
    possessor_sequence,
    possession_spells,
    resolve_keeper_teams,
    defending_sides,
    side_defended,
    detect_events,
)
from app.edits import apply_event_edits
from app.pipeline.insights import build_insights
from app.pipeline.recording import recording_tips
from app.pipeline.teams import assign_roles

HEATMAP_COLS = 20
HEATMAP_ROWS = 10
TEAMS = ("team_a", "team_b")
_POSITION_MARGIN_M = 1.0  # people further outside the pitch (bench, spectators) are ignored
_MIN_TABLE_SECONDS = 5.0
_MAX_RECOVERY_S = 60.0
_POSSESSION_CARRY_S = 3.0


def _build_player_pitch_positions(frames, matrices, pitch_length_m, pitch_width_m):
    """{track_id: {frame_index: (X, Y)}} using the bottom-center of each box as foot position."""
    positions: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    m = _POSITION_MARGIN_M
    for i, (f, M) in enumerate(zip(frames, matrices)):
        if M is None:
            continue
        for p in f["people"]:
            tid = p["track_id"]
            if tid < 0:
                continue
            x1, y1, x2, y2 = p["box"]
            x, y = pixel_to_pitch(M, (x1 + x2) / 2, y2)
            if -m <= x <= pitch_length_m + m and -m <= y <= pitch_width_m + m:
                positions[tid][i] = (x, y)
    return positions


def _heat_cell(x, y, pitch_length_m, pitch_width_m):
    col = min(HEATMAP_COLS - 1, max(0, int(x / max(1e-6, pitch_length_m) * HEATMAP_COLS)))
    row = min(HEATMAP_ROWS - 1, max(0, int(y / max(1e-6, pitch_width_m) * HEATMAP_ROWS)))
    return row, col


def _normalize(heat):
    max_cell = max((max(row) for row in heat), default=0) or 1
    return [[round(c / max_cell, 3) for c in row] for row in heat]


def _player_kinematics(pos_by_frame, times, pitch_length_m, pitch_width_m):
    """Distance covered (m), avg/max speed (km/h), time observed and a heatmap
    for one player. Only consecutive samples are joined: a gap means the player
    was off-camera (or the camera was lost), and we don't guess where they went."""
    indices = sorted(pos_by_frame)
    heat = [[0] * HEATMAP_COLS for _ in range(HEATMAP_ROWS)]
    for idx in indices:
        r, c = _heat_cell(*pos_by_frame[idx], pitch_length_m, pitch_width_m)
        heat[r][c] += 1

    distance_m, observed_s, speeds = 0.0, 0.0, []
    for a, b in zip(indices, indices[1:]):
        if b - a != 1:
            continue
        dt = times[b] - times[a]
        if dt <= 0:
            continue
        (x1, y1), (x2, y2) = pos_by_frame[a], pos_by_frame[b]
        d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        observed_s += dt
        if d / dt * 3.6 > MAX_PLAUSIBLE_SPEED_KMH:
            continue  # tracking-noise teleport, not real movement
        distance_m += d
        speeds.append(d / dt * 3.6)

    return {
        "distance_m": round(distance_m, 1),
        "observed_s": round(observed_s, 1),
        "m_per_min": round(distance_m / observed_s * 60, 1) if observed_s > 0 else 0.0,
        "avg_speed_kmh": round(float(np.mean(speeds)), 1) if speeds else 0.0,
        "max_speed_kmh": round(float(np.percentile(speeds, 95)), 1) if speeds else 0.0,
        "sample_count": len(indices),
        "heat_raw": heat,
    }


def compute_match_stats(frames, camera, calibration, pitch_length_m, pitch_width_m, event_edits=None, video_info=None) -> dict:
    times = [f["t"] for f in frames]
    matrices = frame_to_pitch_matrices(frames, calibration["homography"], camera["mosaic_to_panorama"])
    positions = _build_player_pitch_positions(frames, matrices, pitch_length_m, pitch_width_m)

    role_info = assign_roles(frames, positions, pitch_length_m)
    roles = role_info["roles"]
    ball, ball_info = track_ball(frames, matrices, roles, positions, pitch_length_m, pitch_width_m)
    seq = possessor_sequence(times, positions, roles, ball)
    spells = possession_spells(seq, times)
    resolve_keeper_teams(spells, roles)
    sides = defending_sides(roles, positions, times)
    events = detect_events(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides)
    events, removed_events = apply_event_edits(events, event_edits, roles)
    involvement = _player_involvement(events)

    # players
    players = []
    team_heat = {t: [[0] * HEATMAP_COLS for _ in range(HEATMAP_ROWS)] for t in TEAMS}
    team_run = {t: {"distance_m": 0.0, "observed_s": 0.0} for t in TEAMS}
    for tid, pos_by_frame in positions.items():
        r = roles.get(tid)
        if r is None or r["role"] == "other":
            continue
        kin = _player_kinematics(pos_by_frame, times, pitch_length_m, pitch_width_m)
        heat = kin.pop("heat_raw")
        team = r["team"]
        if team in team_heat:
            for i, row in enumerate(heat):
                for j, v in enumerate(row):
                    team_heat[team][i][j] += v
            if r["role"] == "player":
                team_run[team]["distance_m"] += kin["distance_m"]
                team_run[team]["observed_s"] += kin["observed_s"]
        if kin["observed_s"] >= _MIN_TABLE_SECONDS or r["role"] == "goalkeeper":
            players.append(
                {
                    "track_id": tid,
                    "team": team or "unknown",
                    "role": r["role"],
                    **kin,
                    **involvement.get(tid, _EMPTY_INVOLVEMENT),
                    "heatmap": _normalize(heat),
                }
            )
    players.sort(key=lambda p: (p["team"], p["role"] != "goalkeeper", -p["distance_m"]))

    teams = {t: _team_stats(t, events, seq, roles, ball, positions, times, sides, team_run[t], pitch_length_m) for t in TEAMS}
    _possession_pct(teams, seq, roles)

    possession_timeline = [{"t": t, "team": roles[s]["team"] if s is not None else None} for t, s in zip(times, seq)]

    ball_detected = sum(1 for b in ball if b and b["src"] == "detected")
    registered = sum(1 for M in matrices if M is not None)
    quality = {
        "camera_registration_rate": round(registered / len(frames), 3) if frames else 0.0,
        "ball_detected_rate": round(ball_detected / registered, 3) if registered else 0.0,
        "ball_known_rate": round(sum(1 for b in ball if b) / registered, 3) if registered else 0.0,
        "ball_size_norm": ball_info["size_norm"],
        "sides_known": bool(sides),
        "goalkeepers_found": sum(1 for r in roles.values() if r["role"] == "goalkeeper"),
        "tracks": len(positions),
    }

    return {
        "pitch": {"length_m": pitch_length_m, "width_m": pitch_width_m},
        "duration_s": round(times[-1] - times[0], 1) if times else 0.0,
        "frame_sample_count": len(frames),
        "team_colors": role_info["team_colors"],
        "roles": {str(tid): {"role": r["role"], "team": r["team"]} for tid, r in roles.items()},
        "teams": teams,
        "players": players,
        "team_heatmaps": {t: _normalize(h) for t, h in team_heat.items()},
        "possession_timeline": possession_timeline,
        "ball_track": [{"t": t, **b} if b else None for t, b in zip(times, ball)],
        "ball_summary": _ball_summary(ball, matrices, events),
        "events": events,
        "removed_events": removed_events,
        "quality": quality,
        "insights": build_insights(teams, quality),
        "recording_tips": recording_tips(quality, video_info or {}),
    }


_EMPTY_INVOLVEMENT = {"passes": 0, "turnovers": 0, "shots": 0, "shots_on_target": 0, "goals": 0, "saves": 0, "keeper_handlings": 0}


def _player_involvement(events) -> dict[int, dict]:
    """Per-player counts of the events they were credited with."""
    out: dict[int, dict] = defaultdict(lambda: dict(_EMPTY_INVOLVEMENT))
    for e in events:
        if e["type"] == "pass" and e.get("from") is not None:
            out[e["from"]]["passes"] += 1
        elif e["type"] == "turnover" and e.get("from") is not None:
            out[e["from"]]["turnovers"] += 1
        elif e["type"] == "shot" and e.get("shooter") is not None:
            p = out[e["shooter"]]
            p["shots"] += 1
            p["shots_on_target"] += bool(e["on_target"])
            p["goals"] += e["outcome"] == "goal"
        elif e["type"] == "keeper_handling" and e.get("keeper") is not None:
            out[e["keeper"]]["keeper_handlings"] += 1
            out[e["keeper"]]["saves"] += bool(e["save"])
    return out


def _possession_pct(teams, seq, roles) -> None:
    counts = defaultdict(int)
    for s in seq:
        if s is not None and roles[s]["team"] in teams:
            counts[roles[s]["team"]] += 1
    total = sum(counts.values())
    for t in teams:
        teams[t]["possession_pct"] = round(100 * counts[t] / total, 1) if total else None


def _team_stats(team, events, seq, roles, ball, positions, times, sides, run, pitch_length_m) -> dict:
    opp = "team_b" if team == "team_a" else "team_a"
    passes = [e for e in events if e["type"] == "pass" and e["team"] == team]
    lost = [e for e in events if e["type"] == "turnover" and e["team"] == team]
    shots = [e for e in events if e["type"] == "shot" and e["team"] == team]
    shots_against = [e for e in events if e["type"] == "shot" and e["team"] == opp]
    keeper = [e for e in events if e["type"] in ("keeper_handling", "keeper_touch") and e["team"] == team]
    outs = [e for e in events if e["type"] == "out" and e["team"] == team and e["restart"] != "goal"]

    lost_own_third = 0
    for e in lost:
        own = side_defended(team, e["t"], sides)
        if own and e["at"]:
            gx = 0.0 if own == "left" else pitch_length_m
            lost_own_third += abs(e["at"]["x"] - gx) < pitch_length_m / 3

    saves = sum(1 for e in keeper if e["save"])
    goals_against = sum(1 for e in shots_against if e["outcome"] == "goal")
    dists = [e["distribution"] for e in keeper if e["distribution"]]

    return {
        "possession_pct": None,  # filled in by _possession_pct
        "distance_m": round(run["distance_m"], 1),
        "observed_player_minutes": round(run["observed_s"] / 60, 1),
        "m_per_min": round(run["distance_m"] / run["observed_s"] * 60, 1) if run["observed_s"] > 0 else None,
        "passes": len(passes),
        "turnovers": len(lost),
        "pass_accuracy_pct": round(100 * len(passes) / (len(passes) + len(lost)), 1) if passes or lost else None,
        "turnovers_own_third": int(lost_own_third),
        "shots": len(shots),
        "shots_on_target": sum(1 for s in shots if s["on_target"]),
        "goals": sum(1 for s in shots if s["outcome"] == "goal"),
        "shots_conceded": len(shots_against),
        "goals_conceded": goals_against,
        "balls_out": len(outs),
        "keeper": {
            "handlings": sum(1 for e in keeper if e["type"] == "keeper_handling"),
            "handlings_in_area": sum(1 for e in keeper if e["type"] == "keeper_handling" and e["in_area"]),
            "hold_s": round(sum(e["duration_s"] for e in keeper if e["type"] == "keeper_handling"), 1),
            "touches_outside_area": sum(1 for e in keeper if e["type"] == "keeper_touch"),
            "saves": saves,
            "save_pct": round(100 * saves / (saves + goals_against), 1) if saves + goals_against else None,
            "distributions": len(dists),
            "distribution_success_pct": round(100 * dists.count("teammate") / len(dists), 1) if dists else None,
        },
        "avg_recovery_s": _avg_recovery(team, events),
        "territory_pct": _territory(team, ball, times, sides, pitch_length_m),
        **_shape(team, seq, roles, positions, times),
    }


def _ball_summary(ball, matrices, events) -> dict:
    """Share of the (camera-followed) match the ball spent in each state."""
    counts = {s: 0 for s in ("keeper", "ground", "air", "out", "unknown")}
    for b, M in zip(ball, matrices):
        if M is None:
            continue
        counts[b["state"] if b else "unknown"] += 1
    total = sum(counts.values()) or 1
    pct = {f"{k}_pct": round(100 * v / total, 1) for k, v in counts.items()}
    restarts = {"kick_in": 0, "corner": 0, "goal_clearance": 0, "goal": 0}
    for e in events:
        if e["type"] == "out" and e["restart"] in restarts:
            restarts[e["restart"]] += 1
    return {
        **pct,
        "in_play_pct": round(100 * (counts["keeper"] + counts["ground"] + counts["air"]) / total, 1),
        "outs": sum(1 for e in events if e["type"] == "out"),
        "restarts": restarts,
        "keeper_holds": sum(1 for e in events if e["type"] == "keeper_handling"),
    }


def _avg_recovery(team, events) -> float | None:
    durations, lost_at = [], None
    for e in events:
        if e["type"] != "turnover":
            continue
        if e["team"] == team:
            lost_at = e["t"]
        elif e["to_team"] == team and lost_at is not None:
            if e["t"] - lost_at <= _MAX_RECOVERY_S:
                durations.append(e["t"] - lost_at)
            lost_at = None
    return round(float(np.mean(durations)), 1) if len(durations) >= 2 else None


def _territory(team, ball, times, sides, pitch_length_m) -> dict | None:
    """Share of time the ball spent in this team's defensive / middle / attacking third."""
    counts = {"defensive": 0, "middle": 0, "attacking": 0}
    for t, b in zip(times, ball):
        own = side_defended(team, t, sides) if b and b["x"] is not None and b["state"] != "out" else None
        if own is None:
            continue
        d = b["x"] if own == "left" else pitch_length_m - b["x"]
        third = "defensive" if d < pitch_length_m / 3 else "attacking" if d > 2 * pitch_length_m / 3 else "middle"
        counts[third] += 1
    total = sum(counts.values())
    if total == 0:
        return None
    return {k: round(100 * v / total, 1) for k, v in counts.items()}


def _shape(team, seq, roles, positions, times) -> dict:
    """Average team width with the ball and length (depth) without it, over
    frames where at least 3 outfield players of the team are visible."""
    by_frame = defaultdict(list)
    for tid, pos in positions.items():
        r = roles.get(tid)
        if r and r["role"] == "player" and r["team"] == team:
            for i, p in pos.items():
                by_frame[i].append(p)

    widths_in, depths_out = [], []
    holder, holder_t = None, -1e9
    for i, s in enumerate(seq):
        if s is not None and roles[s]["team"]:
            holder, holder_t = roles[s]["team"], times[i]
        if times[i] - holder_t > _POSSESSION_CARRY_S:
            holder = None
        pts = by_frame.get(i, [])
        if holder is None or len(pts) < 3:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if holder == team:
            widths_in.append(max(ys) - min(ys))
        else:
            depths_out.append(max(xs) - min(xs))
    return {
        "width_in_possession_m": round(float(np.mean(widths_in)), 1) if len(widths_in) >= 8 else None,
        "depth_out_of_possession_m": round(float(np.mean(depths_out)), 1) if len(depths_out) >= 8 else None,
    }
