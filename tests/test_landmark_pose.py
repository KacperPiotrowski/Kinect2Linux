"""Offline tests for Kinect Face3D Stage 4 5-landmark geometry."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest
import numpy as np

path = Path(__file__).resolve().parents[1] / 'face' / 'live3d.py'
spec = importlib.util.spec_from_file_location('live3d_stage4', path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def synthetic_face():
    # Synthetic frontal eyes + nose, millimetres; NOT biometric ground truth.
    return np.array([[40, -20, 900], [28, -20, 900],
                     [-28, -20, 900], [-40, -20, 900],
                     [0, 22, 865]], dtype=np.float64)


def rot_y(deg):
    t = math.radians(deg)
    return np.array([[math.cos(t), 0, math.sin(t)],
                     [0, 1, 0], [-math.sin(t), 0, math.cos(t)]])


def rot_x(deg):
    t = math.radians(deg)
    return np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)],
                     [0, math.sin(t), math.cos(t)]])


class PoseTests(unittest.TestCase):
    def test_3d_yaw_both_directions(self):
        frontal = synthetic_face()
        neutral = mod.five_xyz_to_relative_angles(frontal)
        self.assertIsNotNone(neutral)
        center = np.array([0.0, 0.0, 880.0])
        turns = []
        for deg in [-18, 18]:
            rotated = (frontal-center) @ rot_y(deg).T + center
            value = mod.five_xyz_to_relative_angles(rotated)
            self.assertIsNotNone(value)
            turns.append(value[0]-neutral[0])
        self.assertLess(turns[0], -8)
        self.assertGreater(turns[1], 8)

    def test_3d_pitch_both_directions(self):
        frontal = synthetic_face()
        neutral = mod.five_xyz_to_relative_angles(frontal)
        center = np.array([0.0, 0.0, 880.0])
        turns = []
        for deg in [-18, 18]:
            rotated = (frontal-center) @ rot_x(deg).T + center
            value = mod.five_xyz_to_relative_angles(rotated)
            self.assertIsNotNone(value)
            turns.append(value[1]-neutral[1])
        self.assertLess(turns[0], -8)
        self.assertGreater(turns[1], 8)

    def test_depth_missing_fails(self):
        z = np.zeros((mod.H, mod.W), dtype=np.float32)
        intr = (366.47, 366.47, 255, 211)
        points = [(290, 180), (300, 180), (220, 180), (230, 180), (260, 230)]
        self.assertIsNone(mod.landmark_pose_from_five(z, points, intr))
        self.assertIsNone(mod.five_xyz_to_relative_angles([[0, 0, 900]]))

    def test_pixel_to_xyz(self):
        z = np.full((mod.H, mod.W), 900, dtype=np.float32)
        p = mod.landmark_depth_xyz(z, 255, 211, (365, 365, 255, 211))
        self.assertEqual(p, (0., 0., 900.))


if __name__ == '__main__':
    unittest.main()
