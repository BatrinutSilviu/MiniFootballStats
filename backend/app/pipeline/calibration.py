"""
Maps pixel coordinates from the fixed camera to real-world pitch coordinates (meters).

Assumes the user has clicked the 4 corners of the pitch, in order:
top-left, top-right, bottom-right, bottom-left (as seen in the video frame),
and knows the pitch's real dimensions. A single homography is computed and
reused for the whole match, which is only valid for a STATIC camera.
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
    Y along width (0..pitch_width_m).
    """
    if len(image_points) != 4:
        raise ValueError("exactly 4 corner points are required")

    src = np.array(image_points, dtype=np.float32)
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
    return h.tolist()


def pixel_to_pitch(h: list[list[float]], x: float, y: float) -> tuple[float, float]:
    H = np.array(h, dtype=np.float64)
    p = np.array([x, y, 1.0])
    q = H @ p
    q /= q[2]
    return float(q[0]), float(q[1])
