#!/usr/bin/env python3
"""Repeatable, post-warmup Kinect2 native capture benchmark.

Measures broker frame-counter *deltas* and process CPU use, not end-to-end
image delivery, video quality, camera FPS, or true hardware drop rate.
Hardware USB access is explicit and requires the opt-in broker.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import statistics
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux import BrokerClient  # noqa: E402

FRAME_KEYS = ("rgb", "ir", "depth")
MODES = (
    ("RGB A", {"rgb": True, "ir_depth": False}),
    ("RGB+IR+Depth A", {"rgb": True, "ir_depth": True}),
    ("IR+Depth", {"rgb": False, "ir_depth": True}),
    ("RGB+IR+Depth B", {"rgb": True, "ir_depth": True}),
    ("RGB B", {"rgb": True, "ir_depth": False}),
)


def process_cpu_seconds(pid: int) -> float | None:
    """Read broker user+system CPU seconds from /proc, without extra packages."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        # /proc/PID/stat field 2 is a parenthesized comm containing spaces.
        fields = stat[stat.rfind(")") + 2 :].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def peer_pid(socket_path: str) -> int | None:
    """Learn PID of the actual Unix-socket broker, not of a guessed process."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(2.0)
            conn.connect(socket_path)
            pid, uid, _gid = struct.unpack(
                "3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if uid != os.getuid():
                return None
            return pid
    except OSError:
        return None


def compute_result(
    name: str,
    before: dict,
    after: dict,
    elapsed: float,
    cpu_before: float | None,
    cpu_after: float | None,
) -> dict:
    """Pure calculation, so CI can test diagnostics with no Kinect."""
    if elapsed <= 0:
        raise ValueError("measurement interval must be positive")
    result = {"mode": name, "seconds": elapsed}
    for field in ("frame_counts", "sequence_gaps"):
        left, right = before.get(field), after.get(field)
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ValueError(f"broker lacks {field}; use the diagnostic branch")
        for key in FRAME_KEYS:
            first, last = left.get(key), right.get(key)
            if type(first) is not int or type(last) is not int or last < first:
                raise ValueError(f"invalid/reset {field}.{key} during measurement")
            delta = last - first
            result[f"{key}_frames" if field == "frame_counts" else f"{key}_gaps"] = delta
            if field == "frame_counts":
                result[f"{key}_fps"] = delta / elapsed
    result["cpu_percent"] = (
        max(0.0, cpu_after - cpu_before) / elapsed * 100.0
        if cpu_before is not None and cpu_after is not None else None
    )
    return result


def check_capture_status(status: dict, selection: dict) -> None:
    if status.get("streaming") is not True:
        raise RuntimeError("broker is not reporting active native capture")
    if status.get("selected") != selection:
        raise RuntimeError("broker stream selection changed during measurement")


def run_mode(
    client: BrokerClient, name: str, selection: dict,
    warmup: float, duration: float, pid: int | None,
) -> dict:
    client.start_streams(**selection)
    try:
        time.sleep(warmup)
        first = client.get_status()
        check_capture_status(first, selection)
        cpu_start = process_cpu_seconds(pid) if pid else None
        start = time.monotonic()
        time.sleep(duration)
        second = client.get_status()
        end = time.monotonic()
        cpu_end = process_cpu_seconds(pid) if pid else None
        check_capture_status(second, selection)
        return compute_result(name, first, second, end - start,
                              cpu_start, cpu_end)
    finally:
        client.stop_streams()


def display(row: dict) -> None:
    c = row["cpu_percent"]
    cpu = f"{c:.0f}%" if c is not None else "n/a"
    print(
        f"{row['mode']:<17} {row['rgb_fps']:>6.1f} "
        f"{row['ir_fps']:>6.1f} {row['depth_fps']:>6.1f} "
        f"{row['rgb_gaps']:>8} {row['ir_gaps']:>7} "
        f"{row['depth_gaps']:>10} {cpu:>7}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=float, default=3.0,
                        help="seconds ignored after each stream start (default: 3)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="measured seconds per mode (default: 10)")
    args = parser.parse_args(argv)
    if not (0 <= args.warmup <= 120 and 1 <= args.duration <= 300):
        parser.error("--warmup must be 0..120 and --duration must be 1..300")

    client = BrokerClient(timeout=20)
    if not client.ping():
        raise RuntimeError("broker did not respond to ping")
    pid = peer_pid(client.socket_path)
    print(f"Broker PID: {pid or 'unavailable'}; "
          "CPU % uses 100% per fully busy logical core.")
    print("Order alternates modes to help distinguish startup/warmup effects.")
    print(f"Warmup {args.warmup:g}s + measurement {args.duration:g}s per mode.\n")
    print(f"{'Mode':<17} {'RGB':>6} {'IR':>6} {'Depth':>6} "
          f"{'RGB gaps':>8} {'IR gaps':>7} {'Depth gaps':>10} {'CPU':>7}")
    rows: list[dict] = []
    opened = False
    try:
        client.open_device()
        opened = True
        for name, selected in MODES:
            row = run_mode(client, name, selected, args.warmup, args.duration, pid)
            rows.append(row)
            display(row)
    finally:
        if opened:
            try:
                client.stop_streams()
            finally:
                client.close_device()

    solo = [r["rgb_fps"] for r in rows if r["mode"] in ("RGB A", "RGB B")]
    combined = [r["rgb_fps"] for r in rows if r["mode"].startswith("RGB+IR+Depth")]
    solo_med = statistics.median(solo)
    combined_med = statistics.median(combined)
    print(f"\nRGB-only median: {solo_med:.2f} delivered FPS")
    print(f"RGB combined median: {combined_med:.2f} delivered FPS")
    print(f"RGB combined / solo: {100.0 * combined_med / solo_med:.1f}%"
          if solo_med > 0 else "No RGB frames observed in solo tests")
    print("Caution: delivered frames and sequence gaps are diagnostic, "
          "not USB packet loss, latency or video-frame-quality metrics.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"RGB diagnostic failed: {exc}", file=sys.stderr)
        sys.exit(1)
