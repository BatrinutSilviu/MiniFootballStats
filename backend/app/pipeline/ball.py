"""
Ball tracking and ball state: for every sampled frame, where the ball is and
whether a goalkeeper holds it, it is on the ground (in play), in the air, or
out of play.

Why this is not just "project the ball onto the pitch": the pitch mapping is
only valid for points ON the ground. A ball in the air projects onto the
ground far behind its real position (with a low camera, a ball at knee height
20 m away lands ~8 m off), and a ball in a keeper's hands lands behind the keeper.
So the ball is reasoned about in the image first:

1. Contact. A ball overlapping a person's box is attributed to that person,
   but only if its apparent size fits a ball at that person's distance (a ball
   far behind a player can overlap them in the image yet look much smaller).
   Where on the body decides the state: at the feet -> on the ground with that
   player; in the hands / above the head of a goalkeeper -> keeper holds it;
   at the chest / head of an outfield player -> in the air (a chest or header).
2. Apparent size. A ball in the air is closer to the camera than the ground
   point it projects to, so it looks bigger than a ground ball there would.
   The expected size comes from the pitch calibration; the ratio is
   self-calibrated per video from balls seen at players' feet, so lens, ball
   size and detector box bias cancel out. This works at any camera height and
   is most sensitive exactly when the camera is low and the error matters most.
3. Continuity is checked in "mosaic" pixels (image coordinates with the camera
   motion removed), which stay valid whether the ball is on the ground or up
   in the air, so the tracker doesn't drop the ball during flights.
   For high cameras, where low balls barely change size, a second cue: projected
   onto the ground, a rising ball races away faster than any ball can move.
4. Out of play = a ground ball beyond a line. An airborne ball that merely
   projects outside the pitch is told apart by its size and by coming back in.
5. Gaps (ball hidden or blurred) are filled per state: a keeper hugging the
   ball keeps holding it, a ball out stays out until it reappears in play.

During a flight the ball's ground track is a straight line at constant speed,
so ground positions in the air are interpolated between take-off and landing.
"""
import numpy as np

from app.config import (
    AIR_SIZE_RATIO,
    BALL_DIAMETER_M,
    BALL_MAX_INTERP_S,
    BALL_MAX_SPEED_MS,
    GOAL_WIDTH_M,
    KEEPER_HOLD_MAX_S,
    OUT_MARGIN_M,
)
from app.pipeline.calibration import pixel_to_pitch

_CONFIDENT = 0.45
_LOST_AFTER_S = 1.0
_CONTACT_SIZE_RANGE = (0.6, 1.7)
_HEAD_FP_WINDOW = 6  # frames either side
_HEAD_FP_MIN = 3  # a "ball" on the same outfield player's head this often within the window is their head
_AIR_BACK_IN_S = 2.0
_FLIGHT_MAX_S = 3.0
_FAR_OUTSIDE_M = 3.0
_LOOKS_HIGH_R = 1.2
_RESTING_SPREAD_M = 1.5
_FEET_CONTACT_M = 1.2
_RESTART_INSIDE_M = 1.5
_LONE_AIR_MAX_R = 1.6
_ARRIVAL_S = 0.75
_KICK_S = 0.25  # a ball heading for the keeper's hands gets there within this
_RELEASE_SPEED_MS = 15.0
_OUT_MAX_S = 90.0

STATES = ("keeper", "ground", "air", "out", "unknown")


# -- geometry helpers ------------------------------------------------------------


def _proj(M, x, y):
    q = M @ np.array([x, y, 1.0])
    if q[2] <= 1e-9:
        return None  # behind the camera / above the horizon
    return q[0] / q[2], q[1] / q[2]


def _px_per_m(G, x, y) -> float | None:
    """Image pixels per meter for an object standing at pitch point (x, y),
    i.e. the un-foreshortened scale of the pitch->frame mapping G there."""
    p0, px, py = _proj(G, x, y), _proj(G, x + 0.5, y), _proj(G, x, y + 0.5)
    if p0 is None or px is None or py is None:
        return None
    J = np.array([[px[0] - p0[0], py[0] - p0[0]], [px[1] - p0[1], py[1] - p0[1]]]) * 2
    return float(np.linalg.svd(J, compute_uv=False)[0])


def _local_scale(H, x, y) -> float:
    """Area scale of the frame->mosaic homography around an image point."""
    p0, px, py = _proj(H, x, y), _proj(H, x + 1, y), _proj(H, x, y + 1)
    if p0 is None or px is None or py is None:
        return 1.0
    return abs((px[0] - p0[0]) * (py[1] - p0[1]) - (px[1] - p0[1]) * (py[0] - p0[0])) ** 0.5


