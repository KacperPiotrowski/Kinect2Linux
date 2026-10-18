#!/usr/bin/env python3
"""Optional MediaPipe face landmarks from the Kinect2 C++ broker's RGB subscriber.

Independent consumer: no USB access, no biometrics persisted, no Howdy/PAM.
Face landmarks are NOT face identity recognition, liveness or authentication.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux.frame_client import FrameClient, FrameTimeoutError  # noqa: E402


def rgb_from_snapshot(frame, *, scale: int = 3) -> np.ndarray:
    """Copy broker BGRX (not RGBA) into contiguous SRGB, optionally decimating.

    The returned array owns its bytes: the read-only memfd can be unmapped
    immediately after this function returns, before MediaPipe inference.
    """
    if frame.kind != "rgb" or frame.bytes_per_pixel != 4:
        raise ValueError("expected a broker RGB BGRX frame")
    if type(scale) is not int or scale not in (1, 2, 3, 4):
        raise ValueError("scale must be 1, 2, 3 or 4")
    native = np.frombuffer(frame.mapping, dtype=np.uint8).reshape(
        frame.height, frame.width, 4
    )
    return np.ascontiguousarray(native[::scale, ::scale, :3][:, :, ::-1])


def next_timestamp_ms(host_time_us: int, previous_ms: int) -> int:
    """Guarantee strictly increasing MediaPipe VIDEO timestamps."""
    stamp = host_time_us // 1000 if host_time_us > 0 else time.monotonic_ns() // 1_000_000
    return max(int(stamp), previous_ms + 1)


def overlay(cv2, rgb: np.ndarray, result, count: int) -> np.ndarray:
    """Draw sparse face-mesh points on an optional local preview only."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    for face in result.face_landmarks:
        for landmark in face[::4]:
            x, y = round(landmark.x * width), round(landmark.y * height)
            if 0 <= x < width and 0 <= y < height:
                cv2.circle(bgr, (x, y), 1, (0, 255, 80), -1)
    cv2.putText(bgr, f"Faces: {len(result.face_landmarks)} | frame: {count}",
                (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (255, 255, 255), 2, cv2.LINE_AA)
    return bgr


def run(args, mp, cv2=None) -> int:
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
    )
    count = 0
    idle = 0
    skipped_total = 0
    last_stamp = -1
    name = "Kinect2 / MediaPipe Face Landmarker"
    if cv2 is not None:
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    try:
        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
            # Only this RGB subscription is created. In automatic mode the
            # existing broker owns USB and starts/stops capture on demand.
            with FrameClient("rgb", timeout=2.0) as camera:
                while args.max_frames == 0 or count < args.max_frames:
                    if cv2 is not None:
                        key = cv2.waitKey(1) & 0xFF
                        if key in (27, ord("q")) or cv2.getWindowProperty(
                            name, cv2.WND_PROP_VISIBLE
                        ) <= 0:
                            break
                    try:
                        frame, skipped = camera.receive_latest()
                    except FrameTimeoutError:
                        idle += 1
                        if idle >= 3:
                            raise RuntimeError("no RGB frames after 6 seconds; check broker")
                        continue
                    idle = 0
                    skipped_total += skipped
                    with frame:
                        rgb = rgb_from_snapshot(frame, scale=args.scale)
                        last_stamp = next_timestamp_ms(frame.host_time_us, last_stamp)
                    # No Kinect memfd is held across model inference.
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = detector.detect_for_video(image, last_stamp)
                    count += 1
                    if count == 1 or count % 10 == 0:
                        first = len(result.face_landmarks[0]) if result.face_landmarks else 0
                        print(f"frame={count} faces={len(result.face_landmarks)} "
                              f"landmarks={first} skipped={skipped_total}", flush=True)
                    if cv2 is not None:
                        # Closing X on KDE should end this client only; it
                        # must never stop the shared broker or other viewers.
                        if cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) <= 0:
                            break
                        cv2.imshow(name, overlay(cv2, rgb, result, count))
    finally:
        if cv2 is not None:
            cv2.destroyAllWindows()
    print(f"Finished: {count} frames processed, {skipped_total} stale packets skipped.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "face_landmarker.task")
    parser.add_argument("--check", action="store_true", help="check optional package/API/model without opening Kinect")
    parser.add_argument("--preview", action="store_true", help="show local face mesh in an OpenCV GUI window")
    parser.add_argument("--scale", type=int, choices=(1, 2, 3, 4), default=3,
                        help="1 = full RGB; 3 = 640x360 for low-cost inference (default)")
    parser.add_argument("--max-frames", type=int, default=90,
                        help="stop after N frames (default 90; 0 = unlimited)")
    args = parser.parse_args(argv)
    if args.max_frames < 0:
        parser.error("--max-frames must be non-negative")
    try:
        import mediapipe as mp
    except (ImportError, OSError) as exc:
        parser.error(f"MediaPipe unavailable: {exc}. Install optional requirements in a virtualenv")
    try:
        _ = mp.tasks.vision.FaceLandmarker
    except AttributeError:
        parser.error("MediaPipe Python package has no Tasks FaceLandmarker API")
    if not args.model.is_file() or args.model.stat().st_size < 100_000:
        parser.error(f"Missing/invalid Face Landmarker model: {args.model}. See docs/MEDIAPIPE.md")
    cv2 = None
    if args.preview:
        try:
            import cv2
        except ImportError:
            parser.error("--preview needs OpenCV with HighGUI (not opencv-python-headless)")
    print(f"MediaPipe {mp.__version__} | model: {args.model} | "
          f"preview: {'yes' if args.preview else 'no'}", flush=True)
    if args.check:
        print("Preflight passed; broker and physical Kinect were NOT tested.")
        return 0
    try:
        return run(args, mp, cv2)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Face demo failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped by user; other broker clients remain connected.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
