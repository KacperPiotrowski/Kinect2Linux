"""Offline tests; no camera or Qt GUI required."""
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
import sys

import numpy as np

path = Path(__file__).resolve().parents[1] / 'face' / 'live3d.py'
spec = importlib.util.spec_from_file_location('live3d_stage3', path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.ir = np.full((mod.H, mod.W), 1000.0, dtype=np.float32)
        self.depth = np.full((mod.H, mod.W), 900.0, dtype=np.float32)
        self.box = (155, 112, 355, 322)
        self.e = mod.GuidedEnrollment(threshold=12, min_samples=7, min_hold=.4)
        self.e.start()
        self.seq = 1
        self.tm = 1000.0

    def frame(self, pose, depth=None, boxes=None, when=None):
        self.tm = self.tm + .12 if when is None else when
        r = mod.Result(boxes=(self.box,) if boxes is None else boxes,
                       seq=self.seq, arrived_at=self.tm, pose=pose,
                       ir_raw=self.ir,
                       depth_raw=self.depth if depth is None else depth,
                       intrinsics=(366.47, 366.47, 255, 211))
        self.seq += 1
        return r

    def pass_step(self, pose):
        for _ in range(7):
            self.e.consume(self.frame(pose), now=self.tm+.01)

    def test_all_angles_and_save(self):
        self.pass_step((0, 0))
        self.assertEqual(self.e.step, 'YAW-')
        self.pass_step((-16, 0))
        self.pass_step((16, 0))
        self.pass_step((0, -16))
        self.pass_step((0, 16))
        self.assertTrue(self.e.completed)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(self.e.save(temp))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            manifest = path/'manifest.json'
            self.assertTrue(manifest.exists())
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)
            self.assertEqual(len(list(path.glob('*.npz'))), 5)
            with np.load(path/'front.npz') as sample:
                self.assertEqual(sample['ir'].dtype, np.float32)
                self.assertEqual(sample['depth'].dtype, np.float32)
                self.assertEqual(sample['ir'].shape, (210, 200))
            self.assertEqual(self.e.save(temp), str(path))

    def test_single_detection_seq_once(self):
        r = self.frame((0,0))
        self.e.consume(r,now=self.tm+.01)
        self.e.consume(r,now=self.tm+.01)
        self.assertEqual(len(self.e.candidate),1)

    def test_missing_depth_and_multiple_faces_reject(self):
        empty = np.zeros_like(self.depth)
        self.e.consume(self.frame((0,0),depth=empty),now=self.tm+.01)
        self.assertEqual(self.e.candidate, [])
        self.e.consume(self.frame((0,0),boxes=(self.box,self.box)),now=self.tm+.01)
        self.assertEqual(self.e.candidate, [])

    def test_stale_result_clears_streak(self):
        self.e.consume(self.frame((0,0)),now=self.tm+.01)
        self.assertEqual(len(self.e.candidate),1)
        r = self.frame((0,0))
        self.e.consume(r,now=self.tm+1.0)
        self.assertFalse(self.e.candidate)

    def test_translation_not_turn(self):
        self.pass_step((0,0))
        self.assertEqual(self.e.step,'YAW-')
        self.pass_step((0,0))
        self.assertEqual(self.e.step,'YAW-')

    def test_incomplete_never_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):
                self.e.save(temp)
            self.assertEqual(list(Path(temp).iterdir()), [])

if __name__ == '__main__':
    unittest.main()
