"""Read-only checks for the experimental Debian/Ubuntu package builder."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEB = ROOT / "packaging/debian"


class DebianPackagingTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(
            ["bash", "-n", str(DEB / "build-deb.sh"), str(DEB / "kinect2-broker-run")],
            check=True, timeout=10,
        )

    def test_private_hardware_build_and_dynamic_dependencies(self):
        source = (DEB / "build-deb.sh").read_text()
        self.assertIn("bootstrap_libfreenect2_omp.sh", source)
        self.assertIn("KINECT2_ENABLE_HARDWARE=ON", source)
        self.assertIn("dpkg-shlibdeps", source)
        self.assertIn("ctest --test-dir", source)
        self.assertIn("git -C \"$ROOT\" archive HEAD", source)
        self.assertIn("/usr/lib/kinect2linux", source)
        self.assertIn("python3/dist-packages", source)
        self.assertIn("--root-owner-group", source)
        self.assertNotIn("systemctl --user enable", source)
        self.assertNotIn("modprobe ", source)
        self.assertNotIn("sudo ", source)

    def test_user_unit_is_never_auto_enabled(self):
        unit = (DEB / "kinect2-broker.service").read_text()
        self.assertIn("ExecStart=/usr/lib/kinect2linux/kinect2-broker-run", unit)
        self.assertIn("WantedBy=default.target", unit)
        launcher = (DEB / "kinect2-broker-run").read_text()
        self.assertIn("KINECT2_BROKER_V4L2:-0", launcher)
        self.assertIn("/usr/bin/kinect2-broker-hw", launcher)
        self.assertNotIn("sudo ", launcher)

    def test_no_microsoft_binaries_or_proprietary_models(self):
        s = (DEB / "build-deb.sh").read_text()
        for filename in ("vvtechs.dll", "exemplardb.xmplr", "KinectSDK-v2.0"):
            self.assertNotIn(filename, s)


if __name__ == "__main__":
    unittest.main()