def _outside(x, y, L, W) -> bool:
    m = OUT_MARGIN_M
    return x < -m or x > L + m or y < -m or y > W + m


# -- candidates --------------------------------------------------------------------


def _body_region(cy, box) -> str | None:
    x1, y1, x2, y2 = box
    h = y2 - y1
    f = (cy - y1) / h
    if f < -0.35 or f > 1.08:
        return None
    if f < 0:
        return "above"
    if f < 0.2:
        return "head"
    if f < 0.75:
        return "body"
    return "feet"


def _build_candidates(frames, matrices, roles, positions, L, W):
    """Per frame, every ball candidate with its image, mosaic and ground geometry
    and the people it touches (contact size ratios are raw, normalized later)."""
    out = []
    for i, (f, M) in enumerate(zip(frames, matrices)):
        cands = []
        if M is None or f["H"] is None:
            out.append(cands)
            continue
        G = np.linalg.inv(M)
        H = np.asarray(f["H"], dtype=np.float64)
        for b in f["balls"]:
            x1, y1, x2, y2 = b["box"]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            size = max(1.0, min(x2 - x1, y2 - y1))  # motion blur stretches one side only
            mosaic = _proj(H, cx, cy)
            if mosaic is None:
                continue
            ground = pixel_to_pitch(M, cx, y2)  # valid only if the ball is on the ground
            ppm = _px_per_m(G, *ground) if abs(ground[0]) < 4 * L and abs(ground[1]) < 4 * W else None
            raw_r = size / (BALL_DIAMETER_M * ppm) if ppm else None

            contacts = []
            for p in f["people"]:
                r = roles.get(p["track_id"])
                if r is None or r["role"] == "other":
                    continue
                px1, py1, px2, py2 = p["box"]
                pad = (px2 - px1) * 0.15
                if not px1 - pad <= cx <= px2 + pad:
                    continue
                region = _body_region(cy, p["box"])
                feet = positions.get(p["track_id"], {}).get(i)
                if region is None or feet is None:
                    continue
                pppm = _px_per_m(G, *feet)
                if not pppm:
                    continue
                contacts.append({"tid": p["track_id"], "region": region, "raw_r": size / (BALL_DIAMETER_M * pppm), "feet": feet})

            cands.append(
                {
                    "box": b["box"],
                    "conf": b["conf"],
                    "size": size,
                    "mosaic": mosaic,
                    "scale": _local_scale(H, cx, cy),
                    "ground": ground,
                    "raw_r": raw_r,
                    "contacts": contacts,
                }
            )
        out.append(cands)
    return out


def _size_norm(cands) -> float:
    """Median raw size ratio of balls at someone's feet = what 'on the ground' looks like here."""
    rs = [c["raw_r"] for cs in cands for cand in cs for c in cand["contacts"] if c["region"] == "feet" and 0.4 <= c["raw_r"] <= 2.5]
    if len(rs) < 8:
        return 1.0
    return float(np.clip(np.median(rs), 0.6, 1.6))


def _drop_head_false_positives(cands, roles) -> None:
    """A candidate sitting on the same outfield player's head again and again is that head
    (a real header is a single moment).
    (Goalkeepers are exempt: holding the ball up is legitimate.)"""
    on_head = [{c["tid"] for cand in cs for c in cand["contacts"] if c["region"] == "head"} for cs in cands]
    for i, cs in enumerate(cands):
        keep = []
        for cand in cs:
            heads = [c["tid"] for c in cand["contacts"] if c["region"] == "head" and roles[c["tid"]]["role"] != "goalkeeper"]
            persistent = False
            for tid in heads:
                lo, hi = max(0, i - _HEAD_FP_WINDOW), min(len(cands), i + _HEAD_FP_WINDOW + 1)
                persistent = persistent or sum(tid in on_head[j] for j in range(lo, hi)) >= _HEAD_FP_MIN
            if not persistent:
                keep.append(cand)
        cs[:] = keep


