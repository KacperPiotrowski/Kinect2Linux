"""CPU-only RTMPose-s body adapter using rtmlib; weights must exist locally.

This module is imported ONLY when TrackingSession.process() first needs it.
It never opens Kinect USB, imports MediaPipe, or downloads models. The caller
supplies an already decoded, BGR uint8 image from the broker's RGB stream.
"""
from __future__ import annotations

from pathlib import Path
from math import isfinite
import os

from .tracking import Keypoint, TrackedSubject, TrackingResult, TrackingUnavailable

ROOT = Path(__file__).resolve().parents[3]
DETECTOR = ROOT / "models" / "rtmpose-body-det-tiny.onnx"
POSE = ROOT / "models" / "rtmpose-body-pose-s.onnx"

# Hardware-tested Basic CPU profile: 4 intra-op threads and idle spinning OFF.
# Read only on first model creation, preserving TrackingSession's lazy behavior.
# Overrides 0/0 restore the legacy RTMLib defaults for A/B measurements.
THREADS_ENV = "KINECT2_BODY_ORT_THREADS"
NO_SPIN_ENV = "KINECT2_BODY_ORT_NO_SPIN"


def _cpu_tuning() -> tuple[int, bool]:
    raw = os.environ.get(THREADS_ENV, "4")
    if not raw.isascii() or not raw.isdecimal():
        raise TrackingUnavailable(f"{THREADS_ENV} must be an integer from 0 to 32")
    threads = int(raw)
    if not 0 <= threads <= 32:
        raise TrackingUnavailable(f"{THREADS_ENV} must be an integer from 0 to 32")
    no_spin = os.environ.get(NO_SPIN_ENV, "1")
    if no_spin not in ("0", "1"):
        raise TrackingUnavailable(f"{NO_SPIN_ENV} must be 0 or 1")
    return threads, no_spin == "1"


def _retune_ort_sessions(body: object, threads: int, no_spin: bool) -> None:
    """Rebuild ONLY the two RTMLib model sessions with explicit ORT options.

    RTMLib 0.0.16 creates CPU InferenceSession without exposing SessionOptions.
    Replacing these *session objects*, not inference algorithms, keeps its
    YOLOX and RTMPose preprocessing/postprocessing entirely unchanged.

    This first experimental approach constructs default sessions briefly and
    replaces them immediately. No global monkeypatch, no broker modifications.
    """
    if not threads and not no_spin:
        return
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise TrackingUnavailable("Install optional onnxruntime first.") from exc
    sessions = (
        (getattr(body, "det_model", None), DETECTOR),
        (getattr(body, "pose_model", None), POSE),
    )
    if any(tool is None or not hasattr(tool, "session") for tool, _ in sessions):
        raise TrackingUnavailable(
            "Unsupported RTMLib Body API; refusing to tune unknown session layout."
        )
    opts = ort.SessionOptions()
    if threads:
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if no_spin:
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
        opts.add_session_config_entry("session.inter_op.allow_spinning", "0")
    for tool, path in sessions:
        # Release the default, potentially fully-affinitized thread pool
        # before creating the replacement. Existing preprocessing is retained.
        old = tool.session
        tool.session = None
        del old
        try:
            tool.session = ort.InferenceSession(
                str(path), sess_options=opts, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise TrackingUnavailable(
                f"Cannot initialize tuned ONNX Runtime model {path.name}"
            ) from exc
    print(f"[kinect2-body] CPU ONNX sessions configured: "
          f"intra_threads={threads or 'auto'} spin={'off' if no_spin else 'default'}",
          flush=True)


# COCO-17 order, left/right kept distinct.
COCO_NAMES = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)


class RTMPoseBody:
    def __init__(self) -> None:
        threads, no_spin = _cpu_tuning()
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
        _retune_ort_sessions(self._body, threads, no_spin)

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
                if not (0.0 <= cx < w and 0.0 <= cy < h):
                    # A keypoint guessed OUTSIDE the camera FOV must not be
                    # treated as a valid joint after coordinate clamping.
                    score = 0.0
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
