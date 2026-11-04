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

    def test_quality_separates_score_from_detected_joint_coverage(self):
        points = [Point(.5, .5, .9) for _ in range(17)]
        points[9] = Point(.2, .3, .2)  # left wrist below cutoff
        points[15] = Point(float("nan"), .3, .99)  # invalid left ankle
        reports = pose.pose_quality(Result((Subject(points),)))
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["visible"], 15)
        self.assertEqual(reports[0]["total"], 17)
        self.assertAlmostEqual(reports[0]["mean_model_score"], .9)
        self.assertEqual(reports[0]["missing"], ("nadgarstek L", "kostka L"))
        msg = pose.pose_quality_text(reports)
        self.assertIn("15/17", msg)
        self.assertIn("nie dokładność", msg)
        self.assertIn("kostka L", msg)

    def test_quality_absent_or_multiple_people(self):
        self.assertEqual(pose.pose_quality(Result(())), ())
        self.assertIn("Nie wykryto sylwetki",
                      pose.pose_quality_text(()))
        invisible = Subject([Point(confidence=.0) for _ in range(17)])
        visible = Subject([Point(confidence=.9) for _ in range(17)])
        reports = pose.pose_quality(Result((invisible, visible)))
        self.assertEqual(tuple(x["visible"] for x in reports), (0, 17))
        self.assertIsNone(reports[0]["mean_model_score"])
        msg = pose.pose_quality_text(reports)
        self.assertIn("Osoba 1: 0/17", msg)
        self.assertIn("Osoba 2: 17/17", msg)

    def test_tracking_off_does_not_require_models_or_qt(self):
        self.assertFalse(pose.visible(Point(confidence=None)))
        self.assertFalse(pose.visible(Point(x=float("inf"))))
        self.assertTrue(pose.visible(Point(x=0, y=1, confidence=.45)))


if __name__ == "__main__":
    unittest.main()
