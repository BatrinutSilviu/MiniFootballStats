"""
Heuristic event detection from the ball trajectory and player positions.
Approximate by nature — good enough to spot patterns for coaching, not a
substitute for manual match tagging. Flagged as such in the dashboard.

Uses the per-frame ball states from ball.py (keeper / ground / air / out).

Events produced (all with "t" in seconds):
  pass / turnover          possession handoffs within the same / to the other team
                           (not across the ball going out of play)
  shot                     fast ball movement that reaches a goal (or its keeper), attributed to the
                           last possessor, with an outcome: goal | saved | blocked | off_target | unknown
  keeper_handling          a goalkeeper holding the ball in their hands (in_area tells whether
                           that was inside their goal area; save=True when it ends a shot)
  keeper_touch             a goalkeeper playing the ball with their feet
  out                      the ball leaving the pitch: line, last touch and the restart it gives
Keeper distributions (what happens right after a keeper has the ball) are
attached to the keeper events as "distribution": "teammate" | "opponent" | None.
"""
from app.pipeline.ball import out_line
from app.config import (
    BALL_POSSESSION_RADIUS_M,
    POSSESSION_MAX_BALL_SPEED_MS,
    GOAL_AREA_DEPTH_M,
    GOAL_WIDTH_M,
    SHOT_MIN_SPEED_MS,
    SHOT_MAX_DIST_M,
    SHOT_OUTCOME_WINDOW_S,
)

_HANDOFF_MAX_GAP_S = 4.0  # longer ball-less gaps (out of play, camera lost) are not passes/turnovers
_SHOT_ATTRIBUTION_S = 1.5
_SHOT_COOLDOWN_S = 2.0
_SHOT_REACH_M = 3.0  # a shot must get this close to the goal line (or be stopped by the keeper)


def _has_pos(b) -> bool:
    return b is not None and b["x"] is not None


def _ball_speed(ball, times, i, j) -> float | None:
    if not (0 <= i < len(ball) and 0 <= j < len(ball)) or not _has_pos(ball[i]) or not _has_pos(ball[j]) or times[j] == times[i]:
        return None
    d = ((ball[j]["x"] - ball[i]["x"]) ** 2 + (ball[j]["y"] - ball[i]["y"]) ** 2) ** 0.5
    return d / abs(times[j] - times[i])


def _ball_controllable(ball, times, i) -> bool:
    """At the frame a player receives or plays the ball, one side (in or out) is
    slow; a ball flying past a player is fast on both sides."""
    speeds = [s for s in (_ball_speed(ball, times, i - 1, i), _ball_speed(ball, times, i, i + 1)) if s is not None]
    return not speeds or min(speeds) <= POSSESSION_MAX_BALL_SPEED_MS


def possessor_sequence(times, positions, roles, ball) -> list[int | None]:
    """For each frame, who has the ball: the player it is in contact with in the
    image (feet, chest, a keeper's hands), else for a ground ball the closest
    player within BALL_POSSESSION_RADIUS_M if the ball is slow enough to control.
    Nobody has a ball that is out of play or flying free."""
    by_frame: dict[int, list[tuple[int, float, float]]] = {}
    for tid, pos in positions.items():
        if roles.get(tid, {}).get("role") not in ("player", "goalkeeper"):
            continue
        for i, (x, y) in pos.items():
            by_frame.setdefault(i, []).append((tid, x, y))

    seq: list[int | None] = []
    for i in range(len(times)):
        b = ball[i]
        if b is not None and b["holder"] is not None and b["state"] in ("keeper", "ground", "air"):
            seq.append(b["holder"])
            continue
        best_tid, best_d = None, None
        if _has_pos(b) and b["state"] == "ground" and _ball_controllable(ball, times, i):
            for tid, x, y in by_frame.get(i, []):
                d = ((x - b["x"]) ** 2 + (y - b["y"]) ** 2) ** 0.5
                if best_d is None or d < best_d:
                    best_d, best_tid = d, tid
        seq.append(best_tid if best_d is not None and best_d <= BALL_POSSESSION_RADIUS_M else None)
    return seq


def possession_spells(seq, times) -> list[dict]:
    """Collapses the per-frame sequence into spells of one player having the ball."""
    spells = []
    for i, tid in enumerate(seq):
        if tid is None:
            continue
        if spells and spells[-1]["tid"] == tid and times[i] - spells[-1]["t_end"] <= _HANDOFF_MAX_GAP_S:
            spells[-1]["t_end"] = times[i]
            spells[-1]["i_end"] = i
        else:
            spells.append({"tid": tid, "t_start": times[i], "t_end": times[i], "i_start": i, "i_end": i})
    return spells


