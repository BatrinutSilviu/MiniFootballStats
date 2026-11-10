"""
Player profiles across matches. A tracking ID only means something inside one
match; once a user names a player ("tap yourself"), the same name in other
matches is treated as the same person and their stats are combined into a
profile with a season record and a card rating.
"""
from app import storage


def _slug(name: str) -> str:
    return " ".join(name.lower().split())


def _rating(p: dict) -> dict:
    """A fun 40–99 card rating with four attributes. Deliberately simple and
    explained in the UI: it's for motivation and sharing, not scouting."""
    mins = max(p["observed_s"] / 60, 10.0)  # under 10 minutes of footage, rates aren't extrapolated
    per10 = lambda v: v / mins * 10  # noqa: E731
    clamp = lambda v: int(max(40, min(99, round(v))))  # noqa: E731
    work = clamp(40 + (p["m_per_min"] - 40) * 0.8) if p["m_per_min"] else 40
    pace = clamp(40 + (p["top_speed_kmh"] - 12) * 3.5)
    attempts = p["passes"] + p["turnovers"]
    passing = clamp(45 + (100 * p["passes"] / attempts - 50) * 0.9) if attempts >= 3 else 50
    if p["role"] == "goalkeeper":
        shooting = clamp(50 + per10(p["saves"]) * 15)
    else:
        shooting = clamp(45 + per10(p["shots"]) * 6 + per10(p["goals"]) * 18)
    attrs = {"pace": pace, "work_rate": work, "passing": passing, ("keeping" if p["role"] == "goalkeeper" else "shooting"): shooting}
    overall = clamp(sum(attrs.values()) / len(attrs) + min(5, p["matches"]))
    return {"overall": overall, **attrs}


def build_profiles() -> list[dict]:
    profiles: dict[str, dict] = {}
    for m in storage.list_matches():
        names = m.get("player_names") or {}
        if m.get("status") != "done" or not names:
            continue
        results = storage.load_results(m["id"])
        if results is None:
            continue
        by_tid = {str(p["track_id"]): p for p in results["players"]}
        team_names = m.get("team_names") or {}
        for tid, label in names.items():
            name = (label or {}).get("name", "").strip()
            p = by_tid.get(tid)
            if not name or p is None:
                continue
            prof = profiles.setdefault(_slug(name), {
                "name": name, "number": None, "role": "player", "matches": 0, "observed_s": 0.0, "distance_m": 0.0,
                "top_speed_kmh": 0.0, "passes": 0, "turnovers": 0, "shots": 0, "shots_on_target": 0, "goals": 0,
                "saves": 0, "keeper_matches": 0, "history": [],
            })
            if label.get("number") is not None:
                prof["number"] = label["number"]
            prof["matches"] += 1
            prof["keeper_matches"] += p["role"] == "goalkeeper"
            prof["observed_s"] += p["observed_s"]
            prof["distance_m"] += p["distance_m"]
            prof["top_speed_kmh"] = max(prof["top_speed_kmh"], p["max_speed_kmh"])
            for k in ("passes", "turnovers", "shots", "shots_on_target", "goals", "saves"):
                prof[k] += p.get(k, 0)
            team = p["team"]
            score = {t: results["teams"][t]["goals"] for t in ("team_a", "team_b") if t in results["teams"]}
            opp = "team_b" if team == "team_a" else "team_a"
            gf, ga = score.get(team), score.get(opp)
            prof["history"].append({
                "match_id": m["id"],
                "date": m.get("created_at"),
                "title": m.get("title") or m.get("video_filename"),
                "team": team_names.get(team) or {"team_a": "Team A", "team_b": "Team B"}.get(team, team),
                "opponent": team_names.get(opp) or {"team_a": "Team A", "team_b": "Team B"}.get(opp, opp),
                "result": None if gf is None or ga is None else ("W" if gf > ga else "L" if gf < ga else "D"),
                "score": None if gf is None or ga is None else f"{gf}-{ga}",
                "role": p["role"],
                "goals": p.get("goals", 0),
                "shots": p.get("shots", 0),
                "passes": p.get("passes", 0),
                "saves": p.get("saves", 0),
                "m_per_min": p["m_per_min"],
                "max_speed_kmh": p["max_speed_kmh"],
            })

    out = []
    for prof in profiles.values():
        prof["role"] = "goalkeeper" if prof["keeper_matches"] > prof["matches"] / 2 else "player"
        prof["m_per_min"] = round(prof["distance_m"] / prof["observed_s"] * 60, 1) if prof["observed_s"] else 0.0
        prof["distance_m"] = round(prof["distance_m"], 1)
        prof["observed_s"] = round(prof["observed_s"], 1)
        prof["history"].sort(key=lambda h: h["date"] or "", reverse=True)
        prof["record"] = {r: sum(1 for h in prof["history"] if h["result"] == r) for r in ("W", "D", "L")}
        prof["rating"] = _rating(prof)
        prof.pop("keeper_matches")
        out.append(prof)
    out.sort(key=lambda p: (-p["rating"]["overall"], p["name"].lower()))
    return out