def _contact_ok(c, role, size_px, k, ground) -> bool:
    """Is a ball overlapping this person in the image really at this person?

    At the feet, the ball's own ground point must be next to the person's feet
    (then it really is a ground ball at those feet), so the size check is loose. Higher up
    the body a ball far BEHIND the person can overlap them too — with a low
    camera distant things sit high in the image — so it must look as big as a
    ball at the person's distance would. A ball above the head only counts for
    goalkeepers (holding it up); for outfield players it is a ball passing behind.
    Box sizes of a few pixels are off by a pixel or two, so tiny balls get more slack."""
    r = c["raw_r"] / k
    tol = min(0.7, 2.5 / max(size_px, 1.0))
    if c["region"] == "feet":
        near = ((ground[0] - c["feet"][0]) ** 2 + (ground[1] - c["feet"][1]) ** 2) ** 0.5 <= _FEET_CONTACT_M
        return near and 0.4 <= r <= 2.5
    if role == "goalkeeper":
        lo, hi = _CONTACT_SIZE_RANGE
        return lo * (1 - tol) <= r <= hi * (1 + tol)
    if c["region"] == "above":
        return False
    return 0.75 * (1 - tol / 2) <= r <= 1.5 * (1 + tol / 2)


def _classify(cand, roles, k, L, W) -> dict:
    """State of one candidate, before temporal reasoning. Uses the temporally
    smoothed ball size when available (box sizes of tiny balls are noisy)."""
    size = cand.get("size_s", cand["size"])
    scale = size / cand["size"]
    contacts = [{**c, "raw_r": c["raw_r"] * scale} for c in cand["contacts"]]
    valid = [c for c in contacts if _contact_ok(c, roles[c["tid"]]["role"], size, k, cand["ground"])]
    if valid:
        # a confirmed feet contact is geometric proof; otherwise the best size match wins
        c = min(valid, key=lambda c: (c["region"] != "feet", abs(np.log(c["raw_r"] / k))))
        role = roles[c["tid"]]["role"]
        if c["region"] == "feet":
            gx, gy = cand["ground"]
            return {"state": "ground", "holder": c["tid"], "x": gx, "y": gy, "r": c["raw_r"] / k}
        if role == "goalkeeper":
            return {"state": "keeper", "holder": c["tid"], "x": c["feet"][0], "y": c["feet"][1], "r": c["raw_r"] / k}
        return {"state": "air", "holder": c["tid"], "x": c["feet"][0], "y": c["feet"][1], "r": c["raw_r"] / k}

    r = cand["raw_r"] * scale / k if cand["raw_r"] else None
    if r is None or r >= AIR_SIZE_RATIO:
        return {"state": "air", "holder": None, "x": None, "y": None, "r": r}
    gx, gy = cand["ground"]
    return {"state": "outside" if _outside(gx, gy, L, W) else "ground", "holder": None, "x": gx, "y": gy, "r": r}


# -- tracking ----------------------------------------------------------------------


def _gate_px(prev, dt) -> float:
    """How far (mosaic px) the ball can move in dt, from its apparent size as a pixel ruler."""
    px_per_m = prev["size"] / BALL_DIAMETER_M / max(prev["scale"], 1e-6)
    return (BALL_MAX_SPEED_MS * dt + 1.5) * max(px_per_m, 3.0) * 1.3


def _dist(a, b) -> float:
    return ((a["mosaic"][0] - b["mosaic"][0]) ** 2 + (a["mosaic"][1] - b["mosaic"][1]) ** 2) ** 0.5


def _select(cands, times, roles, k, L, W) -> list[dict | None]:
    chosen: list[dict | None] = [None] * len(cands)
    last = None  # (frame index, candidate)
    for i, cs in enumerate(cands):
        if not cs:
            continue
        if last is not None and times[i] - times[last[0]] <= _LOST_AFTER_S:
            gate = _gate_px(last[1], times[i] - times[last[0]])
            best = min(cs, key=lambda c: _dist(c, last[1]))
            if _dist(best, last[1]) <= gate:
                chosen[i] = best
                last = (i, best)
            continue
        for c in sorted(cs, key=lambda c: -c["conf"]):
            held = _classify(c, roles, k, L, W)["state"] == "keeper"
            if c["conf"] >= _CONFIDENT or held or _confirmed(c, i, cands, times):
                chosen[i] = c
                last = (i, c)
                break
    return chosen


def _confirmed(c, i, cands, times) -> bool:
    for j in range(i + 1, min(len(cands), i + 3)):
        gate = _gate_px(c, times[j] - times[i])
        if any(_dist(d, c) <= gate for d in cands[j]):
            return True
    return False


# -- temporal reasoning -------------------------------------------------------------


