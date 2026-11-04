"""Offline Kinect2 Studio tests: no Qt, sensor or microphone required."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "tools/kinect2_studio_core.py"
spec = importlib.util.spec_from_file_location("kinect2_studio_core", CORE)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class StudioCoreTests(unittest.TestCase):
    def test_qshortcut_imports_from_qtgui_not_qtwidgets(self):
        # The CI image may not ship PySide6. This static check guards
        # the exact Qt import regression that stopped Studio launching.
        tree = ast.parse((ROOT / "tools/kinect2_studio.py").read_text())
        locations = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                    "PySide6.QtGui", "PySide6.QtWidgets"):
                for alias in node.names:
                    locations[alias.name] = node.module
        self.assertEqual(locations.get("QShortcut"), "PySide6.QtGui")
        self.assertEqual(locations.get("QKeySequence"), "PySide6.QtGui")

    def test_studio_receiver_has_no_redundant_30fps_rate_gate(self):
        """Broker already paces frames; a post-conversion 33ms gate halves FPS.

        Keep this guard even on no-Qt CI hosts. GUI timer plus latest-only
        mailbox can drop frames without a second sleep/skip in the receiver.
        """
        tree = ast.parse((ROOT / "tools/kinect2_studio.py").read_text())
        stream = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "StreamWorker"
        )
        receiver = next(
            node for node in stream.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_capture"
        )
        identifiers = {
            node.id for node in ast.walk(receiver)
            if isinstance(node, ast.Name)
        }
        self.assertNotIn("last_processed", identifiers)
        # No additional 5Hz cap: inference worker processes newest BGR
        # snapshots as quickly as ONNX can compute on the machine.
        self.assertNotIn("last_pose_offer", identifiers)
        self.assertIn("receive_latest", {
            node.attr for node in ast.walk(receiver)
            if isinstance(node, ast.Attribute)
        })

    def test_body_benchmark_describes_real_median_and_tail(self):
        import importlib.util
        path = ROOT / "tools/kinect2_body_bench.py"
        spec = importlib.util.spec_from_file_location("kinect2_body_bench", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        s = module.describe([15.0, 25.0, 35.0, 45.0, 55.0])
        self.assertIn("median=35.0ms", s)
        self.assertIn("p95=55.0ms", s)
        self.assertIn("best=15.0ms", s)
        self.assertIn("equiv_sequential_fps=28.6", s)

    def test_studio_cpu_profile_scales_and_bounds_threads(self):
        # This helper does not mutate the global environment. Studio uses
        # os.environ.setdefault, preserving explicit ORT thread overrides.
        self.assertEqual(studio.studio_cpu_thread_default(None), "1")
        self.assertEqual(studio.studio_cpu_thread_default(1), "1")
        self.assertEqual(studio.studio_cpu_thread_default(2), "2")
        self.assertEqual(studio.studio_cpu_thread_default(12), "4")
        self.assertEqual(studio.studio_cpu_thread_default(24), "4")

    def test_presence_exact_names_not_easy_effects_or_monitor(self):
        listing = (
            "1\teasyeffects_source\tPipeWire\tfloat32le 2ch 48000Hz\tRUNNING\n"
            "2\talsa_input.usb-Microsoft_Xbox_NUI_Sensor_TEST-02.analog-surround-40"
            "\tPipeWire\ts32le 4ch 16000Hz\tRUNNING\n"
            "3\tkinect2_linux_mono\tPipeWire\tfloat32le 1ch 48000Hz\tIDLE\n"
            "4\tkinect2_linux_stereo\tPipeWire\tfloat32le 2ch 48000Hz\tIDLE\n"
        )
        self.assertEqual(studio.audio_presence(listing),
                         {"raw": True, "mono": True, "stereo": True})
        self.assertEqual(studio.audio_presence(
            "17\talsa_output.fake.monitor\tPipeWire\tfloat32le 2ch 48000Hz\n"
            "18\tkinect2_linux_monochrome\tPipeWire\tfloat32le 1ch 48000Hz\n"),
            {"raw": False, "mono": False, "stereo": False})

    def test_broker_unknown_does_not_invent_status(self):
        self.assertIn("nie jest dostępny",
                      studio.broker_summary({"frame_preview": {"enabled": False}}))
        self.assertIn("nieznane", studio.broker_summary(
            {"frame_preview": {"enabled": True}}).lower())

    def test_broker_idle_and_running_different(self):
        idle = studio.broker_summary({
            "frame_preview": {"enabled": True, "mode": "automatic"},
            "sensor_open": False, "streaming": False,
        })
        live = studio.broker_summary({
            "frame_preview": {"enabled": True, "mode": "automatic"},
            "sensor_open": True, "streaming": True,
        })
        self.assertIn("USB zamknięte", idle)
        self.assertIn("standby", idle)
        self.assertIn("USB otwarte", live)
        self.assertIn("streaming", live)


if __name__ == "__main__":
    unittest.main()