def resolve_keeper_teams(spells, roles) -> None:
    """A keeper's team, from who they hand the ball to: keepers throw/pass to
    teammates far more often than to opponents. This overrides the kit color
    when the evidence is clear (a keeper's kit can resemble the other team's),
    and two keepers guarding opposite goals can't be on the same team."""
    votes: dict[int, dict[str, int]] = {}
    for a, b in zip(spells, spells[1:]):
        ra, rb = roles[a["tid"]], roles[b["tid"]]
        if ra["role"] == "goalkeeper" and rb["role"] == "player" and rb["team"]:
            if b["t_start"] - a["t_end"] <= _HANDOFF_MAX_GAP_S:
                v = votes.setdefault(a["tid"], {})
                v[rb["team"]] = v.get(rb["team"], 0) + 1

    def support(tid, team):
        v = votes.get(tid, {})
        return v.get(team, 0) - sum(n for t, n in v.items() if t != team)

    keepers = [tid for tid, r in roles.items() if r["role"] == "goalkeeper"]
    for tid in keepers:
        v = votes.get(tid)
        if not v:
            continue
        best = max(v, key=v.get)
        if roles[tid]["team"] is None or (v[best] >= 2 and v[best] >= 2 * sum(n for t, n in v.items() if t != best)):
            roles[tid]["team"] = best

    # keepers with no evidence: copy a resolved keeper at the same end, or oppose one at the other end
    resolved = {(roles[t]["side"], roles[t]["team"]) for t in keepers if roles[t]["team"]}
    for tid in keepers:
        r = roles[tid]
        if r["team"] is not None:
            continue
        same = [t for s, t in resolved if s == r["side"]]
        other = [t for s, t in resolved if s != r["side"]]
        if len(set(same)) == 1:
            r["team"] = same[0]
        elif len(set(other)) == 1:
            r["team"] = _other(other[0])

    # both ends claimed by one team: move the keeper with the weaker evidence
    left = [t for t in keepers if roles[t]["side"] == "left" and roles[t]["team"]]
    right = [t for t in keepers if roles[t]["side"] == "right" and roles[t]["team"]]
    for a in left:
        for b in right:
            if roles[a]["team"] == roles[b]["team"]:
                team = roles[a]["team"]
                weaker = a if support(a, team) < support(b, team) else b
                roles[weaker]["team"] = _other(team)


def _other(team: str) -> str:
    return "team_b" if team == "team_a" else "team_a"


def defending_sides(roles, positions, times) -> list[dict]:
    """Time intervals during which a team is known to defend a goal, derived
    from where its goalkeepers stood. Handles teams switching ends at halftime."""
    out = []
    for tid, r in roles.items():
        if r["role"] == "goalkeeper" and r["team"] and positions.get(tid):
            idx = sorted(positions[tid])
            out.append({"team": r["team"], "side": r["side"], "t_start": times[idx[0]], "t_end": times[idx[-1]]})
    return out


def side_defended(team: str, t: float, intervals: list[dict]) -> str | None:
    def dist(iv):
        return 0.0 if iv["t_start"] <= t <= iv["t_end"] else min(abs(t - iv["t_start"]), abs(t - iv["t_end"]))

    if not intervals:
        return None
    iv = min(intervals, key=dist)
    if iv["team"] == team:
        return iv["side"]
    return "right" if iv["side"] == "left" else "left"


def detect_events(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides) -> list[dict]:
    spells = possession_spells(seq, times)
    team = {tid: r["team"] for tid, r in roles.items()}
    shots = _detect_shots(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides)
    shots += _inferred_saves(spells, roles, ball, shots, pitch_length_m, pitch_width_m)
    events: list[dict] = list(shots)

    # passes / turnovers (a handoff that ends a shot is neither)
    for a, b in zip(spells, spells[1:]):
        if b["t_start"] - a["t_end"] > _HANDOFF_MAX_GAP_S:
            continue
        ta, tb = team.get(a["tid"]), team.get(b["tid"])
        if ta is None or tb is None:
            continue
        if any(s["shooter"] == a["tid"] and a["t_end"] - 0.5 <= s["t"] <= b["t_start"] for s in shots):
            continue
        if any(ball[k] is not None and ball[k]["state"] == "out" for k in range(a["i_end"], b["i_start"] + 1)):
            continue  # ball went out in between: a restart, not a pass or a turnover
        bpos = ball[a["i_end"]]
        where = {"x": bpos["x"], "y": bpos["y"]} if _has_pos(bpos) else None
        if ta == tb:
            events.append({"type": "pass", "team": ta, "t": b["t_start"], "from": a["tid"], "to": b["tid"], "at": where})
        else:
            events.append({"type": "turnover", "team": ta, "to_team": tb, "t": b["t_start"], "from": a["tid"], "at": where})

    events += _keeper_events(spells, roles, ball, pitch_length_m, events)
    events += _out_events(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides)
    events.sort(key=lambda e: e["t"])
    return events


