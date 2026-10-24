"""
Assigns each tracked player to one of two teams based on jersey color,
clustered across all sampled frames. Unsupervised — no training required.

Known limitation (v1): goalkeepers are not distinguished from outfield
players; a distinctly-colored keeper kit may get pulled into whichever
team cluster it's closer to, or skew that team's average color slightly.
"""
from collections import defaultdict

import numpy as np
from sklearn.cluster import KMeans


def assign_teams(frames: list[dict]) -> dict[int, str]:
    """Returns {track_id: "team_a" | "team_b"}."""
    colors_by_track: dict[int, list[list[float]]] = defaultdict(list)
    for f in frames:
        for p in f["people"]:
            if p["track_id"] >= 0 and p.get("color") is not None:
                colors_by_track[p["track_id"]].append(p["color"])

    track_ids = [tid for tid, colors in colors_by_track.items() if colors]
    if len(track_ids) < 2:
        return {tid: "team_a" for tid in track_ids}

    mean_colors = np.array([np.mean(colors_by_track[tid], axis=0) for tid in track_ids])

    k = min(2, len(track_ids))
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(mean_colors)

    # Label the cluster with more members "team_a" just for stable, readable output.
    labels = km.labels_
    counts = np.bincount(labels, minlength=k)
    cluster_name = {int(np.argmax(counts)): "team_a"}
    for c in range(k):
        if c not in cluster_name:
            cluster_name[c] = "team_b"

    return {tid: cluster_name[int(lbl)] for tid, lbl in zip(track_ids, labels)}
