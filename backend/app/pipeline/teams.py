"""
Assigns every tracked person a role: an outfield player of team_a / team_b,
a goalkeeper, or "other" (referee, substitutes, spectators).

1. Jersey colors (Lab) are clustered into two teams, weighting each track by
   how long it was seen. Tracks whose color fits neither team well are outliers.
2. Goalkeepers are found by position: a track that spends most of its time in
   one goal area. Outlier-colored keepers (the usual case, a different kit)
   get their team later, from who they pass the ball to (see events.py);
   team-colored keepers simply keep their color team.
3. Remaining outliers are "other" and are excluded from team stats.
"""
from collections import defaultdict

import cv2
import numpy as np
from sklearn.cluster import KMeans

from app.config import GOAL_AREA_DEPTH_M, SAMPLE_FPS

_MIN_FIT_SAMPLES = 4
_GK_MIN_SAMPLES = 3 * SAMPLE_FPS
_GK_ZONE_FRACTION_OUTLIER = 0.7
_GK_ZONE_FRACTION_TEAM_COLOR = 0.85


def _lab_to_hex(lab) -> str:
    px = np.uint8([[np.clip(lab, 0, 255)]])
    b, g, r = cv2.cvtColor(px, cv2.COLOR_LAB2BGR)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    out = []
    for ch in values.T:
        order = np.argsort(ch)
        cum = np.cumsum(weights[order])
        out.append(ch[order][np.searchsorted(cum, cum[-1] / 2)])
    return np.array(out)


def _fit(colors: np.ndarray, weights: np.ndarray):
    """Two team colors. k-means to start, then weighted medians per cluster: a
    referee or keeper seen as often as a player can drag a mean toward their
    kit, but not the median of a team's several players."""
    centers = KMeans(n_clusters=2, n_init=10, random_state=0).fit(colors, sample_weight=weights).cluster_centers_
    for _ in range(5):
        labels = np.argmin(np.linalg.norm(colors[:, None] - centers[None], axis=2), axis=1)
        if len(set(labels)) < 2:
            break
        centers = np.array([_weighted_median(colors[labels == c], weights[labels == c]) for c in (0, 1)])
    return centers


def assign_roles(frames: list[dict], positions: dict[int, dict[int, tuple]], pitch_length_m: float) -> dict:
    colors_by_track: dict[int, list] = defaultdict(list)
    for f in frames:
        for p in f["people"]:
            if p["track_id"] >= 0 and p.get("color") is not None:
                colors_by_track[p["track_id"]].append(p["color"])

    track_ids = [tid for tid, c in colors_by_track.items() if c]
    mean = {tid: np.median(colors_by_track[tid], axis=0) for tid in track_ids}
    n = {tid: len(colors_by_track[tid]) for tid in track_ids}

    roles: dict[int, dict] = {}
    fit_ids = [tid for tid in track_ids if n[tid] >= _MIN_FIT_SAMPLES] or track_ids
    if len(fit_ids) < 2:
        for tid in track_ids:
            roles[tid] = {"role": "player", "team": "team_a", "side": None}
        return {"roles": roles, "team_colors": {}}

    X = np.array([mean[t] for t in fit_ids])
    W = np.array([n[t] for t in fit_ids], dtype=float)
    centers = _fit(X, W)

    gap = float(np.linalg.norm(centers[0] - centers[1]))
    dist_all = {t: np.linalg.norm(centers - mean[t], axis=1) for t in track_ids}
    own = np.array([dist_all[t].min() for t in fit_ids])
    spread = float(_weighted_median(own[:, None], W)[0])
    outlier_thresh = max(3 * spread, 0.35 * gap, 12.0)

    # bigger cluster (by seen time) is "team_a" just for stable, readable output
    label_weight = np.zeros(2)
    for t in fit_ids:
        label_weight[int(np.argmin(dist_all[t]))] += n[t]
    name = {int(np.argmax(label_weight)): "team_a"}
    name[1 - next(iter(name))] = "team_b"

    for tid in track_ids:
        cluster = int(np.argmin(dist_all[tid]))
        is_outlier = dist_all[tid][cluster] > outlier_thresh
        side, frac = _goal_zone(positions.get(tid, {}), pitch_length_m)
        seen = len(positions.get(tid, {}))

        if side and seen >= _GK_MIN_SAMPLES and frac >= (
            _GK_ZONE_FRACTION_OUTLIER if is_outlier else _GK_ZONE_FRACTION_TEAM_COLOR
        ):
            roles[tid] = {"role": "goalkeeper", "team": None if is_outlier else name[cluster], "side": side}
        elif is_outlier:
            roles[tid] = {"role": "other", "team": None, "side": None}
        else:
            roles[tid] = {"role": "player", "team": name[cluster], "side": None}

    team_colors = {name[c]: _lab_to_hex(centers[c]) for c in (0, 1)}
    return {"roles": roles, "team_colors": team_colors}


def _goal_zone(pos_by_frame: dict, pitch_length_m: float) -> tuple[str | None, float]:
    if not pos_by_frame:
        return None, 0.0
    xs = np.array([p[0] for p in pos_by_frame.values()])
    left = float(np.mean(xs < GOAL_AREA_DEPTH_M))
    right = float(np.mean(xs > pitch_length_m - GOAL_AREA_DEPTH_M))
    return ("left", left) if left >= right else ("right", right)
