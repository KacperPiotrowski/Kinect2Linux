import importlib.util
import pathlib
import struct
import unittest

import numpy as np

path = pathlib.Path(__file__).parents[1] / 'face' / 'live3d.py'
spec = importlib.util.spec_from_file_location('live3d', path)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

class Face3DTests(unittest.TestCase):
    def test_header(self):
        self.assertEqual(mod.HEADER.size, 40)
        self.assertEqual(mod.MAGIC, b'K2F3D002')
        packet = mod.HEADER.pack(mod.MAGIC, 123, 444, mod.W, mod.H, 365, 365, 255, 211)
        self.assertEqual(mod.HEADER.unpack(packet), (mod.MAGIC, 123, 444, 512, 424, 365, 365, 255, 211))

    def test_normalize(self):
        ir = np.full((mod.H, mod.W), 2000.0, dtype=np.float32)
        ir[:, :mod.W//2] = 500.0
        gray = mod.normalize_ir(ir)
        self.assertEqual(gray.dtype, np.uint8)
        self.assertEqual(gray.shape, (424, 512))
        self.assertLess(gray[0, 0], gray[0, 400])

    def test_roi(self):
        dep = np.full((mod.H, mod.W), 1000.0, dtype=np.float32)
        result = mod.face_depth(dep, (100, 80, 240, 220))
        self.assertAlmostEqual(result[0], 1000.0)
        self.assertAlmostEqual(result[1], 1.0)
        self.assertAlmostEqual(result[2], 0.0)
        dep[90:210, 105:230] = 0.0
        self.assertLess(mod.face_depth(dep, (100, 80, 240, 220))[1], 1.0)

    def test_rotation_proxy_and_guide(self):
        box = (155, 112, 355, 322)
        fx, fy, cx, cy = (365.0, 365.0, 255.0, 211.0)
        dep = np.full((mod.H, mod.W), 900.0, dtype=np.float32)
        flat = mod.rotation_proxy(dep, box, (fx, fy, cx, cy))
        self.assertIsNotNone(flat)
        self.assertAlmostEqual(flat[0], 0.0)
        self.assertAlmostEqual(flat[1], 0.0)
        # Deliberate depth tilt across X in bounding box
        dep[:,:] = 900.0 + 0.65*(np.arange(mod.W)[None,:]-255)
        turn = mod.rotation_proxy(dep, box, (fx, fy, cx, cy))
        self.assertIsNotNone(turn)
        self.assertGreater(turn[0], 10.0)
        guide = mod.MotionGuide(threshold=10)
        guide.reset(flat)
        for i in range(3):
            guide.consume(turn)
        self.assertIn('YAW+', guide.hits)

    def test_invalid_depth_rejects(self):
        dep = np.zeros((mod.H, mod.W), dtype=np.float32)
        self.assertIsNone(mod.rotation_proxy(dep, (155,112,355,322), (365,365,255,211)))

    def test_latest_overwrites(self):
        latest = mod.LatestPair()
        dep = np.ones((424,512), np.float32)
        gray = np.zeros((424,512), np.uint8)
        latest.publish(gray, dep, 1)
        latest.publish(gray, dep, 2)
        item = latest.newest(-2)
        self.assertEqual(item[3], 2)
        self.assertIsNone(latest.newest(item[0], timeout=0.01))

if __name__ == '__main__':
    unittest.main()