def _goal_x(side, pitch_length_m):
    return 0.0 if side == "left" else pitch_length_m


def _detect_shots(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides) -> list[dict]:
    shots = []
    last_shot_t = -1e9
    mid_y = pitch_width_m / 2
    for i in range(1, len(times)):
        p0, p1 = ball[i - 1], ball[i]
        if not _has_pos(p0) or not _has_pos(p1) or "out" in (p0["state"], p1["state"]):
            continue
        dt = times[i] - times[i - 1]
        if dt <= 0:
            continue
        vx, vy = (p1["x"] - p0["x"]) / dt, (p1["y"] - p0["y"]) / dt
        speed = (vx**2 + vy**2) ** 0.5
        if speed < SHOT_MIN_SPEED_MS or abs(vx) < 1e-6 or times[i] - last_shot_t < _SHOT_COOLDOWN_S:
            continue
        target = "left" if vx < 0 else "right"
        gx = _goal_x(target, pitch_length_m)
        if abs(p0["x"] - gx) > SHOT_MAX_DIST_M:
            continue
        y_cross = p0["y"] + vy * (gx - p0["x"]) / vx
        miss_by = abs(y_cross - mid_y) - GOAL_WIDTH_M / 2
        if miss_by > 2.5:
            continue  # moving toward the end line but well wide: a cross/clearance, not a shot

        shooter = _last_possessor(seq, times, i - 1, _SHOT_ATTRIBUTION_S)
        if shooter is None:
            continue
        r = roles[shooter]
        if r["team"] is None or (r["role"] == "goalkeeper" and r["side"] == target):
            continue
        defending = side_defended(r["team"], times[i], sides)
        if defending == target:
            continue  # moving toward their own goal: a back pass, not a shot

        on_target = miss_by <= 0.3
        outcome = _shot_outcome(i, times, seq, roles, ball, shooter, target, gx, mid_y, on_target)
        if outcome is None:
            continue
        shots.append(
            {
                "type": "shot",
                "team": r["team"],
                "t": times[i - 1],
                "shooter": shooter,
                "target_side": target,
                "from": {"x": round(p0["x"], 1), "y": round(p0["y"], 1)},
                "distance_m": round(((p0["x"] - gx) ** 2 + (p0["y"] - mid_y) ** 2) ** 0.5, 1),
                "speed_kmh": round(speed * 3.6, 1),
                "on_target": on_target or outcome in ("goal", "saved"),
                "outcome": outcome,
            }
        )
        last_shot_t = times[i]
    return shots


def _inferred_saves(spells, roles, ball, shots, pitch_length_m, pitch_width_m) -> list[dict]:
    """Fast shots are often blurred out of the ball detections entirely. If an
    attacker loses the ball within shooting range and the keeper of the goal
    they attack has it shortly after, that was almost always a shot on target."""
    out = []
    mid_y = pitch_width_m / 2
    for a, b in zip(spells, spells[1:]):
        ra, rb = roles[a["tid"]], roles[b["tid"]]
        if ra["role"] != "player" or rb["role"] != "goalkeeper" or ra["team"] is None:
            continue
        if rb["team"] == ra["team"] or b["t_start"] - a["t_end"] > SHOT_OUTCOME_WINDOW_S:
            continue
        if any(a["t_end"] - 0.5 <= s["t"] <= b["t_start"] for s in shots):
            continue  # already detected from the ball trajectory
        pa, pb = ball[a["i_end"]], ball[b["i_start"]]
        if not _has_pos(pa) or not _has_pos(pb):
            continue
        gx = _goal_x(rb["side"], pitch_length_m)
        dist_goal = ((pa["x"] - gx) ** 2 + (pa["y"] - mid_y) ** 2) ** 0.5
        travel = ((pa["x"] - pb["x"]) ** 2 + (pa["y"] - pb["y"]) ** 2) ** 0.5
        if dist_goal > SHOT_MAX_DIST_M or travel < 4.0:
            continue
        out.append(
            {
                "type": "shot",
                "team": ra["team"],
                "t": a["t_end"],
                "shooter": a["tid"],
                "target_side": rb["side"],
                "from": {"x": round(pa["x"], 1), "y": round(pa["y"], 1)},
                "distance_m": round(dist_goal, 1),
                "speed_kmh": None,
                "on_target": True,
                "outcome": "saved",
                "inferred": True,
            }
        )
    return out


