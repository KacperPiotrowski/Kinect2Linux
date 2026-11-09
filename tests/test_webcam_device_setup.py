"""Mock-only V4L2 device setup tests. Never runs modprobe or touches /dev."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "webcam/device-onboot.sh"


class DeviceSetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="kinect2-devices-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.dev = root / "fake-dev"
        self.sys = root / "fake-sys"
        self.module = root / "fake-module"
        self.bin = root / "fakebin"
        self.log = root / "calls"
        self.dev.mkdir()
        self.bin.mkdir()
        self.script = root / "device-onboot.sh"
        probe = self.bin / "modprobe"
        probe.write_text(
            '#!/usr/bin/env bash\n'
            'echo "modprobe:$*" >> "$MOCK_LOG"\n'
            'mkdir -p "$MOCK_MODULE" "$MOCK_SYS/video10" "$MOCK_SYS/video11"\n'
            'ln -s /dev/null "$MOCK_DEV/video10"\n'
            'ln -s /dev/null "$MOCK_DEV/video11"\n'
            "printf 'Kinect-v2-IR\\n' > \"$MOCK_SYS/video10/name\"\n"
            "printf 'Kinect v2 RGB\\n' > \"$MOCK_SYS/video11/name\"\n"
        )
        probe.chmod(0o755)
        ctl = self.bin / "v4l2loopback-ctl"
        ctl.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "$1" == --help ]]; then\n'
            '  if [[ "${MOCK_CTL_ADD:-0}" == 1 ]]; then echo "  add DEVICE"; '
            'else echo "  set-fps FPS"; fi\n'
            '  if [[ "${MOCK_CTL_HELP_FAIL:-0}" == 1 ]]; then exit 1; fi\n'
            'elif [[ "$1" == add ]]; then\n'
            '  echo "add:$*" >> "$MOCK_LOG"\n'
            '  ln -s /dev/null "$MOCK_DEV/video11"\n'
            '  mkdir -p "$MOCK_SYS/video11"\n'
            "  printf 'Kinect v2 RGB\\n' > \"$MOCK_SYS/video11/name\"\n"
            'else exit 2; fi\n'
        )
        ctl.chmod(0o755)
        code = SOURCE.read_text()
        for a, b in [
            ("/sys/module/v4l2loopback", str(self.module)),
            ("/sys/class/video4linux", str(self.sys)),
            ("/dev/video10", str(self.dev / "video10")),
            ("/dev/video11", str(self.dev / "video11")),
            ("/usr/bin/modprobe", str(probe)),
            ("/usr/sbin/modprobe", str(probe)),
            ("/usr/bin/v4l2loopback-ctl", str(ctl)),
            ("/usr/sbin/v4l2loopback-ctl", str(ctl)),
            # Fake /dev/null symlinks stand in for character devices
            # only inside the copied test script, never production code.
            ("[[ -c /dev/$device && ! -L /dev/$device ]]",
             '[[ -e "$MOCK_DEV/$device" ]]'),
        ]:
            code = code.replace(a, b)
        self.script.write_text(code)
        self.env = {
            **os.environ,
            "MOCK_DEV": str(self.dev),
            "MOCK_SYS": str(self.sys),
            "MOCK_MODULE": str(self.module),
            "MOCK_LOG": str(self.log),
        }

    def run_script(self, **env):
        return subprocess.run(
            ["bash", str(self.script)],
            env={**self.env, **env},
            text=True, capture_output=True, check=False,
        )

    def loaded_ir(self):
        self.module.mkdir()
        (self.dev / "video10").symlink_to("/dev/null")
        (self.sys / "video10").mkdir(parents=True)
        (self.sys / "video10/name").write_text("Kinect-v2-IR\n")

    def test_unloaded_012_creates_both_in_one_modprobe(self):
        result = self.run_script(MOCK_CTL_ADD="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("devices=2", self.log.read_text())
        self.assertIn("video_nr=10,11", self.log.read_text())
        self.assertTrue((self.dev / "video11").exists())

    def test_old_loaded_without_rgb_fails_without_unloading_ir(self):
        self.loaded_ir()
        result = self.run_script(MOCK_CTL_ADD="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no dynamic add", result.stderr)
        self.assertFalse((self.dev / "video11").exists())
        self.assertFalse(self.log.exists())
        self.assertTrue((self.dev / "video10").exists())

    def test_loaded_with_dynamic_add_only_creates_missing_rgb(self):
        self.loaded_ir()
        result = self.run_script(MOCK_CTL_ADD="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("add:", self.log.read_text())
        self.assertNotIn("modprobe:", self.log.read_text())

    def test_loaded_dynamic_add_even_if_help_returns_failure(self):
        self.loaded_ir()
        result = self.run_script(MOCK_CTL_ADD="1", MOCK_CTL_HELP_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("add:", self.log.read_text())

    def test_idempotent_when_both_named_devices_exist(self):
        self.loaded_ir()
        (self.dev / "video11").symlink_to("/dev/null")
        (self.sys / "video11").mkdir(parents=True)
        (self.sys / "video11/name").write_text("Kinect v2 RGB\n")
        result = self.run_script(MOCK_CTL_ADD="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_refuses_foreign_rgb_without_changing_device(self):
        self.loaded_ir()
        (self.dev / "video11").symlink_to("/dev/null")
        (self.sys / "video11").mkdir(parents=True)
        (self.sys / "video11/name").write_text("Foreign Camera\n")
        result = self.run_script(MOCK_CTL_ADD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
