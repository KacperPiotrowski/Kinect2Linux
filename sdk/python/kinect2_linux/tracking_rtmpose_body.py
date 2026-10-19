"""CPU-only RTMPose-s body adapter using rtmlib; weights must exist locally.

This module is imported ONLY when TrackingSession.process() first needs it.
It never opens Kinect USB, imports MediaPipe, or downloads models. The caller
supplies an already decoded, BGR uint8 image from the broker's RGB stream.
"""
from __future__ import annotations

from pathlib import Path
from math import isfinite

from .tracking import Keypoint, TrackedSubject, TrackingResult, TrackingUnavailable

ROOT = Path(__file__).resolve().parents[3]
DETECTOR = ROOT / "models" / "rtmpose-body-det-tiny.onnx"
POSE = ROOT / "models" / "rtmpose-body-pose-s.onnx"

# COCO-17 order, left/right kept distinct.
COCO_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)


class RTMPoseBody:
    def __init__(self) -> None:
        # Prevent rtmlib's built-in network downloader from being invoked.
        for path in (DETECTOR, POSE):
            if not path.is_file() or path.is_symlink():
                raise TrackingUnavailable(
                    f"Missing local model: {path.name}. "
                    "Run: python3 tools/prepare_rtmpose_body.py --download"
                )
        try:
            from rtmlib import Body
        except ImportError as exc:
            raise TrackingUnavailable(
                "Missing optional rtmlib. Install it in an isolated venv; "
                "see docs/BODY-BASIC-CPU.md."
            ) from exc
        self._body = Body(
            det=str(DETECTOR),
            det_input_size=(416, 416),
            pose=str(POSE),
            pose_input_size=(192, 256),
            backend="onnxruntime",
            device="cpu",
        )

    def process(self, frame: object) -> TrackingResult:
        # The real runtime may be absent in offline tests, import on first use.
        import numpy as np
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
            raise TypeError("RTMPose requires an OpenCV BGR uint8 ndarray.")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("RTMPose requires an HxWx3 BGR image.")
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            raise ValueError("Empty RGB frame.")
        points, scores = self._body(np.ascontiguousarray(frame))
        points = np.asarray(points)
        scores = np.asarray(scores)
        if points.size == 0:
            return TrackingResult(task="body", subjects=())
        if points.shape == (17, 2):
            points = points[None, ...]
        if scores.shape == (17,):
            scores = scores[None, ...]
        if (points.ndim != 3 or points.shape[1:] != (17, 2)
                or scores.shape != points.shape[:2]):
            raise ValueError("Unexpected RTMPose keypoint or confidence shape.")
        subjects = []
        for person_pts, person_scores in zip(points, scores):
            joints = []
            for name, (x, y), confidence in zip(
                COCO_NAMES, person_pts, person_scores
            ):
                cx, cy, score = float(x), float(y), float(confidence)
                if not all(isfinite(v) for v in (cx, cy, score)):
                    # Do not produce NaN coordinates in public results.
                    cx, cy, score = 0.0, 0.0, 0.0
                joints.append(Keypoint(
                    name=name,
                    x=min(1.0, max(0.0, cx / w)),
                    y=min(1.0, max(0.0, cy / h)),
                    confidence=min(1.0, max(0.0, score)),
                ))
            subjects.append(TrackedSubject(kind="person", keypoints=tuple(joints)))
        return TrackingResult(task="body", subjects=tuple(subjects))

    def close(self) -> None:
        self._body = None


def create_tracker() -> RTMPoseBody:
    return RTMPoseBody()
