"""Offline 2D skeleton tests; no Qt, USB, camera or AI model loading."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kinect2_studio_pose", ROOT / "tools/kinect2_studio_pose.py"
)
pose = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pose)


class Point:
    def __init__(self, x=.5, y=.5, confidence=.8):
        self.x, self.y, self.confidence = x, y, confidence


class Subject:
    kind = "person"

    def __init__(self, points):
        self.keypoints = tuple(points)


class Result:
    def __init__(self, subjects):
        self.subjects = tuple(subjects)


class PoseTests(unittest.TestCase):
    def test_valid_person_has_joints_bones_and_virtual_spine(self):
        points = [Point(.5, .5) for _ in range(17)]
        points[5], points[6] = Point(.3, .25), Point(.7, .25)
        points[11], points[12] = Point(.35, .7), Point(.65, .7)
        lines, joints = pose.skeleton_geometry(Result((Subject(points),)))
        self.assertEqual(len(joints), 17)
        self.assertEqual(len(lines), len(pose.BONES) + 1)
        self.assertEqual(lines[-1], ((.5, .25), (.5, .7)))

    def test_low_confidence_and_nonfinite_points_are_not_fabricated(self):
        points = [Point(.1, .1, 0) for _ in range(17)]
        points[5] = Point(.3, .25, .9)
        points[6] = Point(float("nan"), .25, .9)
        points[7] = Point(1.2, .35, .9)
        points[11] = Point(.5, .7, float("inf"))
        lines, joints = pose.skeleton_geometry(Result((Subject(points),)))
        self.assertEqual(lines, [])
        self.assertEqual(joints, [(.3, .25)])

    def test_unexpected_subject_and_unverified_geometry_are_ignored(self):
        short = Subject([Point()] * 16)
        not_person = Subject([Point()] * 17)
        not_person.kind = "other"
        lines, joints = pose.skeleton_geometry(Result((short, not_person)))
        self.assertEqual(lines, [])
        self.assertEqual(joints, [])

    def test_tracking_off_does_not_require_models_or_qt(self):
        self.assertFalse(pose.visible(Point(confidence=None)))
        self.assertFalse(pose.visible(Point(x=float("inf"))))
        self.assertTrue(pose.visible(Point(x=0, y=1, confidence=.45)))


if __name__ == "__main__":
    unittest.main()
