"""Experimental local video frames via Unix SOCK_SEQPACKET + sealed memfd.

Control JSON and frame data are intentionally separate. Viewers never open USB.
"""

from __future__ import annotations

from dataclasses import dataclass
import array
import mmap
import os
from pathlib import Path
import select
import socket
import struct

HEADER = struct.Struct("!4sBBHIIIIQ")
KINDS = {"rgb": 1, "ir": 2, "depth": 3}
LETTERS = {"rgb": b"R", "ir": b"I", "depth": b"D"}
MAX_SIZE = 16 * 1024 * 1024


class FrameProtocolError(RuntimeError):
    """Invalid, missing or unsupported local frame packet."""


class FrameTimeoutError(FrameProtocolError):
    """No frame arrived before the deadline; the socket may still recover."""


@dataclass
class FrameSnapshot:
    kind: str
    width: int
    height: int
    bytes_per_pixel: int
    sequence: int
    host_time_us: int
    mapping: mmap.mmap

    def close(self) -> None:
        self.mapping.close()

    def __enter__(self) -> "FrameSnapshot":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def recv_frame_packet(sock: socket.socket, *, nonblocking: bool = False) -> FrameSnapshot:
    """Receive exactly one descriptor and validated, immutable image mapping."""
    fd_size = array.array("i").itemsize
    try:
        packet, ancdata, flags, _addr = sock.recvmsg(
            HEADER.size, socket.CMSG_SPACE(fd_size * 4),
            socket.MSG_CMSG_CLOEXEC | (socket.MSG_DONTWAIT if nonblocking else 0),
        )
    except (TimeoutError, BlockingIOError) as exc:
        # A stalled sensor or an empty nonblocking queue is not malformed IPC.
        # Keep the connected subscription alive so clients can wait/retry.
        raise FrameTimeoutError("no frame received before timeout") from exc
    except OSError as exc:
        raise FrameProtocolError("frame socket receive failed") from exc

    received: list[int] = []
    for level, kind, data in ancdata:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            arr = array.array("i")
            arr.frombytes(data[:len(data) - len(data) % fd_size])
            received.extend(arr)
    try:
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise FrameProtocolError("truncated frame message or descriptors")
        if len(packet) != HEADER.size or len(received) != 1:
            raise FrameProtocolError("missing frame header or memfd")
        magic, kind, bpp, reserved, w, h, size, seq, host_us = HEADER.unpack(packet)
        if magic != b"K2F1" or kind not in KINDS.values() or reserved != 0:
            raise FrameProtocolError("invalid frame header or kind")
        if bpp != 4 or w == 0 or h == 0 or w > 1920 or h > 1080:
            raise FrameProtocolError("unsupported frame shape")
        if size != w * h * bpp or size > MAX_SIZE:
            raise FrameProtocolError("invalid frame byte size")
        if (kind == 1 and (w, h) != (1920, 1080)) or (
            kind != 1 and (w, h) != (512, 424)
        ):
            raise FrameProtocolError("unexpected native Kinect frame dimensions")
        if os.fstat(received[0]).st_size != size:
            raise FrameProtocolError("frame file size mismatch")
        mapping = mmap.mmap(received[0], size, access=mmap.ACCESS_READ)
        return FrameSnapshot(
            next(name for name, value in KINDS.items() if value == kind),
            w, h, bpp, seq, host_us, mapping,
        )
    except (OSError, ValueError) as exc:
        raise FrameProtocolError("invalid frame buffer") from exc
    finally:
        for fd in received:
            os.close(fd)


class FrameClient:
    """Independent read-only RGB, IR or Depth subscriber, no USB ownership."""

    def __init__(
        self, stream: str, socket_path: str | os.PathLike[str] | None = None,
        *, timeout: float = 5.0,
    ):
        if stream not in KINDS:
            raise ValueError("stream must be rgb, ir or depth")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if socket_path is None:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if not runtime_dir:
                raise ValueError("XDG_RUNTIME_DIR missing")
            socket_path = Path(runtime_dir) / "kinect2-frames.sock"
        self.stream = stream
        self.path = os.fspath(socket_path)
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def __enter__(self) -> "FrameClient":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self.path)
            sock.sendall(LETTERS[self.stream])
            if sock.recv(1) != b"K":
                raise FrameProtocolError("broker rejected frame subscription")
        except BaseException:
            sock.close()
            raise
        self._sock = sock
        return self

    def receive(self) -> FrameSnapshot:
        if self._sock is None:
            raise FrameProtocolError("FrameClient not connected")
        packet = recv_frame_packet(self._sock)
        if packet.kind != self.stream:
            packet.close()
            raise FrameProtocolError("wrong stream received")
        return packet

    def receive_latest(self, *, max_pending: int = 32) -> tuple[FrameSnapshot, int]:
        """For interactive video, discard queued old snapshots before rendering.

        Returns (newest_frame, skipped_queued_count). This discards stale frames
        *only* for this subscriber; it never changes sensor/other clients.
        A finite bound prevents starvation if the producer stays faster.
        """
        if type(max_pending) is not int or not 1 <= max_pending <= 128:
            raise ValueError("max_pending must be an integer from 1 to 128")
        frame = self.receive()  # Blocking wait for the next available packet.
        skipped = 0
        try:
            for _ in range(max_pending):
                # No extra blocking wait: this is a live preview, not recording.
                ready, _, _ = select.select([self._sock], [], [], 0)
                if not ready:
                    break
                try:
                    newer = recv_frame_packet(self._sock, nonblocking=True)
                except FrameTimeoutError:
                    # select() readiness may become stale before recvmsg().
                    # We already hold a valid snapshot; don't discard it.
                    break
                if newer.kind != self.stream:
                    newer.close()
                    raise FrameProtocolError("wrong stream received")
                frame.close()  # Also releases old mmap; received fd already closed.
                frame = newer
                skipped += 1
            return frame, skipped
        except BaseException:
            frame.close()
            raise

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __exit__(self, *_exc: object) -> None:
        self.close()
