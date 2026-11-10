"""
Rule-based coaching feedback: turns team stats into strengths to keep and
lessons to learn (each lesson with a practical drill), written for amateur
mini-football players rather than analysts.

Every rule compares a team to its opponent and/or to typical amateur ranges,
needs a minimum amount of evidence before it fires, and carries a confidence
level so shaky camera/ball data never produces confident-sounding advice.
"""

_MAX_PER_KIND = 4


def _conf(n: int, low: int, high: int, ball_ok: bool = True) -> str:
    if not ball_ok or n < low:
        return "low"
    return "high" if n >= high else "medium"


def build_insights(teams: dict, quality: dict) -> dict:
    ball_ok = quality["ball_detected_rate"] >= 0.25
    out = {}
    for team, opp in (("team_a", "team_b"), ("team_b", "team_a")):
        strengths, lessons = [], []
        t, o = teams[team], teams[opp]

        def add(kind, score, title, detail, evidence, confidence, drill=None):
            item = {"title": title, "detail": detail, "evidence": evidence, "confidence": confidence, "score": score}
            if drill:
                item["drill"] = drill
            (strengths if kind == "strength" else lessons).append(item)

        # possession
        if t["possession_pct"] is not None and o["possession_pct"] is not None:
            diff = t["possession_pct"] - o["possession_pct"]
            n = t["passes"] + t["turnovers"] + o["passes"] + o["turnovers"]
            if diff >= 15:
                add("strength", diff, "Kept the ball well",
                    "You had clearly more of the ball than the opponent, which lets you dictate the tempo and tire them out.",
                    f"Possession {t['possession_pct']}% vs {o['possession_pct']}%", _conf(n, 15, 40, ball_ok))
            elif diff <= -15:
                add("lesson", -diff, "Spent long spells without the ball",
                    "The opponent kept the ball much more. Offer more passing angles to the player on the ball and be calmer on your first touch.",
                    f"Possession {t['possession_pct']}% vs {o['possession_pct']}%", _conf(n, 15, 40, ball_ok),
                    "Rondo 4v2 in a 8x8 m square: two-touch max, the defenders swap in when they win it. 3 x 4 minutes.")

        # passing
        acc, attempts = t["pass_accuracy_pct"], t["passes"] + t["turnovers"]
        if acc is not None and attempts >= 8:
            if acc >= 75:
                add("strength", acc - 75 + 5, "Reliable passing",
                    "Most of your passes found a teammate. Keep using the simple, safe pass to build pressure.",
                    f"{t['passes']} completed, {acc}% kept", _conf(attempts, 8, 25, ball_ok))
            elif acc <= 55:
                add("lesson", 55 - acc + 5, "Giving the ball away too often",
                    "Many possessions ended with the ball going to the opponent. Look up before receiving so you know your next pass, and avoid forcing risky balls through the middle.",
                    f"Only {acc}% of possessions passed on to a teammate ({t['turnovers']} turnovers)", _conf(attempts, 8, 25, ball_ok),
                    "Passing square with 4 cones: receive on the back foot, check over the shoulder before every touch, pass within 2 touches. Add a passive defender after 5 minutes.")

        # losing the ball near your own goal
        if t["turnovers"] >= 4 and t["turnovers_own_third"] >= 3 and t["turnovers_own_third"] / t["turnovers"] >= 0.3:
            add("lesson", 10 + t["turnovers_own_third"], "Losing the ball close to your own goal",
                "A big share of your turnovers happened in your defensive third, where every mistake can become a shot. When under pressure there, choose the safe option: wide pass, back to the keeper, or clear it.",
                f"{t['turnovers_own_third']} of {t['turnovers']} turnovers in your own third", _conf(t["turnovers"], 4, 10, ball_ok),
                "Build-out game: keeper + 3 defenders vs 2 pressing attackers. Defenders score by dribbling over the halfway line; attackers score by winning it and shooting within 5 s.")

        # chance creation and finishing
        if t["shots"] - o["shots"] >= 3:
            add("strength", 5 + t["shots"] - o["shots"], "Created more chances",
                "You got into shooting positions more often than the opponent.",
                f"{t['shots']} shots vs {o['shots']}", _conf(t["shots"] + o["shots"], 5, 12, ball_ok))
        elif o["shots"] - t["shots"] >= 3:
            add("lesson", 5 + o["shots"] - t["shots"], "Allowing too many shots",
                "The opponent shot much more often. Close down the shooter faster and keep a defender between the ball and the goal.",
                f"{o['shots']} shots conceded vs {t['shots']} taken", _conf(t["shots"] + o["shots"], 5, 12, ball_ok),
                "1v1 to goal from 15 m: the defender starts 5 m away and must force the attacker wide; switch roles each rep.")
        if t["shots"] >= 4:
            on_target = t["shots_on_target"] / t["shots"]
            if on_target >= 0.6:
                add("strength", 5 + 10 * on_target, "Accurate shooting",
                    "Most of your shots tested the keeper — keep shooting early and low.",
                    f"{t['shots_on_target']} of {t['shots']} shots on target", _conf(t["shots"], 4, 10, ball_ok))
            elif on_target <= 0.35:
                add("lesson", 5 + 10 * (1 - on_target), "Shots missing the target",
                    "Many shots went wide. In a small goal, placement beats power: open your body and aim low to the corners.",
                    f"{t['shots_on_target']} of {t['shots']} shots on target", _conf(t["shots"], 4, 10, ball_ok),
                    "Finishing to small targets: cones 1 m inside each post, 2-touch finish from a lay-off, 10 reps per foot; only shots between cone and post count.")

        # goalkeeper
        k = t["keeper"]
        if k["save_pct"] is not None and k["saves"] + t["goals_conceded"] >= 3:
            n = k["saves"] + t["goals_conceded"]
            if k["save_pct"] >= 70:
                add("strength", k["save_pct"] / 10, "Strong goalkeeping",
                    "Your keeper stopped most of the shots on target that reached them.",
                    f"{k['saves']} saves, {k['save_pct']}% saved", _conf(n, 3, 8, ball_ok))
            elif k["save_pct"] <= 40:
                add("lesson", (100 - k["save_pct"]) / 10, "Keeper beaten too easily",
                    "A high share of shots on target went in. Work on the keeper's set position and on narrowing the angle.",
                    f"{k['saves']} saves, {t['goals_conceded']} goals conceded", _conf(n, 3, 8, ball_ok),
                    "Angle play: shooters from 3 spots around the area; keeper steps out on the ball-goal line and is set (feet apart, weight forward) before each shot.")
        if k["distribution_success_pct"] is not None and k["distributions"] >= 4:
            if k["distribution_success_pct"] >= 75:
                add("strength", k["distribution_success_pct"] / 10, "Keeper starts attacks well",
                    "When your keeper had the ball, it usually reached a teammate.",
                    f"{k['distribution_success_pct']}% of {k['distributions']} keeper distributions kept", _conf(k["distributions"], 4, 10, ball_ok))
            elif k["distribution_success_pct"] <= 50:
                add("lesson", (100 - k["distribution_success_pct"]) / 10, "Keeper distribution gives the ball back",
                    "After the keeper had the ball, the opponent often got it. Outfield players should show wide for a quick throw or roll-out, and the keeper should prefer the free, short option over a long punt.",
                    f"{k['distribution_success_pct']}% of {k['distributions']} keeper distributions kept", _conf(k["distributions"], 4, 10, ball_ok),
                    "Keeper restarts: 2 wide players vs 1 presser. Keeper has 4 s to roll/throw to the free side; the receiver must play forward within 2 touches.")

        # winning the ball back
        rec = t["avg_recovery_s"]
        if rec is not None:
            if rec <= 6:
                add("strength", 10 - rec, "Win the ball back quickly",
                    "After losing the ball you typically regained it within a few seconds — strong reaction and pressing.",
                    f"Average {rec}s to regain possession", _conf(t["turnovers"], 4, 10, ball_ok))
            elif rec >= 15:
                add("lesson", rec / 2, "Slow to win the ball back",
                    "After losing the ball it took a long time to get it back. React immediately: the nearest player presses, the next one covers.",
                    f"Average {rec}s to regain possession", _conf(t["turnovers"], 4, 10, ball_ok),
                    "5-second rule game: small-sided match where a team that loses the ball scores a bonus point if it wins it back within 5 s.")

        # running / work rate (does not depend on ball detection)
        if t["m_per_min"] and o["m_per_min"] and t["observed_player_minutes"] >= 3 and o["observed_player_minutes"] >= 3:
            ratio = t["m_per_min"] / o["m_per_min"]
            n = int(min(t["observed_player_minutes"], o["observed_player_minutes"]))
            if ratio >= 1.1:
                add("strength", (ratio - 1) * 50, "High work rate",
                    "Your players covered more ground per minute than the opponent — that energy helps both pressing and offering options.",
                    f"{t['m_per_min']} m/min vs {o['m_per_min']} m/min", _conf(n, 3, 15))
            elif ratio <= 0.9:
                add("lesson", (1 - ratio) * 50, "Not moving enough off the ball",
                    "The opponent covered more ground per minute. Short movements to get free and quick recovery runs make a big difference on a small pitch.",
                    f"{t['m_per_min']} m/min vs {o['m_per_min']} m/min", _conf(n, 3, 15),
                    "Pass-and-move triangles: after every pass the passer must sprint to a new cone; 30 s on / 30 s off, 6 reps.")

        # shape
        if t["width_in_possession_m"] is not None and o["width_in_possession_m"] is not None:
            if t["width_in_possession_m"] >= 1.2 * o["width_in_possession_m"]:
                add("strength", 6, "Good width in attack",
                    "With the ball you spread across the pitch, which stretches the opponent and opens gaps in the middle.",
                    f"Average width {t['width_in_possession_m']} m vs {o['width_in_possession_m']} m", "medium")
            elif t["width_in_possession_m"] <= 0.8 * o["width_in_possession_m"]:
                add("lesson", 6, "Attacking too narrow",
                    "With the ball your players bunched together, making you easy to defend. Keep one player wide on each side.",
                    f"Average width {t['width_in_possession_m']} m vs {o['width_in_possession_m']} m", "medium",
                    "Wide-channel game: 2 m channels along both touchlines that only one attacker may enter; goals count double if the assist comes from a channel.")
        if t["depth_out_of_possession_m"] is not None and o["depth_out_of_possession_m"] is not None:
            if t["depth_out_of_possession_m"] <= 0.85 * o["depth_out_of_possession_m"]:
                add("strength", 6, "Compact without the ball",
                    "When defending, your team stayed close together, leaving little space between players.",
                    f"Defensive length {t['depth_out_of_possession_m']} m vs {o['depth_out_of_possession_m']} m", "medium")
            elif t["depth_out_of_possession_m"] >= 1.15 * o["depth_out_of_possession_m"]:
                add("lesson", 6, "Gaps between defenders and attackers",
                    "Without the ball your team was stretched long, leaving space for the opponent to play through. Move up and back together as a unit.",
                    f"Defensive length {t['depth_out_of_possession_m']} m vs {o['depth_out_of_possession_m']} m", "medium",
                    "Shadow defending: the team moves as a block following the coach's ball position; the distance between first and last player must stay under 12 m.")

        # territory
        terr = t["territory_pct"]
        if terr:
            if terr["attacking"] >= 40:
                add("strength", terr["attacking"] / 5, "Pinned the opponent back",
                    "The ball spent a lot of time in your attacking third.",
                    f"{terr['attacking']}% of the time in the attacking third", "medium" if ball_ok else "low")
            elif terr["defensive"] >= 45:
                add("lesson", terr["defensive"] / 5, "Stuck in your own half",
                    "The ball spent a lot of time near your own goal. Look for a forward pass or a player to hold the ball up so the team can step up.",
                    f"{terr['defensive']}% of the time in your defensive third", "medium" if ball_ok else "low",
                    "Target-player game: one attacker must receive with their back to goal and lay off to a supporting teammate before a shot counts.")

        for items in (strengths, lessons):
            items.sort(key=lambda i: -i["score"])
            for i in items:
                del i["score"]
        out[team] = {"strengths": strengths[:_MAX_PER_KIND], "lessons": lessons[:_MAX_PER_KIND]}

    notes = []
    if quality["camera_registration_rate"] < 0.8:
        notes.append("The camera view could not be followed in many frames (fast pans, cuts or blur), so some play is missing from the stats.")
    if not ball_ok:
        notes.append("The ball was detected in few frames, so possession, passing, shots and keeper stats are rough estimates. A dedicated ball model would help (see README).")
    if not quality["sides_known"]:
        notes.append("No goalkeepers were identified, so attacking direction is unknown and territory / own-third stats are unavailable.")
    out["notes"] = notes
    return out
