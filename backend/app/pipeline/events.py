"""
Heuristic event detection from a per-frame "who has the ball" sequence.
Approximate by nature — good enough to spot patterns for coaching, not a
substitute for manual match tagging. Flagged as such in the dashboard.
"""
from app.config import BALL_POSSESSION_RADIUS_M


def possessor_sequence(frames: list[dict], player_pitch_pos: dict, h) -> list[dict | None]:
    """For each sampled frame, find the player closest to the ball (if within
    BALL_POSSESSION_RADIUS_M). Returns one entry per frame: {track_id, team, t} or None.
    """
    from app.pipeline.calibration import pixel_to_pitch

    seq = []
    for i, f in enumerate(frames):
        if not f["balls"]:
            seq.append(None)
            continue
        ball_box = max(f["balls"], key=lambda b: b["conf"])["box"]
        bx = (ball_box[0] + ball_box[2]) / 2
        by = ball_box[3]  # ball rests near the ground; use box bottom
        ball_x, ball_y = pixel_to_pitch(h, bx, by)

        best_tid, best_dist = None, None
        for p in f["people"]:
            tid = p["track_id"]
            if tid not in player_pitch_pos or i not in player_pitch_pos[tid]:
                continue
            px, py = player_pitch_pos[tid][i]
            d = ((px - ball_x) ** 2 + (py - ball_y) ** 2) ** 0.5
            if best_dist is None or d < best_dist:
                best_dist, best_tid = d, tid

        if best_tid is not None and best_dist <= BALL_POSSESSION_RADIUS_M:
            seq.append({"track_id": best_tid, "t": f["t"]})
        else:
            seq.append(None)
    return seq


def detect_passes(seq: list[dict | None], team_map: dict[int, str]) -> dict:
    """Walks the possessor sequence and counts same-team possession handoffs as
    passes, and cross-team handoffs as turnovers/interceptions.
    """
    passes = {"team_a": 0, "team_b": 0}
    turnovers = {"team_a": 0, "team_b": 0}  # team that LOST the ball
    events = []

    last = None
    for entry in seq:
        if entry is None:
            continue
        tid = entry["track_id"]
        team = team_map.get(tid)
        if team is None:
            continue
        if last is not None and last["track_id"] != tid:
            last_team = team_map.get(last["track_id"])
            if last_team == team:
                passes[team] = passes.get(team, 0) + 1
                events.append({"type": "pass", "team": team, "t": entry["t"]})
            elif last_team is not None:
                turnovers[last_team] = turnovers.get(last_team, 0) + 1
                events.append({"type": "turnover", "team": last_team, "to_team": team, "t": entry["t"]})
        last = entry

    return {"passes": passes, "turnovers": turnovers, "events": events}