def _smooth_sizes(chosen, times) -> None:
    """Median ball size over the sighting and its neighbours within 0.75 s."""
    idx = [i for i, c in enumerate(chosen) if c is not None]
    for n, i in enumerate(idx):
        near = [chosen[j]["size"] for j in idx[max(0, n - 2) : n + 3] if abs(times[j] - times[i]) <= 0.75]
        chosen[i] = {**chosen[i], "size_s": float(np.median(near))}


def _smooth_air(obs, idx) -> None:
    """Size ratios of tiny boxes are noisy: decide air/ground for contact-free
    sightings on the median of each sighting and its direct neighbours."""
    for n, i in enumerate(idx):
        o = obs[i]
        if o["holder"] is not None or o["state"] not in ("ground", "air", "outside"):
            continue
        rs = [obs[j]["r"] for j in idx[max(0, n - 1) : n + 2] if abs(j - i) <= 1 and obs[j]["r"] is not None and obs[j]["holder"] is None]
        if not rs or o["r"] is None:
            continue
        med = float(np.median(rs))
        if o["state"] == "air" and med < _LONE_AIR_MAX_R and _between_ground(obs, idx, n):
            gx, gy = o["ground"]
            o.update(state="ground", x=gx, y=gy)  # one mildly large box among ground sightings: noise
            continue
        if med >= AIR_SIZE_RATIO and o["state"] != "air":
            o.update(state="air", x=None, y=None)
        elif med < AIR_SIZE_RATIO and o["state"] == "air" and o["ground"] is not None:
            gx, gy = o["ground"]
            o.update(state="ground", x=gx, y=gy)


def _between_ground(obs, idx, n) -> bool:
    return 0 < n < len(idx) - 1 and obs[idx[n - 1]]["state"] == "ground" and obs[idx[n + 1]]["state"] == "ground"


def _projection_jumps(obs, idx, times) -> None:
    """Second air cue, for high cameras where low balls barely change apparent size:
    projected onto the ground, a rising ball races away from the camera faster
    than any ball can move. Compared against neighbouring sightings that are
    surely on the ground (at someone's feet)."""
    def anchored(o):
        return o["state"] in ("ground", "keeper") and o["holder"] is not None and o["x"] is not None

    for n, i in enumerate(idx):
        o = obs[i]
        if o["holder"] is not None or o["state"] not in ("ground", "outside"):
            continue
        for m in (n - 1, n + 1):
            if not 0 <= m < len(idx) or not anchored(obs[idx[m]]):
                continue
            dt = abs(times[idx[m]] - times[i])
            if dt == 0 or dt > _LOST_AFTER_S:
                continue
            nb = obs[idx[m]]
            if ((o["x"] - nb["x"]) ** 2 + (o["y"] - nb["y"]) ** 2) ** 0.5 / dt > BALL_MAX_SPEED_MS:
                o.update(state="air", x=None, y=None)
                break


def _resolve_outside(obs, idx, times, L, W) -> None:
    """A ground-looking ball beyond a line is out of play — unless it is back
    inside within a moment and looked a bit large: then it was a high ball."""
    n = 0
    while n < len(idx):
        if obs[idx[n]]["state"] != "outside":
            n += 1
            continue
        m = n
        while m + 1 < len(idx) and obs[idx[m + 1]]["state"] == "outside":
            m += 1
        run = [obs[idx[j]] for j in range(n, m + 1)]
        nxt = obs[idx[m + 1]] if m + 1 < len(idx) else None
        # back in play = seen inside on its own or at someone's feet; a chest-height
        # "contact" may just be a player standing in front of the ball
        back_in = (
            nxt is not None
            and nxt["state"] != "outside"
            and not (nxt["state"] == "air" and nxt["holder"] is not None)
            and times[idx[m + 1]] - times[idx[m]] <= _AIR_BACK_IN_S
        )
        rs = [o["r"] for o in run if o["r"] is not None]
        looks_high = rs and float(np.median(rs)) >= _LOOKS_HIGH_R
        # a ball resting out of play stays put; a ball in the air moves fast on the ground
        pts = np.array([[o["x"], o["y"]] for o in run])
        resting = len(run) >= 3 and float(np.max(np.linalg.norm(pts - np.median(pts, axis=0), axis=1))) <= _RESTING_SPREAD_M
        # one lone sighting projecting far beyond a line is far more likely a high ball
        # than a ball out: a ball that is really out is normally seen there repeatedly
        far = len(run) == 1 and _outside_by(run[0], L, W) > _FAR_OUTSIDE_M
        brief = times[idx[m]] - times[idx[n]] <= _AIR_BACK_IN_S
        # a lone sighting just over a line with play going straight on: calibration
        # error on a ball at the line, not a ball out (a real out lasts seconds)
        grazing = len(run) == 1 and back_in and times[idx[m + 1]] - times[idx[m]] <= 1.5
        for o in run:
            if resting:
                o["state"] = "out"
            elif (back_in and brief and looks_high) or far:
                o.update(state="air", x=None, y=None)
            elif grazing:
                o["state"] = "ground"
            else:
                o["state"] = "out"
        n = m + 1

    # a lone in-play-looking sighting between two "out" sightings is noise, or a
    # player picking the ball up by hand to take the restart: the ball stays out
    for n in range(1, len(idx) - 1):
        a, o, b = obs[idx[n - 1]], obs[idx[n]], obs[idx[n + 1]]
        if a["state"] == b["state"] == "out" and o["state"] != "out" and (o["holder"] is None or o["state"] == "air"):
            if times[idx[n + 1]] - times[idx[n - 1]] <= 3.0:
                o["state"] = "out"
                if o["x"] is None and o["ground"] is not None:
                    o["x"], o["y"] = o["ground"]


