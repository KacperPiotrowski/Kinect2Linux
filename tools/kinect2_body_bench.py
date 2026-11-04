#!/usr/bin/env python3
"""Actual CPU body-inference benchmark on a single real Kinect RGB snapshot.

Runs NO Qt, GUI, webcam/V4L2, GPU, network downloads, recording or USB access.
Takes one volatile RGB snapshot from the established per-user broker only.
Use a person visible in the image for representative detector+pose timings.
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
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux.frame_client import FrameClient  # noqa: E402


def describe(samples: list[float]) -> str:
    """Warm-cache, sequential per-inference latency; not GUI frame rate."""
    if not samples:
        return "no samples"
    ordered = sorted(samples)
    median = statistics.median(ordered)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    return (
        f"median={median:.1f}ms p95={p95:.1f}ms "
        f"best={ordered[0]:.1f}ms "
        f"equiv_sequential_fps={1000.0 / median:.1f}"
    )


def take_rgb():
    import numpy as np

    with FrameClient("rgb", timeout=4.0) as camera:
        frame, _ = camera.receive_latest(max_pending=16)
        with frame:
            # BGRX from broker. Keep an owned 960x540 BGR snapshot in RAM.
            borrowed = frame.as_numpy(copy=False)
            try:
                return np.ascontiguousarray(borrowed[::2, ::2, :3])
            finally:
                del borrowed


def run_benchmark(*, warmup: int, runs: int) -> int:
    from kinect2_linux.tracking_rtmpose_body import RTMPoseBody

    print("Kinect2 Body CPU benchmark: no model/driver changes, no file output.")
    print(f"ORT threads={os.getenv('KINECT2_BODY_ORT_THREADS', '1')} "
          f"no_spin={os.getenv('KINECT2_BODY_ORT_NO_SPIN', '1')} "
          f"warmup={warmup} measured={runs}", flush=True)
    frame = take_rgb()
    print(f"Captured one owned in-memory RGB sample: {frame.shape[1]}x"
          f"{frame.shape[0]} BGR", flush=True)

    init_start = time.perf_counter()
    tracker = RTMPoseBody()  # errors if local ONNX files or runtime are missing
    try:
        print(f"Model initialization={(time.perf_counter()-init_start)*1000:.0f}ms")
        for _ in range(warmup):
            tracker.process(frame)
        samples = []
        people = set()
        for _ in range(runs):
            start = time.perf_counter()
            result = tracker.process(frame)
            samples.append((time.perf_counter() - start) * 1000)
            people.add(len(result.subjects))
        print("Full YOLOX + RTMPose + SDK adapter:", describe(samples))
        print("Detected person counts in cached sample:", sorted(people))
        if not any(people):
            print("WARNING: No person detected. Move into the camera view "
                  "before benchmarking; no-person results may be misleading.")

        # Explicit stage timings using pinned rtmlib 0.0.16 Body internals.
        # This is diagnostic only; Studio continues to use public TrackingSession.
        body = tracker._body
        for _ in range(warmup):
            boxes = body.det_model(frame)
            body.pose_model(frame, bboxes=boxes)
        detector_ms = []
        pose_ms = []
        for _ in range(runs):
            start = time.perf_counter()
            boxes = body.det_model(frame)
            detector_ms.append((time.perf_counter() - start) * 1000)
            start = time.perf_counter()
            body.pose_model(frame, bboxes=boxes)
            pose_ms.append((time.perf_counter() - start) * 1000)
        print("YOLOX person detector:          ", describe(detector_ms))
        print("RTMPose joint estimation:       ", describe(pose_ms))
        print("Stages share a frame but run sequentially. Values are measured "
              "CPU times, not predicted camera FPS.")
    finally:
        tracker.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if not (0 <= args.warmup <= 30 and 5 <= args.runs <= 200):
        parser.error("warmup must be 0..30, runs 5..200")
    if os.geteuid() == 0:
        parser.error("run as your desktop user, never sudo")
    try:
        return run_benchmark(warmup=args.warmup, runs=args.runs)
    except (OSError, RuntimeError, ImportError, ValueError, TypeError) as exc:
        print(f"Benchmark unavailable: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
