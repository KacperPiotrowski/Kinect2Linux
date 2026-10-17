"""Legacy launchers resolve the pinned source library without requiring Kinect hardware."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "libfreenect2_path.sh"


class Libfreenect2PathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.repo = self.workspace / "project"
        self.repo.mkdir()

    def resolve(self, override=None):
        env = os.environ.copy()
        env.pop("LIBFREENECT2_DIR", None)
        if override is not None:
            env["LIBFREENECT2_DIR"] = str(override)
        cmd = 'source "$1"; kinect2_libfreenect2_dir "$2"'
        cp = subprocess.run(
            ["bash", "-c", cmd, "test", str(HELPER), str(self.repo)],
            text=True, capture_output=True, env=env, check=True,
        )
        return cp.stdout.strip()

    def test_prioritizes_pinned_source_when_headers_exist(self):
        pinned = self.repo / "third_party" / "libfreenect2-omp"
        header = pinned / "include" / "libfreenect2" / "libfreenect2.hpp"
        header.parent.mkdir(parents=True)
        header.write_text("// test fixture")
        self.assertEqual(self.resolve(), str(pinned))

    def test_fallback_to_adjacent_legacy_checkout(self):
        legacy = self.workspace / "libfreenect2-omp"
        legacy.mkdir()
        self.assertEqual(self.resolve(), str(legacy))

    def test_explicit_external_override_takes_priority(self):
        pinned = self.repo / "third_party" / "libfreenect2-omp"
        header = pinned / "include" / "libfreenect2" / "libfreenect2.hpp"
        header.parent.mkdir(parents=True)
        header.write_text("// test fixture")
        external = self.workspace / "custom"
        external.mkdir()
        self.assertEqual(self.resolve(external), str(external))

    def test_all_launchers_source_common_helper(self):
        for path in ("kinect2", "face3d", "webcam/build.sh"):
            with self.subTest(path=path):
                code = (ROOT / path).read_text()
                self.assertIn('source "$ROOT/tools/libfreenect2_path.sh"', code)
                self.assertIn('kinect2_libfreenect2_dir "$ROOT"', code)


if __name__ == "__main__":
    unittest.main()
