"""
User corrections to a match, stored in meta.json and applied on top of the
automatic analysis:

  team_names     {"team_a": "Lions", ...}               display only
  player_names   {"<track_id>": {"name": str, "number": int|None}}  display + player profiles
  track_merges   {"<track_id>": <track_id>}              "these tracks are the same player"
                                                         (manual re-identification) — needs a recompute
  event_edits    {"removed": [key], "outcomes": {key: outcome}, "added": [event]}
                                                         fixes wrong/missed shots and goals — needs a recompute

Event keys are "<type>@<t with 2 decimals>": recomputing from the same frames
and calibration is deterministic, so they stay stable between recomputes.
"""
import copy

SHOT_OUTCOMES = ("goal", "saved", "blocked", "off_target", "unknown")
RECOMPUTE_FIELDS = ("track_merges", "event_edits")


def event_key(e: dict) -> str:
    return f"{e['type']}@{e['t']:.2f}"


def resolve_merges(merges: dict | None) -> dict[int, int]:
    """{tid: canonical tid}, following chains (a->b, b->c gives a->c) and ignoring cycles."""
    raw = {int(k): int(v) for k, v in (merges or {}).items() if int(k) != int(v)}
    out = {}
    for tid in raw:
        seen, cur = {tid}, raw[tid]
        while cur in raw and cur not in seen:
            seen.add(cur)
            cur = raw[cur]
        if cur != tid:
            out[tid] = cur
    return out


def apply_merges(frames: list[dict], merges: dict | None) -> list[dict]:
    """Relabels merged tracks in a copy of the frames. Two merged tracks seen in
    the same frame can't be the same person: the later-listed one is dropped there."""
    m = resolve_merges(merges)
    if not m:
        return frames
    out = []
    for f in frames:
        seen, people = set(), []
        for p in f["people"]:
            tid = m.get(p["track_id"], p["track_id"])
            if tid in seen and tid >= 0:
                continue
            seen.add(tid)
            people.append({**p, "track_id": tid})
        out.append({**f, "people": people})
    return out


def apply_event_edits(events: list[dict], edits: dict | None, roles: dict) -> tuple[list[dict], list[dict]]:
    """Returns (events with the edits applied, removed events). Every event gets
    its "key"; user-added events are keyed "manual@<index in the added list>"."""
    if not edits:
        return [{**e, "key": event_key(e)} for e in events], []
    removed_keys = set(edits.get("removed", []))
    outcomes = edits.get("outcomes", {})
    kept, removed = [], []
    for e in events:
        k = event_key(e)
        if k in removed_keys:
            removed.append({**e, "key": k})
            continue
        e = {**e, "key": k}
        if e["type"] == "shot" and k in outcomes and outcomes[k] in SHOT_OUTCOMES:
            e.update(outcome=outcomes[k], on_target=outcomes[k] in ("goal", "saved", "unknown"), edited=True)
        kept.append(e)

    for i, a in enumerate(edits.get("added", [])):
        e = copy.deepcopy(a)
        e["key"] = f"manual@{i}"
        shooter = e.get("shooter")
        r = roles.get(int(shooter)) if shooter is not None else None
        if r and r["team"]:
            e["team"] = r["team"]
        e.setdefault("distance_m", None)
        e.setdefault("speed_kmh", None)
        e.setdefault("target_side", None)
        e["on_target"] = e.get("outcome") in ("goal", "saved", "unknown")
        e["manual"] = True
        kept.append(e)
    kept.sort(key=lambda e: e["t"])
    return kept, removed


def validate_added_event(e: dict) -> dict:
    if e.get("type") != "shot":
        raise ValueError("only shots/goals can be added")
    if e.get("outcome") not in SHOT_OUTCOMES:
        raise ValueError(f"outcome must be one of {SHOT_OUTCOMES}")
    if e.get("team") not in ("team_a", "team_b") and e.get("shooter") is None:
        raise ValueError("an added shot needs a team or a shooter")
    t = float(e.get("t", -1))
    if t < 0:
        raise ValueError("t must be >= 0")
    out = {"type": "shot", "t": round(t, 2), "outcome": e["outcome"], "team": e.get("team")}
    if e.get("shooter") is not None:
        out["shooter"] = int(e["shooter"])
    return out
