"""Offline real broker -> child worker integration; USB remains disabled."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))
from kinect2_linux import BrokerClient  # noqa: E402

BROKER = os.environ.get("KINECT2_BROKER_BIN")
WORKER = os.environ.get("KINECT2_WORKER_BIN")


@unittest.skipUnless(BROKER and WORKER and Path(BROKER).is_file()
                     and Path(WORKER).is_file(), "requires built broker and child")
class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="kinect2-child-")
        self.addCleanup(self.dir.cleanup)
        self.socket = str(Path(self.dir.name) / "broker.sock")
        self.broker = subprocess.Popen(
            [BROKER, "--socket", self.socket, "--worker", WORKER],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(self.cleanup_broker)
        for _ in range(300):
            if Path(self.socket).exists():
                break
            if self.broker.poll() is not None:
                self.fail(f"broker exited unexpectedly: {self.broker.stderr.read()!r}")
            time.sleep(0.01)
        else:
            self.fail("broker socket missing")

    def cleanup_broker(self):
        if self.broker.poll() is None:
            self.broker.terminate()
            try:
                self.broker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.broker.kill()
                self.broker.wait(timeout=3)
        self.broker.stderr.close()

    def test_parent_owns_child_and_usb_stays_disabled(self):
        client = BrokerClient(self.socket)
        s = client.get_status()
        self.assertTrue(s["worker"]["enabled"])
        self.assertTrue(s["worker"]["healthy"])
        self.assertGreater(s["worker"]["pid"], 1)
        pid = s["worker"]["pid"]
        status_text = Path(f"/proc/{pid}/status").read_text()
        parent_line = next(x for x in status_text.splitlines() if x.startswith("PPid:"))
        self.assertEqual(int(parent_line.split()[1]), self.broker.pid)
        self.assertTrue(client.ping())
        self.assertFalse(s["sensor_open"])
        self.assertFalse(s["device_control_enabled"])

    def test_killed_child_is_detected_but_broker_survives(self):
        client = BrokerClient(self.socket)
        pid = client.get_status()["worker"]["pid"]
        os.kill(pid, signal.SIGKILL)
        for _ in range(100):
            if not client.get_status()["worker"]["healthy"]:
                break
            time.sleep(0.01)
        else:
            self.fail("dead child still appears healthy")
        self.assertIsNone(self.broker.poll())
        self.assertTrue(client.ping())

    def test_broker_reaps_child_on_shutdown(self):
        client = BrokerClient(self.socket)
        pid = client.get_status()["worker"]["pid"]
        self.broker.terminate()
        self.broker.wait(timeout=3)
        for _ in range(100):
            if not Path(f"/proc/{pid}").exists():
                break
            time.sleep(0.01)
        else:
            self.fail("child still running after parent exited")


if __name__ == "__main__":
    unittest.main()
