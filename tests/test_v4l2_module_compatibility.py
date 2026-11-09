"""Offline validation of v4l2loopback version checks; no kernel modules are touched."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "webcam/check-loopback.sh"


class V4L2ModuleCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="kinect2-loopback-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.module = root / "fake-module"
        self.bin = root / "bin"
        self.bin.mkdir()
        self.script = root / "check-loopback.sh"
        self.script.write_text(
            SOURCE.read_text().replace(
                "/sys/module/v4l2loopback", str(self.module)
            )
        )
        modinfo = self.bin / "modinfo"
        modinfo.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "-F" ] && [ "$2" = "version" ]; then\n'
            '  printf "%s\\n" "${MOCK_MOD_VERSION:-0.12.7}"\n'
            'else exit 1; fi\n'
        )
        modinfo.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}

    def call(self, mode: str, version: str | None = None):
        env = {**self.env}
        if version is not None:
            env["MOCK_MOD_VERSION"] = version
        return subprocess.run(
            ["bash", str(self.script), mode],
            text=True, capture_output=True, check=False, env=env,
        )

    def test_installed_old_module_is_rejected_before_load(self):
        result = self.call("--installed", "0.12.7")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLIENT_USAGE", result.stderr)

    def test_installed_new_module_is_accepted(self):
        result = self.call("--installed", "0.13.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.13.1", result.stdout)

    def test_loaded_old_module_is_rejected(self):
        self.module.mkdir()
        (self.module / "version").write_text("0.12.7\n")
        result = self.call("--loaded")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported", result.stderr)

    def test_loaded_new_module_is_accepted(self):
        self.module.mkdir()
        (self.module / "version").write_text("0.14.0\n")
        result = self.call("--loaded")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_loaded_required_for_activation(self):
        result = self.call("--loaded")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not loaded", result.stderr)

    def test_unknown_version_fails_closed(self):
        result = self.call("--installed", "custom-build")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unrecognized", result.stderr)


if __name__ == "__main__":
    unittest.main()
