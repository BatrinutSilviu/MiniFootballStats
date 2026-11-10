"""
Camera motion estimation for a moving / panning camera.

The pitch is a plane, so any two views of it are related by a homography
(exactly, whatever the camera does, for points on the ground). We estimate,
for every sampled frame, the homography mapping that frame's pixels into a
common "mosaic" coordinate system — the pixel space of the very first frame.

Drift is limited by matching each frame against stored keyframes (the ones
closest to where the camera is predicted to look) rather than chaining
frame-to-frame. Player boxes are masked out so features come from the pitch
markings, surface texture and surroundings, not from moving people.

The keyframes are also stitched into a panorama, on which the user clicks the
pitch corners once — the camera never needs to see the whole pitch in one shot.
A static camera simply yields identity homographies and a one-frame panorama.
"""
import cv2
import numpy as np

from app.config import (
    CAMERA_WORK_WIDTH,
    CAMERA_MIN_INLIERS,
    KEYFRAME_MIN_INLIERS,
    PANORAMA_MAX_WIDTH,
)

_RATIO_TEST = 0.75
_CANDIDATE_KEYFRAMES = 3


class _Keyframe:
    def __init__(self, kp, des, H_to_mosaic, jpeg: bytes, center):
        self.kp = kp
        self.des = des
        self.H = H_to_mosaic  # full-res keyframe px -> mosaic px
        self.jpeg = jpeg  # downscaled image kept compressed for the panorama
        self.center = center  # keyframe image center, in mosaic px


