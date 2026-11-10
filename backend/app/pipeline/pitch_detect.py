"""
Suggests the 4 pitch corners on the panorama, so the user only has to check
(and maybe nudge) them instead of clicking all four.

Heuristic, no model needed:
  1. the playing surface is the dominant saturated color in the lower-middle
     of the image (turf green, but also blue/red courts);
  2. the largest connected region of that color is the pitch area;
  3. inside it, the white line pixels give the pitch outline more precisely
     than the turf edge (turf usually runs on past the lines);
  4. the outline is simplified to a quadrilateral and ordered TL, TR, BR, BL.

Returns None when nothing pitch-like is found — the user then clicks as before.
"""
import cv2
import numpy as np


def _order(pts: np.ndarray) -> list[list[float]]:
    pts = pts.reshape(-1, 2).astype(float)
    s, d = pts.sum(1), pts[:, 0] - pts[:, 1]
    tl, br = pts[np.argmin(s)], pts[np.argmax(s)]
    tr, bl = pts[np.argmax(d)], pts[np.argmin(d)]
    return [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in (tl, tr, br, bl)]


def _quad(points: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(points.astype(np.float32))
    peri = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.12, 23):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return approx
        if len(approx) < 4:
            break
    # fall back: the 4 extreme points of the hull
    h = hull.reshape(-1, 2)
    s, d = h.sum(1), h[:, 0] - h[:, 1]
    return np.array([h[np.argmin(s)], h[np.argmax(d)], h[np.argmax(s)], h[np.argmin(d)]])


def suggest_corners(image: np.ndarray) -> list[list[float]] | None:
    h, w = image.shape[:2]
    scale = 800 / max(h, w) if max(h, w) > 800 else 1.0
    small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale != 1.0 else image
    sh, sw = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # 1. dominant surface hue, sampled where the pitch almost always is
    roi = hsv[int(sh * 0.4):int(sh * 0.9), int(sw * 0.2):int(sw * 0.8)].reshape(-1, 3)
    roi = roi[(roi[:, 1] > 50) & (roi[:, 2] > 40)]
    if len(roi) < 500:
        return None
    hist = np.bincount(roi[:, 0], minlength=180).astype(float)
    hist = np.convolve(np.r_[hist[-5:], hist, hist[:5]], np.ones(11) / 11, mode="same")[5:-5]
    hue = int(np.argmax(hist))

    diff = np.abs(hsv[:, :, 0].astype(int) - hue)
    diff = np.minimum(diff, 180 - diff)
    surface = ((diff <= 12) & (hsv[:, :, 1] > 40) & (hsv[:, :, 2] > 30)).astype(np.uint8) * 255
    k = max(3, sw // 160) | 1
    surface = cv2.morphologyEx(surface, cv2.MORPH_CLOSE, np.ones((k * 3, k * 3), np.uint8))
    surface = cv2.morphologyEx(surface, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))

    # 2. largest connected surface region
    n, labels, stats, _ = cv2.connectedComponentsWithStats(surface)
    if n <= 1:
        return None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[big, cv2.CC_STAT_AREA] < 0.12 * sh * sw:
        return None
    region = (labels == big).astype(np.uint8)
    hull = cv2.convexHull(cv2.findNonZero(region))
    area_mask = np.zeros_like(region)
    cv2.fillConvexPoly(area_mask, hull, 1)

    # 3. white lines inside the playing area
    white = (hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 170) & (area_mask > 0)
    white = cv2.morphologyEx(white.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    ys, xs = np.nonzero(white)
    pts = np.stack([xs, ys], 1) if len(xs) else np.empty((0, 2))
    use_lines = False
    if len(pts) > 200:
        lhull = cv2.convexHull(pts.astype(np.float32))
        use_lines = cv2.contourArea(lhull) >= 0.5 * cv2.contourArea(hull)
    quad = _quad(pts if use_lines else hull.reshape(-1, 2))
    if quad is None or cv2.contourArea(quad.astype(np.float32)) < 0.1 * sh * sw:
        return None
    return _order(quad / scale)