def _last_possessor(seq, times, i, window_s):
    for j in range(i, -1, -1):
        if times[i] - times[j] > window_s:
            return None
        if seq[j] is not None:
            return seq[j]
    return None


def _shot_outcome(i, times, seq, roles, ball, shooter, target, gx, mid_y, on_target) -> str | None:
    """None means the fast ball never got near the goal: a long pass or a
    clearance that someone collected, not a shot."""
    reached_goal = False
    for j in range(i, len(times)):
        if times[j] - times[i] > SHOT_OUTCOME_WINDOW_S:
            break
        b = ball[j]
        if _has_pos(b):
            if b["state"] != "air" and abs(b["x"] - gx) <= 0.8 and abs(b["y"] - mid_y) <= GOAL_WIDTH_M / 2:
                return "goal"
            reached_goal = reached_goal or abs(b["x"] - gx) <= _SHOT_REACH_M
            if b["state"] == "out" and b["src"] == "detected":
                line, side, in_goal = out_line(b["x"], b["y"], pitch_length_m, 2 * mid_y)
                if line == "goal_line" and side == target:
                    return "goal" if in_goal else "off_target"
        tid = seq[j]
        if tid is None or tid == shooter:
            continue
        r = roles[tid]
        if r["role"] == "goalkeeper" and r["side"] == target:
            return "saved"
        return "blocked" if reached_goal else None
    if not reached_goal:
        return None
    return "unknown" if on_target else "off_target"


def _keeper_events(spells, roles, ball, pitch_length_m, events) -> list[dict]:
    shots = [e for e in events if e["type"] == "shot"]
    out = []
    for k, s in enumerate(spells):
        r = roles[s["tid"]]
        if r["role"] != "goalkeeper":
            continue
        b = ball[s["i_start"]]
        gx = _goal_x(r["side"], pitch_length_m)
        in_area = _has_pos(b) and abs(b["x"] - gx) <= GOAL_AREA_DEPTH_M
        in_hands = any(ball[i] is not None and ball[i]["state"] == "keeper" for i in range(s["i_start"], s["i_end"] + 1))
        save = any(sh["outcome"] == "saved" and sh["target_side"] == r["side"] and 0 <= s["t_start"] - sh["t"] <= SHOT_OUTCOME_WINDOW_S for sh in shots)

        distribution = None
        if k + 1 < len(spells) and spells[k + 1]["t_start"] - s["t_end"] <= _HANDOFF_MAX_GAP_S:
            nxt = roles[spells[k + 1]["tid"]]
            if r["team"] and nxt["team"]:
                distribution = "teammate" if nxt["team"] == r["team"] else "opponent"

        out.append(
            {
                "type": "keeper_handling" if in_hands else "keeper_touch",
                "in_area": in_area,
                "team": r["team"],
                "keeper": s["tid"],
                "side": r["side"],
                "t": s["t_start"],
                "duration_s": round(s["t_end"] - s["t_start"], 2),
                "save": save,
                "distribution": distribution,
            }
        )
    return out


def _out_events(times, seq, roles, ball, pitch_length_m, pitch_width_m, sides) -> list[dict]:
    """One event each time the ball leaves the pitch, with the restart it gives:
    over a touchline -> kick-in; over a goal line -> corner if the defending team
    touched it last, else a goal clearance by the keeper. A ball in the net is a goal."""
    out = []
    for i, b in enumerate(ball):
        if b is None or b["state"] != "out":
            continue
        if i > 0 and ball[i - 1] is not None and ball[i - 1]["state"] == "out":
            continue
        j = next((j for j in range(i, len(ball)) if ball[j] and ball[j]["state"] == "out" and _has_pos(ball[j])), None)
        where = ball[j] if j is not None else None
        if where is None or times[j] - times[i] > 2.0:
            line, side, in_goal = None, None, False
        else:
            line, side, in_goal = out_line(where["x"], where["y"], pitch_length_m, pitch_width_m)
        toucher = _last_possessor(seq, times, max(0, i - 1), 5.0)
        team = roles[toucher]["team"] if toucher is not None else None

        restart = None
        if in_goal:
            restart = "goal"
        elif line == "touchline":
            restart = "kick_in"
        elif line == "goal_line" and team is not None:
            defending = side_defended(team, times[i], sides)
            if defending is not None:
                restart = "corner" if defending == side else "goal_clearance"
        out.append(
            {
                "type": "out",
                "t": times[i],
                "line": line,
                "side": side,
                "team": team,
                "last_touch": toucher,
                "restart": restart,
                "at": {"x": where["x"], "y": where["y"]} if where is not None and line else None,
            }
        )
    return out
