"""Optional Qt pixel preview smoke tests. No hardware and no display required."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
HAVE_QT = (importlib.util.find_spec("numpy") is not None and
           importlib.util.find_spec("PySide6") is not None)


@unittest.skipUnless(HAVE_QT, "PySide6/NumPy optional GUI dependencies absent")
class StudioImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No QApplication nor actual Qt window required for QImage conversions.
        import numpy as np
        from kinect2_studio import frame_image
        cls.np = np
        cls.convert = staticmethod(frame_image)

    def test_bgrx_is_converted_to_bgr_preview_and_owned(self):
        np = self.np
        bgrx = np.zeros((4, 4, 4), dtype=np.uint8)
        bgrx[:, :, :] = (7, 23, 129, 255)
        image = self.convert("rgb", bgrx)
        self.assertEqual((image.width(), image.height()), (2, 2))
        pixel = image.pixelColor(0, 0)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()), (129, 23, 7))
        bgrx[:] = 0
        self.assertEqual(image.pixelColor(0, 0).red(), 129)

    def test_pose_overlay_marks_valid_rgb_joints(self):
        from kinect2_studio import overlay_body
        from kinect2_studio_pose import skeleton_geometry
        from kinect2_linux.tracking import Keypoint, TrackedSubject, TrackingResult

        image = self.convert("rgb", self.np.zeros((200, 200, 4),
                            dtype=self.np.uint8))
        points = tuple(Keypoint(str(i), .5, .5, .9) for i in range(17))
        result = TrackingResult(
            task="body", subjects=(TrackedSubject("person", points),)
        )
        self.assertEqual(len(skeleton_geometry(result)[1]), 17)
        overlay_body(image, result)
        # A valid point is drawn at the center of the 100x100 Qt preview.
        self.assertNotEqual(image.pixelColor(49, 49).name(), "#000000")

    def test_latest_only_mailbox_drops_old_unrendered_frames(self):
        from PySide6.QtGui import QImage
        from kinect2_studio import StreamWorker
        worker = StreamWorker("rgb")
        first = QImage(2, 2, QImage.Format.Format_RGB888)
        newest = QImage(2, 2, QImage.Format.Format_RGB888)
        first.fill(0)
        newest.fill(0xffffff)
        worker._publish(first, 100, 1)
        worker._publish(newest, 200, 2)
        item = worker.take_latest()
        self.assertEqual((item[1], item[2]), (200, 2))
        self.assertEqual(item[0].pixelColor(0, 0).red(), 255)
        self.assertIsNone(worker.take_latest())

    def test_ir_invalid_readings_do_not_crash(self):
        np = self.np
        image = self.convert("ir", np.array(
            [[np.nan, np.inf], [-np.inf, 0.0]], dtype=np.float32))
        self.assertEqual((image.width(), image.height()), (2, 2))
        self.assertEqual(image.pixelColor(0, 0).red(), 0)

    def test_depth_invalid_is_black_and_mm_preview_not_recording(self):
        np = self.np
        image = self.convert("depth", np.array(
            [[np.nan, np.inf], [500.0, 4500.0]], dtype=np.float32))
        self.assertEqual((image.width(), image.height()), (2, 2))
        self.assertEqual(image.pixelColor(0, 0).red(), 0)
        self.assertGreater(image.pixelColor(0, 1).red() +
                           image.pixelColor(0, 1).blue(), 0)


if __name__ == "__main__":
    unittest.main()
