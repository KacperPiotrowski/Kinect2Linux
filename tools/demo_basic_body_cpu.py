#!/usr/bin/env python3
"""Experimental Kinect v2 Basic CPU skeleton preview via a broker RGB subscriber.

Never opens USB separately. Needs a running --auto-streams --frame-preview
broker, optional rtmlib, and two explicitly provisioned ONNX models.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk/python"))

from kinect2_linux.tracking import TrackingSession, TrackingUnavailable  # noqa: E402
from kinect2_linux.frame_client import FrameClient, FrameTimeoutError  # noqa: E402

# COCO 17 keypoints indices. Do not connect left and right wrists, for example.
BONES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12), (11, 13), (13, 15),
    (12, 14), (14, 16),
)


def draw_body(cv2, image, result, *, min_score=0.3):
    h, w = image.shape[:2]
    for subject in result.subjects:
        pts = subject.keypoints
        for a, b in BONES:
            left, right = pts[a], pts[b]
            if (left.confidence or 0) < min_score or (right.confidence or 0) < min_score:
                continue
            pa = (round(left.x * (w - 1)), round(left.y * (h - 1)))
            pb = (round(right.x * (w - 1)), round(right.y * (h - 1)))
            cv2.line(image, pa, pb, (0, 255, 0), 2)
        for point in pts:
            if (point.confidence or 0) >= min_score:
                cv2.circle(image, (round(point.x * (w - 1)),
                                  round(point.y * (h - 1))), 3, (0, 255, 255), -1)
    return image


def window_open(cv2, name):
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) > 0
    except cv2.error:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-frames", type=int, default=0,
                    help="Stop automatically after N inferred RGB frames (0 = GUI until Q/Esc/X).")
    ap.add_argument("--no-preview", action="store_true",
                    help="Benchmark inference without opening a GUI window.")
    ap.add_argument("--width", type=int, default=960, help="RGB preview width (320..960).")
    args = ap.parse_args()
    if args.width < 320 or args.width > 960 or args.max_frames < 0:
        ap.error("width must be 320..960; max-frames must be >= 0.")
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("Missing OpenCV/NumPy: see docs/BODY-BASIC-CPU.md", file=sys.stderr)
        return 2
    name = "Kinect2Linux Basic | Body CPU (Q/Esc/X to exit)"
    if not args.no_preview:
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(name, 960, 540)

    latencies = []
    total = 0
    skipped_total = 0
    started = time.perf_counter()
    try:
        with TrackingSession("body", mode="basic") as tracker:
            with FrameClient("rgb", timeout=2.0) as rgb:
                print("Basic body CPU: subscribed to existing RGB broker, "
                      "models initialize on first frame.", flush=True)
                while True:
                    if not args.no_preview and (
                        cv2.waitKey(1) & 0xFF in (27, ord("q")) or not window_open(cv2, name)
                    ):
                        break
                    try:
                        frame, skipped = rgb.receive_latest()
                    except FrameTimeoutError:
                        continue
                    skipped_total += skipped
                    with frame:
                        data = np.frombuffer(frame.mapping, dtype=np.uint8)
                        image = cv2.resize(
                            data.reshape(frame.height, frame.width, 4)[:, :, :3],
                            (args.width, round(frame.height * args.width / frame.width)),
                            interpolation=cv2.INTER_AREA,
                        )
                        del data
                    tick = time.perf_counter()
                    result = tracker.process(image)
                    elapsed_ms = (time.perf_counter() - tick) * 1000.0
                    latencies.append(elapsed_ms)
                    total += 1
                    if not args.no_preview:
                        draw_body(cv2, image, result)
                        fps = total / max(1e-6, time.perf_counter() - started)
                        cv2.putText(
                            image, f"Basic Body CPU | people={len(result.subjects)} "
                            f"| {fps:.1f} inferred FPS | last={elapsed_ms:.0f}ms",
                            (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (255, 255, 255), 1, cv2.LINE_AA,
                        )
                        if not window_open(cv2, name):
                            break
                        cv2.imshow(name, image)
                    if total == 1 or total % 30 == 0:
                        print(f"frames={total} people={len(result.subjects)} "
                              f"last_inference_ms={elapsed_ms:.1f} "
                              f"queued_skipped={skipped_total}", flush=True)
                    if args.max_frames and total >= args.max_frames:
                        break
    except (TrackingUnavailable, OSError, ImportError) as exc:
        print(f"Body Basic unavailable: {exc}", file=sys.stderr)
        return 2
    finally:
        if not args.no_preview:
            cv2.destroyAllWindows()
    if latencies:
        print(f"completed={total}, inferred_fps="
              f"{total/max(1e-6, time.perf_counter()-started):.2f}, "
              f"median_inference_ms={statistics.median(latencies):.1f}, "
              f"worst_inference_ms={max(latencies):.1f}, "
              f"skipped_queued={skipped_total}")
        print("Inference times include first-model initialization; "
              "these are not end-to-end sensor latency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
