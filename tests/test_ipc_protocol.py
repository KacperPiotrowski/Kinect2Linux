"""Hardware-free tests of proposed Python/daemon control framing."""

import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from kinect2_linux.ipc import (  # noqa: E402
    MAX_CONTROL_BYTES,
    ProtocolError,
    encode_message,
    receive_message,
)


class ChunkedSocket:
    def __init__(self, payload: bytes, chunk_size: int = 2):
        self.buffer = payload
        self.chunk_size = chunk_size
        self.requested_sizes = []

    def recv(self, size):
        self.requested_sizes.append(size)
        size = min(size, self.chunk_size)
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result


def packet(value) -> bytes:
    body = json.dumps(value).encode("utf-8")
    return struct.pack(">I", len(body)) + body


class IPCProtocolTests(unittest.TestCase):
    def test_partial_socket_reads_and_unicode(self):
        obj = {"protocol_version": 1, "request_id": 7, "op": "stan-urządzenia"}
        wire = encode_message(obj)
        self.assertEqual(receive_message(ChunkedSocket(wire, 1)), obj)

    def test_concatenated_messages(self):
        first = {"protocol_version": 1, "request_id": 1}
        second = {"protocol_version": 1, "request_id": 2}
        sock = ChunkedSocket(encode_message(first) + encode_message(second), 3)
        self.assertEqual(receive_message(sock), first)
        self.assertEqual(receive_message(sock), second)

    def test_reject_empty_header(self):
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(b""))

    def test_reject_truncated_payload(self):
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(struct.pack(">I", 5) + b"{}"))

    def test_reject_oversized_length_without_reading_body(self):
        sock = ChunkedSocket(struct.pack(">I", MAX_CONTROL_BYTES + 1))
        with self.assertRaises(ProtocolError):
            receive_message(sock)
        self.assertEqual(sock.requested_sizes, [4, 2])

    def test_reject_zero_length(self):
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(struct.pack(">I", 0)))

    def test_reject_bad_json_or_scalar(self):
        for body in (b"not-json", b"[]", b"null", b'"x"'):
            with self.subTest(body=body), self.assertRaises(ProtocolError):
                receive_message(ChunkedSocket(struct.pack(">I", len(body)) + body))

    def test_reject_unsupported_version_and_bool(self):
        for version in (0, 2, True, "1", None):
            with self.subTest(version=version), self.assertRaises(ProtocolError):
                encode_message({"protocol_version": version})
            with self.subTest(version=version), self.assertRaises(ProtocolError):
                receive_message(ChunkedSocket(packet({"protocol_version": version})))

    def test_reject_nonfinite_numbers(self):
        with self.assertRaises(ProtocolError):
            encode_message({"protocol_version": 1, "value": float("nan")})
        raw = b'{"protocol_version":1,"value":NaN}'
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(struct.pack(">I", len(raw)) + raw))

    def test_reject_duplicate_json_keys(self):
        raw = b'{"protocol_version":1,"request_id":2,"request_id":3}'
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(struct.pack(">I", len(raw)) + raw))

    def test_reject_invalid_utf8(self):
        raw = b'\xff\xfe'
        with self.assertRaises(ProtocolError):
            receive_message(ChunkedSocket(struct.pack(">I", len(raw)) + raw))

    def test_reject_encode_size_limit(self):
        with self.assertRaises(ProtocolError):
            encode_message({"protocol_version": 1, "data": "z" * MAX_CONTROL_BYTES})


if __name__ == "__main__":
    unittest.main()
