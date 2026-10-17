"""Offline user-service installer checks. No Kinect, USB or real systemd."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = "tools/run_broker_service.sh"
INSTALLER = "tools/install_broker_user.sh"


class UserBrokerServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kinect2-unit-")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "repository"
        self.home = base / "home"
        self.mockbin = base / "fakebin"
        self.runtime = base / "runtime"
        for folder in (self.home, self.mockbin, self.runtime,
                       self.root / "tools", self.root / "bin"):
            folder.mkdir(parents=True, exist_ok=True)
        self.runtime.chmod(0o700)
        for name in (LAUNCHER, INSTALLER):
            shutil.copyfile(SOURCE_ROOT / name, self.root / name)
        self.broker = self.root / "bin" / "kinect2-broker-hw"
        self.broker.write_text(
            '#!/usr/bin/env bash\n'
            'printf "args=%s\\n" "$*" > "$MOCK_BROKER_LOG"\n'
            'printf "omp=%s\\n" "$OMP_NUM_THREADS" >> "$MOCK_BROKER_LOG"\n'
            'printf "dynamic=%s\\n" "$OMP_DYNAMIC" >> "$MOCK_BROKER_LOG"\n'
        )
        self.broker.chmod(0o755)
        self.log = base / "systemctl.txt"
        self.broker_log = base / "broker.txt"
        ctl = self.mockbin / "systemctl"
        ctl.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_SYSTEMCTL_LOG"\n')
        ctl.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "MOCK_SYSTEMCTL_LOG": str(self.log),
            "MOCK_BROKER_LOG": str(self.broker_log),
            "PATH": f"{self.mockbin}:" + os.environ.get("PATH", ""),
        })

    def run_install(self, *args):
        return subprocess.run(
            ["bash", str(self.root / INSTALLER), *args],
            env=self.env, capture_output=True, text=True, check=False,
        )

    def test_install_is_opt_in_not_autostart(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = self.home / ".config/systemd/user/kinect2-broker.service"
        self.assertTrue(unit.is_file())
        text = unit.read_text()
        self.assertIn("WantedBy=default.target", text)
        self.assertIn("ExecStart=/usr/bin/bash %h/.local/bin/kinect2-broker-run", text)
        self.assertIn("Restart=on-failure", text)
        self.assertNotIn("kinect2-rgb-webcam.service", text)
        self.assertEqual(self.log.read_text().splitlines(), ["--user daemon-reload"])
        link = self.home / ".local/bin/kinect2-broker-run"
        self.assertEqual(link.resolve(), self.root / LAUNCHER)
        self.assertEqual(self.run_install().returncode, 0)  # idempotent

    def test_enable_requires_explicit_switch(self):
        result = self.run_install("--enable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [
            "--user daemon-reload",
            "--user enable --now kinect2-broker.service",
        ])

    def test_refuses_foreign_user_unit(self):
        unit = self.home / ".config/systemd/user/kinect2-broker.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStart=/usr/bin/true\n")
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to overwrite", result.stderr)
        self.assertIn("ExecStart=/usr/bin/true", unit.read_text())
        self.assertFalse(self.log.exists())

    def test_refuses_foreign_launcher_symlink(self):
        link = self.home / ".local/bin/kinect2-broker-run"
        link.parent.mkdir(parents=True)
        link.symlink_to("/usr/bin/true")
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to overwrite", result.stderr)
        self.assertEqual(os.readlink(link), "/usr/bin/true")
        self.assertFalse(self.log.exists())

    def test_launcher_only_execs_single_native_broker(self):
        result = subprocess.run(
            ["bash", str(self.root / LAUNCHER)],
            env=self.env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.broker_log.read_text().splitlines(), [
            "args=--allow-device-control --frame-preview --auto-streams",
            "omp=4", "dynamic=FALSE",
        ])

    def test_launcher_requires_runtime_dir(self):
        env = dict(self.env)
        env.pop("XDG_RUNTIME_DIR")
        result = subprocess.run(
            ["bash", str(self.root / LAUNCHER)],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XDG_RUNTIME_DIR", result.stderr)
        self.assertFalse(self.broker_log.exists())

    def test_install_fails_without_hardware_build(self):
        self.broker.unlink()
        result = self.run_install("--enable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Build it first", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.home / ".config/systemd/user/kinect2-broker.service").exists())


if __name__ == "__main__":
    unittest.main()
