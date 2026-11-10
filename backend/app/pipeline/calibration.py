"""
Maps pixel coordinates to real-world pitch coordinates (meters).

The user clicks the 4 pitch corners on the stitched panorama, in order:
top-left, top-right, bottom-right, bottom-left (as seen in the panorama), and
confirms the pitch's real dimensions. That gives panorama px -> pitch meters.
Combined with each frame's camera homography (frame px -> mosaic px) and the
panorama transform (mosaic px -> panorama px), every frame gets its own
frame px -> pitch meters mapping, so the camera is free to pan and zoom.
"""
import numpy as np
import cv2


def compute_homography(
    image_points: list[list[float]],
    pitch_length_m: float,
    pitch_width_m: float,
) -> list[list[float]]:
    """image_points: 4 [x, y] pixel points in order TL, TR, BR, BL.

    Pitch coordinate system: origin at TL corner, X along length (0..pitch_length_m),
    Y along width (0..pitch_width_m). The goals sit at X=0 ("left") and X=pitch_length_m ("right").
    """
    if len(image_points) != 4:
        raise ValueError("exactly 4 corner points are required")

    src = np.array(image_points, dtype=np.float32)
    edges = np.roll(src, -1, axis=0) - src
    turns = [float(np.cross(edges[i], edges[(i + 1) % 4])) for i in range(4)]
    span = float(np.ptp(src[:, 0]) * np.ptp(src[:, 1]))
    if span <= 0 or not (all(t > 0 for t in turns) or all(t < 0 for t in turns)) or min(abs(t) for t in turns) < 1e-3 * span:
        raise ValueError("the 4 corners must form a convex shape, clicked in order TL, TR, BR, BL")
    dst = np.array(
        [
            [0.0, 0.0],
            [pitch_length_m, 0.0],
            [pitch_length_m, pitch_width_m],
            [0.0, pitch_width_m],
        ],
        dtype=np.float32,
    )
    h, _ = cv2.findHomography(src, dst)
    if h is None:
        raise ValueError("corner points are degenerate (e.g. three of them on one line)")
    return h.tolist()


def frame_to_pitch_matrices(frames: list[dict], pano_to_pitch, mosaic_to_pano) -> list[np.ndarray | None]:
    """Per-frame 3x3 matrices mapping frame px -> pitch meters (None where the
    camera could not be registered for that frame)."""
    base = np.asarray(pano_to_pitch, dtype=np.float64) @ np.asarray(mosaic_to_pano, dtype=np.float64)
    return [None if f["H"] is None else base @ np.asarray(f["H"], dtype=np.float64) for f in frames]


def pixel_to_pitch(h, x: float, y: float) -> tuple[float, float]:
    H = np.asarray(h, dtype=np.float64)
    q = H @ np.array([x, y, 1.0])
    return float(q[0] / q[2]), float(q[1] / q[2])
