"""Offline regression checks for body skeleton visualization."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk/python"))
from kinect2_linux.tracking import Keypoint, TrackedSubject, TrackingResult  # noqa: E402

spec = importlib.util.spec_from_file_location("body_preview", ROOT / "tools/demo_basic_body_cpu.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class FakeCV2:
    def __init__(self):
        self.lines = []
        self.circles = []

    def line(self, image, start, end, color, width):
        self.lines.append((start, end))

    def circle(self, image, pos, radius, color, thickness):
        self.circles.append(pos)


class FakeImage:
    shape = (480, 640, 3)


def skeleton(overrides=None):
    pts = [Keypoint(str(i), 0.5, 0.5, 0.95) for i in range(17)]
    xy = {
        5: (0.40, 0.30), 6: (0.60, 0.30),
        11: (0.43, 0.60), 12: (0.57, 0.60),
        13: (0.42, 0.75), 14: (0.58, 0.75),
        15: (0.40, 0.94), 16: (0.60, 0.94),
    }
    for i, (x, y) in xy.items():
        pts[i] = Keypoint(str(i), x, y, 0.95)
    for i, p in (overrides or {}).items():
        pts[i] = p
    return TrackingResult("body", (TrackedSubject("person", tuple(pts)),))


class BodyPreviewTests(TestCase):
    def test_torso_is_center_spine_not_box(self):
        cv = FakeCV2()
        preview.draw_body(cv, FakeImage(), skeleton())
        shoulder_mid = (round(.5 * 639), round(.3 * 479))
        hip_mid = (round(.5 * 639), round(.6 * 479))
        self.assertIn((shoulder_mid, hip_mid), cv.lines)
        left_shoulder, left_hip = (round(.4 * 639), round(.3 * 479)), (
            round(.43 * 639), round(.6 * 479))
        self.assertNotIn((left_shoulder, left_hip), cv.lines)

    def test_offscreen_leg_is_never_drawn(self):
        cv = FakeCV2()
        preview.draw_body(cv, FakeImage(), skeleton({
            15: Keypoint("left_ankle", .4, 1.1, .99)
        }))
        self.assertEqual(len(cv.circles), 16)
        knee = (round(.42 * 639), round(.75 * 479))
        ankle = (round(.4 * 639), round(1.1 * 479))
        self.assertNotIn((knee, ankle), cv.lines)

    def test_low_confidence_hip_hides_center_spine(self):
        cv = FakeCV2()
        preview.draw_body(cv, FakeImage(), skeleton({
            11: Keypoint("left_hip", .43, .60, .1)
        }))
        mid_a = (round(.5 * 639), round(.3 * 479))
        mid_b = (round(.5 * 639), round(.6 * 479))
        self.assertNotIn((mid_a, mid_b), cv.lines)

    def test_nan_joint_is_not_drawn(self):
        cv = FakeCV2()
        preview.draw_body(cv, FakeImage(), skeleton({
            9: Keypoint("left_wrist", math.nan, .5, .99)
        }))
        self.assertEqual(len(cv.circles), 16)

    def test_invalid_subject_joint_count_is_ignored(self):
        cv = FakeCV2()
        invalid = TrackingResult("body", (TrackedSubject("person", ()),))
        preview.draw_body(cv, FakeImage(), invalid)
        self.assertFalse(cv.lines)
        self.assertFalse(cv.circles)