def _out_hysteresis(obs, idx, L, W) -> None:
    """Once out, the ball stays out until play clearly restarts: a kick-in (someone's
    feet on it), a keeper restart (in the keeper's hands), or the ball seen well inside
    the pitch. Far from the camera one pixel is about a meter, so a ball resting
    just beyond a line flickers in and out of the margin otherwise."""
    out = False
    for i in idx:
        o = obs[i]
        if o["state"] == "out":
            out = True
            continue
        if not out:
            continue
        restarted = (o["holder"] is not None and o["state"] in ("ground", "keeper")) or (
            o["holder"] is None and o["state"] == "ground" and _inside_by(o, L, W) > _RESTART_INSIDE_M
        )
        if restarted:
            out = False
        else:
            o["state"] = "out"
            if o["x"] is None and o["ground"] is not None:
                o["x"], o["y"] = o["ground"]


def _inside_by(o, L, W) -> float:
    return min(o["x"], L - o["x"], o["y"], W - o["y"])


def _outside_by(o, L, W) -> float:
    x, y = o["x"], o["y"]
    return max(-x, x - L, -y, y - W, 0.0)


def _keeper_release(oa, landing, t_landing, t_b) -> float:
    """When did the keeper let go? Work back from where the ball next has a known
    position (often where the throw lands), at a typical throw / kick speed.
    It must have been released before it was next seen."""
    if landing is not None and oa["x"] is not None:
        d = ((landing["x"] - oa["x"]) ** 2 + (landing["y"] - oa["y"]) ** 2) ** 0.5
        return min(t_landing - d / _RELEASE_SPEED_MS, t_b - 0.25)
    return t_b - 0.5


def _fill(track, obs, idx, times) -> None:
    """Decide the state of frames where the ball wasn't seen, from the sightings
    around them. When the state changed somewhere inside the gap, the change is
    placed at the most likely moment (midpoint unless we know better)."""
    for n, (a, b) in enumerate(zip(idx, idx[1:])):
        if b - a < 2:
            continue
        oa, ob = obs[a], obs[b]
        sa, sb = oa["state"], ob["state"]
        ta, tb = times[a], times[b]
        dt = tb - ta
        mid = (ta + tb) / 2

        def split(at):
            return lambda t: sa if t < at else sb

        rule = None
        if sa == "keeper" and (sb == "keeper" and dt <= KEEPER_HOLD_MAX_S or dt <= 3.0):
            # keeper hides the ball against the body, then throws / kicks it
            nxt = next((j for j in idx[n + 1 :] if obs[j]["x"] is not None and times[j] - tb <= 4.0), None)
            landing = obs[nxt] if nxt is not None else None
            release = tb if sb == "keeper" else _keeper_release(oa, landing, times[nxt] if nxt is not None else tb, tb)
            rule = lambda t, release=release: "keeper" if t < release else ("air" if sb == "air" else "unknown")
        elif sb == "keeper" and sa in ("air", "ground") and dt <= KEEPER_HOLD_MAX_S:
            # the ball reaches the keeper fast, then is usually hidden in their arms
            rule = split(ta + _ARRIVAL_S)
        elif sa == "out" and dt <= _OUT_MAX_S:
            # ball retrieved and put back in play shortly before it is seen again
            rule = split(tb if sb == "out" else max(mid, tb - 1.5))
        elif sa == sb == "ground" and dt <= BALL_MAX_INTERP_S:
            rule = split(tb)
        elif sa == sb == "air" and dt <= _FLIGHT_MAX_S:
            rule = split(tb)
        elif sa == "ground" and sb == "air" and dt <= _FLIGHT_MAX_S:
            rule = split(ta + _KICK_S)  # a kicked ball leaves the ground at once
        elif {sa, sb} <= {"ground", "air", "out"} and sa != "out" and dt <= _FLIGHT_MAX_S:
            rule = split(mid)
        if rule is None:
            continue

        for k in range(a + 1, b):
            st = rule(times[k])
            entry = {"state": st, "holder": None, "x": None, "y": None, "src": "inferred", "box": None}
            if st == "keeper":
                held = oa if sa == "keeper" else ob
                entry.update(holder=held["holder"], x=held["x"], y=held["y"])
            track[k] = entry
    if idx:
        last = idx[-1]
        if obs[last]["state"] == "out":
            for k in range(last + 1, len(track)):
                if times[k] - times[last] > _OUT_MAX_S:
                    break
                track[k] = {"state": "out", "holder": None, "x": None, "y": None, "src": "inferred", "box": None}


