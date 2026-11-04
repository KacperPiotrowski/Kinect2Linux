#!/usr/bin/env python3
"""Measure broker frame delivery independently from Qt/GPU/RTMPose.

Does not open physical USB, modify services, decode pixels or write files.
Concurrent RGB/IR/Depth subscriptions match Studio's three-client workload.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux.frame_client import FrameClient, FrameTimeoutError  # noqa: E402


def sample_stream(kind: str, *, seconds: float, warmup: float):
    with FrameClient(kind, timeout=1.0) as stream:
        end_warmup = time.monotonic() + warmup
        while time.monotonic() < end_warmup:
            try:
                frame, _ = stream.receive_latest(max_pending=16)
                frame.close()
            except FrameTimeoutError:
                continue
        started = time.monotonic()
        count = 0
        skipped_total = 0
        ages_ms = []
        timeouts = 0
        while time.monotonic() - started < seconds:
            try:
                frame, skipped = stream.receive_latest(max_pending=16)
            except FrameTimeoutError:
                timeouts += 1
                continue
            try:
                # Broker uses host monotonic clock, not sensor exposure time.
                age = max(0.0, ((time.monotonic_ns() // 1000)
                                 - frame.host_time_us) / 1000.0)
                ages_ms.append(age)
                count += 1
                skipped_total += skipped
            finally:
                frame.close()
        elapsed = time.monotonic() - started
        return {
            "kind": kind,
            "received": count,
            "fps": count / elapsed,
            "skipped": skipped_total,
            "timeouts": timeouts,
            "median_age_ms": statistics.median(ages_ms) if ages_ms else None,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--warmup", type=float, default=2.0)
    args = ap.parse_args()
    if not (2.0 <= args.seconds <= 60.0 and 0 <= args.warmup <= 10.0):
        ap.error("seconds must be 2..60; warmup must be 0..10")
    print("Independent broker delivery probe (no Qt, no AI, no USB open).",
          flush=True)
    print("The results are subscriber delivery FPS, NOT native sensor FPS.",
          flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            kind: pool.submit(sample_stream, kind,
                              seconds=args.seconds, warmup=args.warmup)
            for kind in ("rgb", "ir", "depth")
        }
        failed = False
        for kind, future in futures.items():
            try:
                row = future.result()
                age = (f"{row['median_age_ms']:.0f}ms"
                       if row["median_age_ms"] is not None else "n/a")
                print(f"{kind.upper():5s}: {row['fps']:5.1f} fps | "
                      f"frames={row['received']} | "
                      f"queue_skips={row['skipped']} | "
                      f"timeouts={row['timeouts']} | "
                      f"median publish-to-receive={age}")
            except Exception as exc:
                failed = True
                print(f"{kind.upper():5s}: unavailable ({type(exc).__name__}: "
                      f"{exc})", file=sys.stderr)
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
