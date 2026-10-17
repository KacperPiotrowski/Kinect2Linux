"""Offline frame passing tests; zero Kinect/GUI requirements."""
import array
import mmap
import os
import socket
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux.frame_client import (  # noqa: E402
    FrameClient, FrameProtocolError, FrameTimeoutError, HEADER, recv_frame_packet,
)


class FrameClientTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.writer = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET,
        )
        self.addCleanup(self.reader.close)
        self.addCleanup(self.writer.close)
        self.reader.settimeout(1)

    def send(self, *, stream=2, width=512, height=424, broken_size=False,
             attach_fd=True, seq=42):
        size = width * height * 4
        hdr = HEADER.pack(
            b"K2F1", stream, 4, 0, width, height,
            size + (4 if broken_size else 0), seq, 123456,
        )
        anc = []
        if attach_fd:
            fd = os.memfd_create("fake-immutable")
            try:
                os.ftruncate(fd, size)
                # Sparse memfd; a real producer writes and seals frame data.
                anc = [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                        array.array("i", [fd]))]
                self.writer.sendmsg([hdr], anc)
            finally:
                os.close(fd)
        else:
            self.writer.send(hdr)

    def test_valid_ir_frame_and_closed_descriptor(self):
        self.send()
        with recv_frame_packet(self.reader) as frame:
            self.assertEqual(frame.kind, "ir")
            self.assertEqual((frame.width, frame.height), (512, 424))
            self.assertEqual(frame.sequence, 42)
            self.assertEqual(frame.host_time_us, 123456)
            self.assertEqual(len(frame.mapping), 512 * 424 * 4)

    def test_latest_skips_backlog_and_returns_newest_sequence(self):
        self.send(seq=91)
        self.send(seq=92)
        self.send(seq=93)
        client = FrameClient("ir")
        client._sock = self.reader  # Offline harness: handshake already bypassed.
        frame, skipped = client.receive_latest()
        with frame:
            self.assertEqual(frame.kind, "ir")
            self.assertEqual(frame.sequence, 93)
        self.assertEqual(skipped, 2)

    def test_latest_single_packet_keeps_it(self):
        self.send(seq=104)
        client = FrameClient("ir")
        client._sock = self.reader
        frame, skipped = client.receive_latest()
        with frame:
            self.assertEqual(frame.sequence, 104)
        self.assertEqual(skipped, 0)

    def test_latest_bounded_drain(self):
        for seq in range(10, 15):
            self.send(seq=seq)
        client = FrameClient("ir")
        client._sock = self.reader
        frame, skipped = client.receive_latest(max_pending=2)
        with frame:
            self.assertEqual(frame.sequence, 12)
        self.assertEqual(skipped, 2)
        with client.receive() as next_frame:
            self.assertEqual(next_frame.sequence, 13)
        with client.receive() as next_frame:
            self.assertEqual(next_frame.sequence, 14)

    def test_latest_parameter_rejects_wrong_limits(self):
        client = FrameClient("ir")
        for limit in (0, -1, 129, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                client.receive_latest(max_pending=limit)

    def test_temporary_timeout_keeps_subscription_alive(self):
        self.reader.settimeout(0.02)
        with self.assertRaises(FrameTimeoutError):
            recv_frame_packet(self.reader)
        # No disconnect: the next real frame must still arrive.
        self.send(seq=74)
        with recv_frame_packet(self.reader) as frame:
            self.assertEqual(frame.sequence, 74)

    def test_receive_latest_timeout_does_not_close_client_socket(self):
        self.reader.settimeout(0.02)
        client = FrameClient("ir")
        client._sock = self.reader
        with self.assertRaises(FrameTimeoutError):
            client.receive_latest()
        self.send(seq=75)
        frame, skipped = client.receive_latest()
        with frame:
            self.assertEqual(frame.sequence, 75)
        self.assertEqual(skipped, 0)

    def test_no_frames_nonblocking_is_retryable(self):
        with self.assertRaises(FrameTimeoutError):
            recv_frame_packet(self.reader, nonblocking=True)
        self.send(seq=76)
        with recv_frame_packet(self.reader) as frame:
            self.assertEqual(frame.sequence, 76)

    def test_wrong_frame_byte_length_rejected(self):
        self.send(broken_size=True)
        with self.assertRaisesRegex(FrameProtocolError, "byte size"):
            recv_frame_packet(self.reader)

    def test_missing_descriptor_rejected(self):
        self.send(attach_fd=False)
        with self.assertRaisesRegex(FrameProtocolError, "missing frame header"):
            recv_frame_packet(self.reader)

    def test_impossible_frame_size_rejected(self):
        self.send(width=4096, height=2160)
        with self.assertRaisesRegex(FrameProtocolError, "unsupported frame shape"):
            recv_frame_packet(self.reader)

    def test_invalid_kind_rejected(self):
        self.send(stream=99)
        with self.assertRaisesRegex(FrameProtocolError, "invalid frame header"):
            recv_frame_packet(self.reader)

    def test_requires_explicit_valid_stream(self):
        with self.assertRaises(ValueError):
            FrameClient("audio")
        with self.assertRaises(ValueError):
            FrameClient("rgb", timeout=0)


if __name__ == "__main__":
    unittest.main()
