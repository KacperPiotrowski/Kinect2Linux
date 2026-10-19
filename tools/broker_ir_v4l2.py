#!/usr/bin/env python3
"""Optional IR output: existing Kinect broker -> /dev/video10, without USB access.

--check is read-only. --run explicitly publishes IR to the virtual V4L2 camera.
No Howdy, PAM, models, sudo, service or system configuration changes.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk/python"))

DEVICE = "/dev/video10"
LABEL = "Kinect-v2-IR"
WIDTH, HEIGHT = 512, 424
OUTPUT_BYTES = WIDTH * HEIGHT * 2
YUYV = int.from_bytes(b"YUYV", "little")
V4L2_BUF_TYPE_VIDEO_OUTPUT = 2
V4L2_FIELD_NONE = 1
V4L2_COLORSPACE_SRGB = 8


class PixFormat(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "width", "height", "pixelformat", "field", "bytesperline", "sizeimage",
        "colorspace", "priv", "flags", "ycbcr_enc", "quantization", "xfer_func",
    )]


class FormatUnion(ctypes.Union):
    _fields_ = [("pix", PixFormat), ("raw_data", ctypes.c_uint8 * 200),
                ("align", ctypes.c_uint64)]


class V4L2Format(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("fmt", FormatUnion)]


# Linux x86_64 v4l2_format ABI. Refuse other layouts rather than issuing an
# ioctl with an incorrect buffer size.
if ctypes.sizeof(V4L2Format) != 208:
    raise RuntimeError("Unsupported V4L2 ABI: expected 208-byte format")
VIDIOC_S_FMT = 0xC0000000 | (ctypes.sizeof(V4L2Format) << 16) | (ord("V") << 8) | 5


def check_device() -> None:
    name_path = Path("/sys/class/video4linux/video10/name")
    if name_path.read_text(encoding="utf-8").strip() != LABEL:
        raise RuntimeError("Refusing /dev/video10: unexpected camera name")
    if not stat.S_ISCHR(os.stat(DEVICE, follow_symlinks=False).st_mode):
        raise RuntimeError("Refusing /dev/video10: not a character device")
    print("/dev/video10: Kinect-v2-IR (name and node verified)", flush=True)


def configure(fd: int) -> None:
    f = V4L2Format()
    f.type = V4L2_BUF_TYPE_VIDEO_OUTPUT
    f.fmt.pix.width, f.fmt.pix.height = WIDTH, HEIGHT
    f.fmt.pix.pixelformat = YUYV
    f.fmt.pix.field = V4L2_FIELD_NONE
    f.fmt.pix.bytesperline = WIDTH * 2
    f.fmt.pix.sizeimage = OUTPUT_BYTES
    f.fmt.pix.colorspace = V4L2_COLORSPACE_SRGB
    data = bytearray(ctypes.string_at(ctypes.addressof(f), ctypes.sizeof(f)))
    fcntl.ioctl(fd, VIDIOC_S_FMT, data, True)
    pix = V4L2Format.from_buffer_copy(data).fmt.pix
    if ((pix.width, pix.height, pix.pixelformat, pix.bytesperline) !=
            (WIDTH, HEIGHT, YUYV, WIDTH * 2) or pix.sizeimage < OUTPUT_BYTES):
        raise RuntimeError("V4L2 refused Kinect IR 512x424 YUYV format")


def black_frame() -> bytes:
    return bytes((16, 128, 16, 128)) * (WIDTH * HEIGHT // 2)


def write_frame(fd: int, data: bytes) -> bool:
    if len(data) != OUTPUT_BYTES:
        raise ValueError("Unexpected V4L2 buffer length")
    try:
        written = os.write(fd, data)
    except (BlockingIOError, InterruptedError):
        return False  # skip, never queue outdated images
    if written != len(data):
        raise OSError(f"V4L2 short write: {written}/{len(data)}")
    return True


class IRConverter:
    """Percentile scaling similar to the legacy IR bridge; no AI."""

    def __init__(self) -> None:
        self.low = None
        self.high = None
        self.frame_count = 0

    def convert(self, raw: object) -> bytes:
        import numpy as np

        image = np.asarray(raw, dtype=np.float32)
        if image.shape != (HEIGHT, WIDTH):
            raise ValueError("Expected IR frame shape 424x512")
        if self.low is None or self.frame_count % 15 == 0:
            samples = image[::4, ::4]
            samples = samples[np.isfinite(samples) & (samples > 0)]
            if samples.size >= 100:
                low, high = np.percentile(samples, [1, 99.5])
                high = max(float(high), float(low) + 1.0)
                if self.low is None:
                    self.low, self.high = float(low), high
                else:
                    self.low = self.low * 0.75 + float(low) * 0.25
                    self.high = self.high * 0.75 + high * 0.25
        self.frame_count += 1
        if self.low is None:
            return black_frame()
        valid = np.isfinite(image) & (image > 0)
        safe = np.where(valid, image, self.low)
        y = np.where(
            valid, np.sqrt(np.clip((safe - self.low) / (self.high - self.low), 0, 1)) * 255 + 0.5,
            0,
        ).astype(np.uint8)
        result = bytearray(OUTPUT_BYTES)
        result[::2] = y.tobytes()
        result[1::2] = b"\x80" * (WIDTH * HEIGHT)
        return bytes(result)


def bridge(*, max_frames: int) -> None:
    import numpy as np
    from kinect2_linux.frame_client import FrameClient, FrameTimeoutError

    check_device()
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise RuntimeError("XDG_RUNTIME_DIR required for per-user writer lock")
    lockfd = os.open(str(Path(runtime) / "kinect2-ir-writer.lock"),
                     os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(DEVICE, os.O_WRONLY | os.O_NONBLOCK |
                     os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            configure(fd)
            write_frame(fd, black_frame())
            count, skipped = 0, 0
            converter = IRConverter()
            print("Broker IR -> /dev/video10; Ctrl+C closes writer.", flush=True)
            with FrameClient("ir", timeout=2.0) as client:
                while not max_frames or count < max_frames:
                    try:
                        frame, missed = client.receive_latest()
                    except FrameTimeoutError:
                        # Replace any last-good image with black if USB stalls.
                        cleared = write_frame(fd, black_frame())
                        print("IR stalled: " + ("privacy black frame written." if cleared else
                              "black frame temporarily blocked by V4L2."),
                              file=sys.stderr)
                        continue
                    skipped += missed
                    with frame:
                        if frame.kind != "ir" or (frame.width, frame.height) != (WIDTH, HEIGHT):
                            raise RuntimeError("Unexpected broker frame type/shape")
                        raw = np.frombuffer(frame.mapping, dtype=np.float32)
                        converted = converter.convert(raw.reshape(HEIGHT, WIDTH))
                        del raw
                    if write_frame(fd, converted):
                        count += 1
                        if count == 1 or count % 60 == 0:
                            print(f"IR frames={count}; local queued skipped={skipped}",
                                  flush=True)
        finally:
            try:
                write_frame(fd, black_frame())
            except OSError:
                pass
            os.close(fd)
    finally:
        os.close(lockfd)


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only IR device check")
    mode.add_argument("--run", action="store_true", help="Explicitly feed V4L2 IR")
    parser.add_argument("--max-frames", type=int, default=0, help="Exit after N frames; 0=until Ctrl+C")
    opts = parser.parse_args(args)
    if opts.max_frames < 0:
        parser.error("--max-frames cannot be negative")
    try:
        if opts.check:
            check_device()
            print("Read-only check complete. No stream started.")
        else:
            bridge(max_frames=opts.max_frames)
        return 0
    except KeyboardInterrupt:
        print("\nIR bridge stopped.")
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(f"IR bridge error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
