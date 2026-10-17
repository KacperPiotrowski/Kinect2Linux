#!/usr/bin/env python3
"""Four *independent processes* viewing one Kinect's RGB/IR via one broker.

Broker must have --allow-device-control --frame-preview.
This script alone claims/releases capture via the broker's CONTROL API.
Children are read-only frame subscribers. No legacy V4L2 bridge is started.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux import BrokerClient, BrokerError  # noqa: E402
from kinect2_linux.frame_client import FrameClient  # noqa: E402


def window_is_open(cv2, label: str) -> bool:
    """OpenCV's imshow() recreates X-closed windows unless we check first."""
    try:
        return cv2.getWindowProperty(label, cv2.WND_PROP_VISIBLE) > 0
    except cv2.error:
        # HighGUI can throw after the window has been destroyed.
        return False


def show_if_open(cv2, label: str, image: object) -> bool:
    """Do not recreate a window closed with the titlebar X."""
    if not window_is_open(cv2, label):
        return False
    cv2.imshow(label, image)
    return True


def viewer(stream: str, label: str) -> None:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "GUI preview requires numpy and an OpenCV build with HighGUI support"
        ) from exc

    cv2.namedWindow(label, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(label, 750, 450)
    last = time.monotonic()
    displayed = 0
    fps = 0.0
    with FrameClient(stream, timeout=10) as client:
        try:
            while True:
                # Process pending native window-close events *before* the next
                # imshow(), otherwise HighGUI silently recreates a closed X window.
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")) or not window_is_open(cv2, label):
                    break
                with client.receive() as frame:
                    if stream == "rgb":
                        # libfreenect2 CPU color output is 4 bytes per pixel.
                        # BGRX: keep three components for the OpenCV viewer.
                        raw = np.frombuffer(frame.mapping, dtype=np.uint8)
                        image = raw.reshape(frame.height, frame.width, 4)[:, :, :3]
                        image = cv2.resize(image, (960, 540),
                                           interpolation=cv2.INTER_AREA)
                        del raw
                    else:
                        raw = np.frombuffer(frame.mapping, dtype=np.float32)
                        image = raw.reshape(frame.height, frame.width)
                        image = cv2.normalize(image, None, 0, 255,
                                              cv2.NORM_MINMAX).astype(np.uint8)
                        del raw
                    seq = frame.sequence
                displayed += 1
                now = time.monotonic()
                if now - last >= 1:
                    fps = displayed / (now - last)
                    last, displayed = now, 0
                cv2.putText(image, f"{label} | {fps:.1f} display FPS | seq={seq}",
                            (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (255, 255, 255) if stream == "rgb" else 255,
                            2, cv2.LINE_AA)
                # A close event may also arrive while waiting for a frame.
                cv2.waitKey(1)
                if not show_if_open(cv2, label, image):
                    break
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")) or not window_is_open(cv2, label):
                    break
        finally:
            cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", choices=("rgb", "ir"),
                        help=argparse.SUPPRESS)
    parser.add_argument("--label", default="Kinect2 preview",
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.viewer:
        viewer(args.viewer, args.label)
        return 0

    broker = BrokerClient(timeout=20)
    status = broker.get_status()
    if not status.get("frame_preview", {}).get("enabled"):
        raise SystemExit(
            "Broker requires hardware mode and --frame-preview:\n"
            "  ./bin/kinect2-broker-hw --allow-device-control --frame-preview"
        )
    if status.get("sensor_open") or status.get("streaming"):
        raise SystemExit(
            "Device already active; stop the previous benchmark/session first. "
            "This demo deliberately does not steal or close another session."
        )

    children: list[subprocess.Popen[bytes]] = []
    opened = False
    started = False
    try:
        broker.open_device()
        opened = True
        broker.start_streams(rgb=True, ir_depth=True)
        started = True
        for stream, name in (
            ("rgb", "Kinect2 RGB A"),
            ("rgb", "Kinect2 RGB B"),
            ("ir", "Kinect2 IR A"),
            ("ir", "Kinect2 IR B"),
        ):
            children.append(subprocess.Popen([
                sys.executable, str(Path(__file__).resolve()),
                "--viewer", stream, "--label", name,
            ], stdin=subprocess.DEVNULL))
        print("Four independent viewers started. Close individual windows with ESC/Q; "
              "press Ctrl+C here to stop all.", flush=True)
        print("Capture uses ONE Kinect USB owner: the broker.", flush=True)
        exited: set[int] = set()
        while True:
            for child in children:
                if child.poll() is not None and child.pid not in exited:
                    exited.add(child.pid)
                    print(f"Viewer PID {child.pid} closed; remaining viewers continue.",
                          flush=True)
            if all(child.poll() is not None for child in children):
                return 0 if all(child.returncode == 0 for child in children) else 1
            time.sleep(0.15)
    except KeyboardInterrupt:
        print("\nClosing four viewers and releasing Kinect...")
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        if started:
            try:
                broker.stop_streams()
            except BrokerError as exc:
                print(f"Warning: stop_streams failed: {exc}", file=sys.stderr)
        if opened:
            try:
                broker.close_device()
            except BrokerError as exc:
                print(f"Warning: close_device failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
