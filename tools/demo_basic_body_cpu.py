#!/usr/bin/env python3
"""Experimental Kinect v2 Basic CPU skeleton preview via a broker RGB subscriber.

Never opens USB separately. Needs a running --auto-streams --frame-preview
broker, optional rtmlib, and two explicitly provisioned ONNX models.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk/python"))

from kinect2_linux.tracking import TrackingSession, TrackingUnavailable  # noqa: E402
from kinect2_linux.frame_client import FrameClient, FrameTimeoutError  # noqa: E402

# COCO-17 indices. Shoulder / hip crossbars plus one virtual spine
# replace the former shoulder/hip rectangle (the "square torso" effect).
# The midpoints are VISUALIZATION ONLY: not predicted / measured joints.
BONES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
)


def visible_joint(point, min_score: float) -> bool:
    """Only draw finite, confidently localized joints inside the RGB frame."""
    score = point.confidence
    return (
        score is not None and math.isfinite(score) and score >= min_score
        and math.isfinite(point.x) and math.isfinite(point.y)
        and 0.0 <= point.x <= 1.0 and 0.0 <= point.y <= 1.0
    )


def draw_body(cv2, image, result, *, min_score=0.45):
    h, w = image.shape[:2]

    def xy(point):
        return (round(point.x * (w - 1)), round(point.y * (h - 1)))

    for subject in result.subjects:
        pts = subject.keypoints
        if len(pts) != 17:
            continue
        for a, b in BONES:
            if not (visible_joint(pts[a], min_score)
                    and visible_joint(pts[b], min_score)):
                continue
            cv2.line(image, xy(pts[a]), xy(pts[b]), (0, 255, 0), 2)

        # Draw a natural-looking center spine only when all four torso
        # landmarks are reliable. Never hallucinate missing hips/legs.
        if all(visible_joint(pts[i], min_score) for i in (5, 6, 11, 12)):
            shoulders = ((pts[5].x + pts[6].x) / 2,
                         (pts[5].y + pts[6].y) / 2)
            hips = ((pts[11].x + pts[12].x) / 2,
                    (pts[11].y + pts[12].y) / 2)
            a = (round(shoulders[0] * (w - 1)),
                 round(shoulders[1] * (h - 1)))
            b = (round(hips[0] * (w - 1)),
                 round(hips[1] * (h - 1)))
            cv2.line(image, a, b, (0, 255, 0), 2)

        for point in pts:
            if visible_joint(point, min_score):
                cv2.circle(image, xy(point), 3, (0, 255, 255), -1)
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
    ap.add_argument("--ort-threads", type=int, choices=(0, 1, 2, 4, 8, 12, 16),
                    default=4, help="CPU intra-op threads per ONNX session (Basic default: 4; 0=RTMLib auto).")
    ap.add_argument("--ort-no-spin", dest="ort_no_spin", action="store_true",
                    default=True, help="Disable idle CPU spinning (Basic default).")
    ap.add_argument("--ort-spin", dest="ort_no_spin", action="store_false",
                    help="Restore idle CPU spinning for legacy A/B comparison.")
    args = ap.parse_args()
    # Only the current preview process. The tracking adapter reads the values
    # lazily on its first process(frame); the Kinect broker is untouched.
    os.environ["KINECT2_BODY_ORT_THREADS"] = str(args.ort_threads)
    os.environ["KINECT2_BODY_ORT_NO_SPIN"] = "1" if args.ort_no_spin else "0"
    if args.width < 320 or args.width > 960 or args.max_frames < 0:
        ap.error("width must be 320..960; max-frames must be >= 0.")
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("Missing OpenCV/NumPy: see docs/BODY-BASIC-CPU.md", file=sys.stderr)
        return 2
    print(f"ONNX thread test: intra_threads={args.ort_threads or 'default'}, "
          f"idle_spinning={'off' if args.ort_no_spin else 'default'}", flush=True)
    name = "Kinect2Linux Basic | Body CPU (Q/Esc/X to exit)"
    if not args.no_preview:
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(name, 960, 540)

    latencies = []
    wait_times = []
    resize_times = []
    render_times = []
    total = 0
    skipped_total = 0
    started = time.perf_counter()
    cpu_started = time.process_time()
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
                    recv_start = time.perf_counter()
                    try:
                        frame, skipped = rgb.receive_latest()
                    except FrameTimeoutError:
                        continue
                    recv_end = time.perf_counter()
                    wait_times.append((recv_end - recv_start) * 1000.0)
                    skipped_total += skipped
                    with frame:
                        data = np.frombuffer(frame.mapping, dtype=np.uint8)
                        image = cv2.resize(
                            data.reshape(frame.height, frame.width, 4)[:, :, :3],
                            (args.width, round(frame.height * args.width / frame.width)),
                            interpolation=cv2.INTER_AREA,
                        )
                        del data
                    resize_end = time.perf_counter()
                    resize_times.append((resize_end - recv_end) * 1000.0)
                    result = tracker.process(image)
                    infer_end = time.perf_counter()
                    elapsed_ms = (infer_end - resize_end) * 1000.0
                    latencies.append(elapsed_ms)
                    total += 1
                    draw_start = time.perf_counter()
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
                    render_times.append((time.perf_counter() - draw_start) * 1000.0)
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
        total_wall_s = max(1e-6, time.perf_counter() - started)
        process_cpu_percent = 100.0 * max(
            0.0, time.process_time() - cpu_started) / total_wall_s
        print(f"completed={total}, inferred_fps="
              f"{total/total_wall_s:.2f}, "
              f"median_inference_ms={statistics.median(latencies):.1f}, "
              f"worst_inference_ms={max(latencies):.1f}, "
              f"skipped_queued={skipped_total}")
        # The first inference includes ONNX model loading: report it separately
        # instead of letting warm/steady performance be confused with startup.
        warm = latencies[1:]
        print(f"average_process_cpu_percent_of_one_core={process_cpu_percent:.1f}")
        print(f"first_inference_including_model_load_ms={latencies[0]:.1f}")
        if warm:
            print(f"warm_median_inference_ms={statistics.median(warm):.1f} "
                  f"warm_worst_inference_ms={max(warm):.1f}")
        print(f"median_frame_wait_ms={statistics.median(wait_times):.1f} "
              f"median_bgr_resize_ms={statistics.median(resize_times):.1f} "
              f"median_preview_ms={statistics.median(render_times):.1f}")
        print("Frame wait includes broker RGB delivery and receive_latest; "
              "FPS includes startup and all waiting. None are end-to-end "
              "sensor exposure-to-screen latency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
