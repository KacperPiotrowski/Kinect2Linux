"""Real C++ broker / Python IPC integration, offline and without Kinect.

Set KINECT2_BROKER_BIN to a built binary to enable this suite.
"""

import os
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux import encode_message, receive_message  # noqa: E402
from kinect2_linux.broker_client import BrokerClient, BrokerError  # noqa: E402

BROKER_BIN = os.environ.get("KINECT2_BROKER_BIN", "")


@unittest.skipUnless(BROKER_BIN and Path(BROKER_BIN).is_file(), "build C++ broker and set KINECT2_BROKER_BIN")
class BrokerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kinect2-ipc-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "broker.sock"
        self.proc = subprocess.Popen(
            [BROKER_BIN, "--socket", str(self.path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self.addCleanup(self.stop_broker)
        for _ in range(200):
            if self.path.exists():
                break
            if self.proc.poll() is not None:
                self.fail(f"broker exited unexpectedly: {self.proc.stderr.read()!r}")
            time.sleep(0.01)
        else:
            self.fail("broker socket did not appear")

    def stop_broker(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.proc.stderr.close()

    def raw(self, payload: bytes) -> dict | None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(str(self.path))
            sock.sendall(payload)
            try:
                return receive_message(sock)
            except (OSError, ValueError):
                return None

    def test_socket_is_private(self):
        st = self.path.stat()
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)

    def test_ping_and_status(self):
        client = BrokerClient(self.path)
        self.assertTrue(client.ping())
        self.assertEqual(client.get_status(), {
            "state": "unavailable", "sensor_open": False,
            "reason": "sensor_backend_not_implemented",
        })

    def test_multiple_independent_clients(self):
        self.assertTrue(BrokerClient(self.path).ping())
        self.assertTrue(BrokerClient(self.path).ping())

    def test_unknown_operation_is_explicit_error(self):
        with self.assertRaisesRegex(BrokerError, "unknown_operation"):
            BrokerClient(self.path).request("does_not_exist")

    def test_fragmented_frame(self):
        packet = encode_message({"protocol_version": 1, "request_id": 42, "op": "ping", "params": {}})
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(str(self.path))
            for i in range(0, len(packet), 2):
                sock.sendall(packet[i:i+2])
            self.assertEqual(receive_message(sock)["request_id"], 42)

    def test_oversized_length_rejected(self):
        self.assertIsNone(self.raw(struct.pack(">I", 65537)))
        self.assertTrue(BrokerClient(self.path).ping())

    def test_invalid_json_and_version_rejected(self):
        bad_json = b'{"protocol_version":1,"op":"ping",'
        for payload in (
            struct.pack(">I", len(bad_json)) + bad_json,
            self.frame(b'{"protocol_version":2,"request_id":1,"op":"ping","params":{}}'),
            self.frame(b'{"protocol_version":1,"request_id":1,"op":"ping","params":{},"params":{}}'),
            self.frame(b'{"protocol_version":1,"request_id":1,"op":"ping","params":{},"x":"\xff"}'),
            self.frame(b'{"protocol_version":1,"request_id":1,"op":"ping","params":{},"x":NaN}'),
        ):
            with self.subTest(payload=payload[:70]):
                self.assertIsNone(self.raw(payload))
        self.assertTrue(BrokerClient(self.path).ping())

    def test_duplicate_nested_fields_rejected(self):
        payload = (b'{"protocol_version":1,"request_id":1,"op":"ping",'
                   b'"params":{"x":1,"x":2}}')
        self.assertIsNone(self.raw(self.frame(payload)))
        self.assertTrue(BrokerClient(self.path).ping())

    def test_json_nesting_limit_rejected(self):
        deep = b'[' * 34 + b'0' + b']' * 34
        body = (b'{"protocol_version":1,"request_id":1,"op":"ping",'
                b'"params":{"nested":' + deep + b'}}')
        self.assertIsNone(self.raw(self.frame(body)))
        self.assertTrue(BrokerClient(self.path).ping())

    def test_request_id_rejects_wrong_type_or_excess_range(self):
        for request_id in ("true", "1.25", "-1", "10000000000000000"):
            payload = ('{"protocol_version":1,"request_id":' + request_id +
                       ',"op":"ping","params":{}}').encode()
            with self.subTest(request_id=request_id):
                self.assertIsNone(self.raw(self.frame(payload)))
        self.assertTrue(BrokerClient(self.path).ping())

    def test_invalid_socket_directory_denied(self):
        with tempfile.TemporaryDirectory() as other:
            os.chmod(other, 0o755)
            try:
                bad = subprocess.run([BROKER_BIN, "--socket", str(Path(other) / "x.sock")],
                                     capture_output=True, timeout=2)
                self.assertNotEqual(bad.returncode, 0)
                self.assertFalse((Path(other) / "x.sock").exists())
            finally:
                os.chmod(other, 0o700)

    def test_existing_socket_not_removed(self):
        attempt = subprocess.run([BROKER_BIN, "--socket", str(self.path)],
                                 capture_output=True, timeout=2)
        self.assertNotEqual(attempt.returncode, 0)
        self.assertTrue(BrokerClient(self.path).ping())

    def test_clean_socket_on_sigterm(self):
        self.proc.send_signal(signal.SIGTERM)
        self.proc.wait(timeout=3)
        self.assertFalse(self.path.exists())

    @staticmethod
    def frame(body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + body


if __name__ == "__main__":
    unittest.main()
