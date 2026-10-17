"""Offline installer tests: no real systemd, USB or privileged operations."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools/install_kinect2.sh"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kinect2-installer-")
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        self.repo, self.home, self.mockbin = p / "repo", p / "home", p / "mockbin"
        for path in (self.repo / "tools", self.repo / "bin", self.home, self.mockbin):
            path.mkdir(parents=True, exist_ok=True)
        self.log = p / "calls"
        self.dev = p / "video11"
        self.dev.symlink_to("/dev/null")  # char device, no writes to /dev
        self.sysname = p / "video-name"
        self.sysname.write_text("Kinect v2 RGB\n")
        # Replace production hardware paths only in a private TEST copy.
        code = SOURCE.read_text().replace(
            "DEVICE=/dev/video11", f"DEVICE={self.dev}"
        ).replace(
            "NAME_FILE=/sys/class/video4linux/video11/name",
            f"NAME_FILE={self.sysname}",
        )
        self.installer = self.repo / "tools/install_kinect2.sh"
        self.installer.write_text(code)
        ctl = self.mockbin / "systemctl"
        ctl.write_text("""#!/usr/bin/env bash
if [[ "$1" == --user && "$2" == is-active ]]; then
  if [[ "$3" == kinect2-rgb-webcam.service ]]; then
    echo "${MOCK_LEGACY_ACTIVE:-inactive}"
  else
    echo "${MOCK_BROKER_ACTIVE:-inactive}"
  fi
elif [[ "$1" == --user && "$2" == show-environment ]]; then
  [[ "${MOCK_USER_BUS_FAIL:-0}" != 1 ]]
elif [[ "$1" == --user && "$2" == is-enabled ]]; then
  if [[ "$3" == kinect2-rgb-webcam.service ]]; then
    echo "${MOCK_LEGACY_ENABLED:-disabled}"
  else
    echo disabled
  fi
else
  echo "$*" >> "$MOCK_CALL_LOG"
fi
""".replace("\\${", "${"))
        ctl.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), MOCK_CALL_LOG=str(self.log))
        self.env["PATH"] = str(self.mockbin) + ":" + os.environ["PATH"]

    def call(self, arg, **changes):
        return subprocess.run(
            ["bash", str(self.installer), arg],
            env={**self.env, **changes}, text=True, capture_output=True, check=False,
        )

    def managed(self):
        unit = self.home / ".config/systemd/user/kinect2-broker.service"
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(
            "# Managed by Kinect2-Linux broker installer.\n"
            "ExecStart=/usr/bin/bash %h/.local/bin/kinect2-broker-run\n"
        )
        launcher = self.home / ".local/bin/kinect2-broker-run"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.symlink_to(self.repo / "tools/run_broker_service.sh")
        (self.repo / "tools/run_broker_service.sh").write_text("#!/bin/sh\n")
        binpath = self.repo / "bin/kinect2-broker-hw"
        binpath.write_text("#!/bin/sh\nexit 0\n")
        binpath.chmod(0o755)

    def test_check_does_not_write_or_activate(self):
        result = self.call("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preflight complete", result.stdout)
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse(self.log.exists())

    def test_prepare_uses_build_and_tests_without_activation(self):
        for name in ("bootstrap_libfreenect2_omp.sh",
                     "build_broker.sh", "install_broker_user.sh"):
            (self.repo / "tools" / name).write_text(
                f'#!/usr/bin/env bash\necho "{name}:$*" >> "$MOCK_CALL_LOG"\n'
            )
        for name in ("test_auto_capture", "test_v4l2_rgb"):
            exe = self.repo / "bin" / name
            exe.write_text(f'#!/bin/sh\necho "{name}" >> "$MOCK_CALL_LOG"\n')
            exe.chmod(0o755)
        result = self.call("--prepare")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [
            "bootstrap_libfreenect2_omp.sh:",
            "build_broker.sh:--with-hardware",
            "test_auto_capture", "test_v4l2_rgb",
            "install_broker_user.sh:",
        ])

    def test_refuses_legacy_active_or_enabled(self):
        self.managed()
        for override in ({"MOCK_LEGACY_ACTIVE": "active"},
                         {"MOCK_LEGACY_ENABLED": "enabled"}):
            result = self.call("--activate", **override)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Legacy RGB", result.stderr)
        self.assertFalse(self.log.exists())

    def test_refuses_foreign_device_and_active_broker(self):
        self.managed()
        self.sysname.write_text("Not Kinect\n")
        self.assertNotEqual(self.call("--activate").returncode, 0)
        self.sysname.write_text("Kinect v2 RGB\n")
        result = self.call("--activate", MOCK_BROKER_ACTIVE="active")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already active", result.stderr)

    def test_refuses_existing_foreign_dropin(self):
        self.managed()
        drop = self.home / ".config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf"
        drop.parent.mkdir(parents=True)
        drop.write_text("[Service]\nEnvironment=FOREIGN=1\n")
        result = self.call("--activate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to overwrite", result.stderr)
        self.assertIn("FOREIGN=1", drop.read_text())
        self.assertFalse(self.log.exists())

    def test_activate_fails_without_systemd_user_manager(self):
        self.managed()
        result = self.call("--activate", MOCK_USER_BUS_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("user manager unavailable", result.stderr)
        self.assertFalse(self.log.exists())

    def test_activate_rejects_foreign_launcher_or_execstart(self):
        self.managed()
        launcher = self.home / ".local/bin/kinect2-broker-run"
        launcher.unlink()
        launcher.symlink_to("/usr/bin/true")
        result = self.call("--activate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launcher", result.stderr)
        launcher.unlink()
        launcher.symlink_to(self.repo / "tools/run_broker_service.sh")
        unit = self.home / ".config/systemd/user/kinect2-broker.service"
        unit.write_text("# Managed by Kinect2-Linux broker installer.\\nExecStart=/usr/bin/true\\n")
        result = self.call("--activate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ExecStart", result.stderr)
        self.assertFalse(self.log.exists())

    def test_activate_requires_explicit_opt_in(self):
        self.managed()
        result = self.call("--activate")
        self.assertEqual(result.returncode, 0, result.stderr)
        drop = self.home / ".config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf"
        self.assertEqual(drop.read_text(), "[Service]\nEnvironment=KINECT2_BROKER_V4L2=1\n")
        self.assertEqual(self.log.read_text().splitlines(), [
            "--user daemon-reload", "--user enable --now kinect2-broker.service"
        ])


if __name__ == "__main__":
    unittest.main()
