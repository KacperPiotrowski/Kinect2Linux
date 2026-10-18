"""Offline profile CLI checks; never interact with real USB, audio or systemd."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/kinect2_modes.py"


class ModeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="kinect2-modes-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "tools").mkdir()
        (root / "tools/kinect2_modes.py").write_text(SCRIPT.read_text())
        (root / "tools/install_kinect2.sh").write_text(
            '#!/usr/bin/env bash\n'
            'printf "installer:%s\\n" "$1" >> "$MOCK_CALLS"\n'
            'if [[ "$1" == --activate && "${MOCK_FAIL_CAMERA:-0}" == 1 ]]; then exit 2; fi\n'
        )
        (root / "tools/kinect2_audio_profiles.py").write_text(
            'import os, sys\n'
            'with open(os.environ["MOCK_CALLS"], "a") as f: '
            'f.write("audio:" + sys.argv[1] + "\\n")\n'
            'if sys.argv[1] == "enable-service" and '
            'os.getenv("MOCK_FAIL_STEREO") == "1": sys.exit(2)\n'
        )
        (root / "kinect2").write_text(
            '#!/usr/bin/env bash\nprintf "cli:%s\\n" "$*" >> "$MOCK_CALLS"\n'
        )
        self.script = root / "tools/kinect2_modes.py"
        self.calls = root / "calls"
        self.env = {**os.environ, "MOCK_CALLS": str(self.calls)}

    def call(self, *args, **changes):
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            env={**self.env, **changes},
            text=True, capture_output=True, check=False,
        )

    def called(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_help_is_read_only(self):
        result = self.call("basic")
        self.assertEqual(result.returncode, 0)
        self.assertIn("jeden silnik", result.stdout)
        self.assertFalse(self.calls.exists())

    def test_basic_check_checks_video_and_audio_without_activation(self):
        result = self.call("basic", "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["installer:--check", "audio:status"])

    def test_basic_prepare_only_prepares_video(self):
        result = self.call("basic", "prepare")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["installer:--prepare"])

    def test_basic_stereo_uses_existing_profile_manager(self):
        result = self.call("basic", "stereo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["audio:enable-service"])
        self.assertIn("Nie zmieniam domyślnego", result.stdout)

    def test_basic_activate_sequences_and_explains_microphone(self):
        result = self.call("basic", "activate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["installer:--activate", "audio:enable-service"])
        self.assertIn("Kinect2_Stereo", result.stdout)

    def test_camera_failure_never_enables_audio(self):
        result = self.call("basic", "activate", MOCK_FAIL_CAMERA="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.called(), ["installer:--activate"])

    def test_audio_failure_reports_partial_activation(self):
        result = self.call("basic", "activate", MOCK_FAIL_STEREO="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CZĘŚCIOWY SUKCES", result.stderr)
        self.assertEqual(self.called(), ["installer:--activate", "audio:enable-service"])

    def test_advanced_forwards_original_commands(self):
        result = self.call("advanced", "depth", "120")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["cli:depth 120"])

    def test_advanced_audio_status_preserves_existing_function(self):
        result = self.call("advanced", "audio")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.called(), ["audio:status"])

    def test_rejects_unknown_modes_or_basic_arguments(self):
        self.assertNotEqual(self.call("premium", "activate").returncode, 0)
        self.assertNotEqual(self.call("basic", "activate", "--unsafe").returncode, 0)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