class CameraTracker:
    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=2500, fastThreshold=12)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.keyframes: list[_Keyframe] = []
        self.prev = None  # (kp, des, H) of the last registered frame
        self.full_size = None  # (w, h) of original frames
        self.scale = None  # work-size / full-size
        self.registered = 0
        self.total = 0

    # -- public ---------------------------------------------------------------

    def update(self, frame: np.ndarray, person_boxes: list[list[float]]) -> list[list[float]] | None:
        """Returns the 3x3 frame->mosaic homography (full-res px), or None if this
        frame could not be registered (motion blur, a cut, too few features)."""
        self.total += 1
        h, w = frame.shape[:2]
        if self.full_size is None:
            self.full_size = (w, h)
            self.scale = CAMERA_WORK_WIDTH / w

        small = cv2.resize(frame, (CAMERA_WORK_WIDTH, int(round(h * self.scale))))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        mask = self._mask(gray.shape, person_boxes)
        kp, des = self.orb.detectAndCompute(gray, mask)
        if des is None or len(kp) < CAMERA_MIN_INLIERS:
            return None

        if not self.keyframes:
            H = np.eye(3)
            self._add_keyframe(kp, des, H, small)
            self.prev = (kp, des, H)
            self.registered += 1
            return H.tolist()

        best = None  # (inliers, H_frame_to_mosaic, matched keyframe or None)
        for kf in self._candidate_keyframes():
            res = self._register(kp, des, kf.kp, kf.des)
            if res is not None and (best is None or res[0] > best[0]):
                best = (res[0], kf.H @ res[1], kf)

        if (best is None or best[0] < KEYFRAME_MIN_INLIERS) and self.prev is not None:
            res = self._register(kp, des, self.prev[0], self.prev[1])
            if res is not None and (best is None or res[0] > best[0]):
                best = (res[0], self.prev[2] @ res[1], None)

        if best is None or not _plausible(best[1], self.full_size):
            return None

        inliers, H, kf = best
        if kf is None or inliers < KEYFRAME_MIN_INLIERS:
            self._add_keyframe(kp, des, H, small)
        self.prev = (kp, des, H)
        self.registered += 1
        return H.tolist()

    def quality(self) -> dict:
        return {
            "registered_frames": self.registered,
            "total_frames": self.total,
            "registration_rate": round(self.registered / self.total, 3) if self.total else 0.0,
            "keyframes": len(self.keyframes),
        }

    def build_panorama(self) -> tuple[np.ndarray, list[list[float]]] | None:
        """Stitches keyframes into one image. Returns (image, P) where P maps
        mosaic px -> panorama px."""
        if not self.keyframes:
            return None
        w, h = self.full_size
        corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
        pts = np.vstack([_apply(kf.H, corners) for kf in self.keyframes])
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        s = min(1.0, PANORAMA_MAX_WIDTH / max(1.0, x1 - x0))
        pano_w, pano_h = int(np.ceil((x1 - x0) * s)), int(np.ceil((y1 - y0) * s))
        P = np.array([[s, 0, -x0 * s], [0, s, -y0 * s], [0, 0, 1]])

        acc = np.zeros((pano_h, pano_w, 3), np.float32)
        wsum = np.zeros((pano_h, pano_w), np.float32)
        small_to_full = np.diag([1 / self.scale, 1 / self.scale, 1.0])
        for kf in self.keyframes:
            img = cv2.imdecode(np.frombuffer(kf.jpeg, np.uint8), cv2.IMREAD_COLOR)
            # feather: pixels near the image center count more, which hides seams
            sh, sw = img.shape[:2]
            yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
            weight = (1 - np.abs(xx / sw * 2 - 1)) * (1 - np.abs(yy / sh * 2 - 1)) + 1e-3
            M = P @ kf.H @ small_to_full
            acc += cv2.warpPerspective(img.astype(np.float32) * weight[..., None], M, (pano_w, pano_h))
            wsum += cv2.warpPerspective(weight, M, (pano_w, pano_h))
        pano = (acc / np.maximum(wsum, 1e-6)[..., None]).clip(0, 255).astype(np.uint8)
        return pano, P.tolist()

    # -- internals ------------------------------------------------------------

    def _mask(self, shape, person_boxes):
        mask = np.full(shape, 255, np.uint8)
        for x1, y1, x2, y2 in person_boxes:
            pad_x, pad_y = (x2 - x1) * 0.15, (y2 - y1) * 0.1
            cv2.rectangle(
                mask,
                (int((x1 - pad_x) * self.scale), int((y1 - pad_y) * self.scale)),
                (int((x2 + pad_x) * self.scale), int((y2 + pad_y) * self.scale)),
                0,
                -1,
            )
        return mask

    def _register(self, kp, des, kp_ref, des_ref):
        """Homography (full-res px) mapping the current frame onto the reference."""
        if des_ref is None or len(des_ref) < 2:
            return None
        pairs = self.matcher.knnMatch(des, des_ref, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < _RATIO_TEST * n.distance]
        if len(good) < CAMERA_MIN_INLIERS:
            return None
        src = np.float32([kp[m.queryIdx].pt for m in good])
        dst = np.float32([kp_ref[m.trainIdx].pt for m in good])
        Hs, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if Hs is None:
            return None
        n_inliers = int(inl.sum())
        if n_inliers < CAMERA_MIN_INLIERS:
            return None
        S = np.diag([self.scale, self.scale, 1.0])
        return n_inliers, np.linalg.inv(S) @ Hs @ S

    def _candidate_keyframes(self) -> list[_Keyframe]:
        if self.prev is None:
            return self.keyframes[-_CANDIDATE_KEYFRAMES:]
        w, h = self.full_size
        c = _apply(self.prev[2], np.array([[w / 2, h / 2]]))[0]
        ranked = sorted(self.keyframes, key=lambda kf: np.hypot(*(kf.center - c)))
        return ranked[:_CANDIDATE_KEYFRAMES]

    def _add_keyframe(self, kp, des, H, small):
        w, h = self.full_size
        center = _apply(H, np.array([[w / 2, h / 2]]))[0]
        ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        self.keyframes.append(_Keyframe(kp, des, np.asarray(H), jpeg.tobytes(), center))


def _apply(H, pts: np.ndarray) -> np.ndarray:
    p = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(H).T
    return p[:, :2] / p[:, 2:3]


def _plausible(H, full_size) -> bool:
    """Rejects degenerate homographies (flips, extreme zoom, huge perspective)."""
    H = np.asarray(H)
    w, h = full_size
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
    p = np.hstack([corners, np.ones((4, 1))]) @ H.T
    if np.any(p[:, 2] <= 0):
        return False
    q = p[:, :2] / p[:, 2:3]
    area = 0.5 * abs(np.dot(q[:, 0], np.roll(q[:, 1], 1)) - np.dot(q[:, 1], np.roll(q[:, 0], 1)))
    ratio = area / (w * h)
    if not 0.1 < ratio < 10:
        return False
    # the warped frame must stay a convex quad (no self-intersection / flip)
    cross = [np.cross(q[(i + 1) % 4] - q[i], q[(i + 2) % 4] - q[(i + 1) % 4]) for i in range(4)]
    return all(c > 0 for c in cross) or all(c < 0 for c in cross)

