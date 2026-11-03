"""Offline Kinect2 Studio tests: no Qt, sensor or microphone required."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "tools/kinect2_studio_core.py"
spec = importlib.util.spec_from_file_location("kinect2_studio_core", CORE)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class StudioCoreTests(unittest.TestCase):
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
