"""OpenCV HighGUI titlebar close regression tests; no camera or GUI required."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "kinect2_demo_four_clients", ROOT / "tools" / "demo_four_clients.py",
)
assert spec is not None and spec.loader is not None
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class FakeCv2:
    class error(Exception):
        pass

    WND_PROP_VISIBLE = 4
    WINDOW_NORMAL = 0

    def __init__(self, property_value: float = 0):
        self.property_value = property_value
        self.shown = []
        self.destroyed = False
        self.created = []

    def namedWindow(self, name: str, mode: int) -> None:
        self.created.append(name)

    def resizeWindow(self, name: str, width: int, height: int) -> None:
        pass

    def waitKey(self, delay: int) -> int:
        return -1

    def getWindowProperty(self, name: str, prop: int) -> float:
        return self.property_value

    def imshow(self, name: str, image: object) -> None:
        # Real OpenCV would silently re-create the removed window.
        self.shown.append(name)

    def destroyAllWindows(self) -> None:
        self.destroyed = True


class DemoWindowLifecycleTests(unittest.TestCase):
    def test_missing_broker_shows_restart_instructions(self):
        class FakeBroker:
            socket_path = "/tmp/test-missing-kinect2-broker.sock"

            def __init__(self, timeout):
                self.timeout = timeout

            def get_status(self):
                raise demo.BrokerError("cannot communicate with broker")

        with patch.object(demo, "BrokerClient", FakeBroker), \
             patch.object(sys, "argv", ["demo_four_clients.py"]):
            with self.assertRaises(SystemExit) as context:
                demo.main()
        message = str(context.exception)
        self.assertIn("test-missing-kinect2-broker.sock", message)
        self.assertIn("--allow-device-control --frame-preview", message)
        self.assertIn("python3 tools/demo_four_clients.py", message)

    def test_automatic_demo_never_uses_global_usb_commands(self):
        class FakeBroker:
            def __init__(self, timeout):
                pass

            def get_status(self):
                return {
                    "frame_preview": {"enabled": True, "mode": "automatic"},
                    "sensor_open": True, "streaming": True,
                }

            def open_device(self):
                raise AssertionError("Automatic subscribers never open USB manually")

            def start_streams(self, **_kwargs):
                raise AssertionError("Automatic subscribers never start streams globally")

            def stop_streams(self):
                raise AssertionError("Automatic subscribers never stop other clients")

            def close_device(self):
                raise AssertionError("Automatic subscribers never close another session")

        class FakeChild:
            pid = 345
            returncode = 0

            def __init__(self, command, stdin):
                self.command = command

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with patch.object(demo, "BrokerClient", FakeBroker), \
             patch.object(demo.subprocess, "Popen", FakeChild) as spawned, \
             patch.object(sys, "argv", ["demo_four_clients.py"]):
            self.assertEqual(demo.main(), 0)
        self.assertEqual(spawned.call_count, 4)

    def test_closed_window_is_not_recreated(self):
        gui = FakeCv2(0)
        self.assertFalse(demo.show_if_open(gui, "RGB B", object()))
        self.assertEqual(gui.shown, [])

    def test_visible_window_is_displayed(self):
        gui = FakeCv2(1)
        self.assertTrue(demo.show_if_open(gui, "RGB A", object()))
        self.assertEqual(gui.shown, ["RGB A"])

    def test_missing_window_exception_counts_as_closed(self):
        gui = FakeCv2()
        def destroyed(*args):
            raise gui.error("NULL window")
        gui.getWindowProperty = destroyed
        self.assertFalse(demo.window_is_open(gui, "IR A"))
        self.assertFalse(demo.show_if_open(gui, "IR A", object()))
        self.assertEqual(gui.shown, [])

    def test_viewer_exits_before_reading_when_x_closed(self):
        gui = FakeCv2(0)
        cv2_module = types.ModuleType("cv2")
        cv2_module.error = gui.error
        cv2_module.WND_PROP_VISIBLE = gui.WND_PROP_VISIBLE
        cv2_module.WINDOW_NORMAL = gui.WINDOW_NORMAL
        for name in ("namedWindow", "resizeWindow", "waitKey",
                     "getWindowProperty", "imshow", "destroyAllWindows"):
            setattr(cv2_module, name, getattr(gui, name))
        numpy_module = types.ModuleType("numpy")
        clients = []

        class FakeFrameClient:
            def __init__(self, stream, timeout):
                self.stream = stream
                clients.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def receive(self):
                raise AssertionError("Closed window must not receive/recreate frames")

        with patch.dict(sys.modules, {"cv2": cv2_module, "numpy": numpy_module}), \
             patch.object(demo, "FrameClient", FakeFrameClient):
            demo.viewer("rgb", "RGB B")
        self.assertEqual(len(clients), 1)
        self.assertTrue(gui.destroyed)
        self.assertEqual(gui.shown, [])


if __name__ == "__main__":
    unittest.main()
