"""Static offline checks for the experimental AUR packaging recipe.

These checks do not run makepkg, fetch upstream sources, install files,
change services, or touch the USB camera.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUR = ROOT / "packaging" / "arch"


class AurPackagingTests(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(
            ["bash", "-n", str(AUR / "PKGBUILD"), str(ROOT / "packaging/common/kinect2-broker-run")],
            check=True, timeout=10,
        )

    def test_pinned_private_libfreenect2(self):
        recipe = (AUR / "PKGBUILD").read_text()
        self.assertIn("fd64c5d9b214df6f6a55b4419357e51083f15d93", recipe)
        self.assertIn("85966b7dd39a1977b6f2f2b3a203f35a0d9f65e0", recipe)
        self.assertIn("14756995f96687336e6614d83f99028cc680c4d5", recipe)
        self.assertIn("git apply --check", recipe)
        self.assertIn("KINECT2_ENABLE_HARDWARE=ON", recipe)
        self.assertIn("DESTDIR=", recipe)
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("DESTINATION lib/kinect2linux", cmake)
        self.assertIn("cmake --install", recipe)
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("INSTALL_RPATH", cmake)
        self.assertIn("packaging/common/kinect2-broker-run", cmake)
        self.assertNotIn("systemctl --user enable", recipe)
        self.assertNotIn("modprobe ", recipe)

    def test_auxiliary_aur_sources_have_checksums(self):
        recipe = (AUR / "PKGBUILD").read_text()
        for basename in ("README.md",):
            self.assertIn(f"'{basename}'", recipe)
            digest = hashlib.sha256((AUR / basename).read_bytes()).hexdigest()
            self.assertIn(digest, recipe)

    def test_unit_is_opt_in_and_runs_packaged_launcher(self):
        unit = (ROOT / "packaging/common/kinect2-broker.service").read_text()
        self.assertIn("ExecStart=/usr/lib/kinect2linux/kinect2-broker-run", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertNotIn("ExecStart=/home/", unit)
        launcher = (ROOT / "packaging/common/kinect2-broker-run").read_text()
        self.assertIn("/usr/bin/kinect2-broker-hw", launcher)
        self.assertIn("--auto-streams", launcher)
        self.assertIn('KINECT2_BROKER_V4L2:-0', launcher)
        self.assertNotIn("systemctl", launcher)
        self.assertNotIn("sudo", launcher)

    def test_does_not_bundle_microsoft_models(self):
        recipe = (AUR / "PKGBUILD").read_text()
        self.assertNotIn("KinectSDK-v2.0", recipe)
        self.assertNotIn("exemplardb.xmplr", recipe)
        self.assertNotIn("vvtechs.dll", recipe)


if __name__ == "__main__":
    unittest.main()