def _interpolate_positions(track, times) -> None:
    """Ground positions for frames without one: linear between known ground
    points (rolling ball, or the straight ground track of a flight)."""
    known = [i for i, p in enumerate(track) if p is not None and p["x"] is not None]
    for a, b in zip(known, known[1:]):
        if b - a < 2 or times[b] - times[a] > _FLIGHT_MAX_S:
            continue
        pa, pb = track[a], track[b]
        dt = times[b] - times[a]
        if ((pb["x"] - pa["x"]) ** 2 + (pb["y"] - pa["y"]) ** 2) ** 0.5 > BALL_MAX_SPEED_MS * dt + 1.0:
            continue
        for k in range(a + 1, b):
            p = track[k]
            if p is None or p["state"] not in ("ground", "air", "keeper"):
                continue
            r = (times[k] - times[a]) / dt
            p["x"] = pa["x"] + (pb["x"] - pa["x"]) * r
            p["y"] = pa["y"] + (pb["y"] - pa["y"]) * r
            if p["src"] == "inferred":
                p["src"] = "flight" if p["state"] == "air" else "interpolated"


def track_ball(frames, matrices, roles, positions, pitch_length_m, pitch_width_m) -> tuple[list[dict | None], dict]:
    """One entry per frame: {"state", "holder", "x", "y", "src", "box"} or None (no idea).
    state: keeper | ground | air | out ; x/y in meters (None when unknown);
    src: detected | interpolated | flight | inferred; box: the ball's box in frame px."""
    L, W = pitch_length_m, pitch_width_m
    times = [f["t"] for f in frames]
    cands = _build_candidates(frames, matrices, roles, positions, L, W)
    _drop_head_false_positives(cands, roles)
    k = _size_norm(cands)
    chosen = _select(cands, times, roles, k, L, W)
    _smooth_sizes(chosen, times)

    obs: dict[int, dict] = {}
    for i, c in enumerate(chosen):
        if c is not None:
            obs[i] = {**_classify(c, roles, k, L, W), "ground": c["ground"], "box": c["box"]}
    idx = sorted(obs)
    _smooth_air(obs, idx)
    _projection_jumps(obs, idx, times)
    _resolve_outside(obs, idx, times, L, W)
    _out_hysteresis(obs, idx, L, W)

    track: list[dict | None] = [None] * len(frames)
    for i in idx:
        o = obs[i]
        track[i] = {"state": o["state"], "holder": o["holder"], "x": o["x"], "y": o["y"], "src": "detected", "box": o["box"]}
    _fill(track, obs, idx, times)
    _interpolate_positions(track, times)
    for p in track:
        if p is not None and p["x"] is not None:
            p["x"], p["y"] = round(float(p["x"]), 2), round(float(p["y"]), 2)
    return track, {"size_norm": round(k, 3)}


def out_line(x, y, L, W) -> tuple[str, str | None, bool]:
    """Which line the ball went over: ("goal_line", "left"/"right", in_goal) or ("touchline", None, False)."""
    dx = max(-x, x - L, 0.0)
    dy = max(-y, y - W, 0.0)
    if dx > 0 and dx >= dy:
        return "goal_line", "left" if x < 0 else "right", abs(y - W / 2) <= GOAL_WIDTH_M / 2
    return "touchline", None, False
