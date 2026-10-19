"""Adapter integration uses mock rtmlib: no model files, USB, GUI or ONNX runtime."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import types
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk/python"))
from kinect2_linux import tracking as t  # noqa: E402
from kinect2_linux import tracking_rtmpose_body as adapter  # noqa: E402


class RtmposeAdapterTests(TestCase):
    def test_model_is_registered_but_not_imported_in_off(self):
        with mock.patch.object(t.importlib, "import_module") as loader:
            with t.TrackingSession("body", mode="off") as session:
                self.assertIsNone(session.process(None))
                self.assertFalse(session.loaded)
            loader.assert_not_called()

    def test_basic_does_not_load_before_first_frame(self):
        with mock.patch.object(t.importlib, "import_module") as loader:
            s = t.TrackingSession("body", mode="basic")
            self.assertFalse(s.loaded)
            loader.assert_not_called()
            s.close()

    def test_missing_local_weights_rejected_before_rtmlib_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(adapter, "DETECTOR", Path(tmp) / "det.onnx"):
                with mock.patch.object(adapter, "POSE", Path(tmp) / "pose.onnx"):
                    with self.assertRaisesRegex(t.TrackingUnavailable, "Missing local model"):
                        adapter.create_tracker()
        self.assertNotIn("rtmlib", sys.modules)

    def test_real_adapter_shapes_and_coordinates_with_fake_inference(self):
        import numpy as np
        captured = {}

        class FakeBody:
            def __init__(self, **kwargs):
                captured.update(kwargs)
            def __call__(self, image):
                self.image_shape = image.shape
                points = np.tile([image.shape[1] / 2, image.shape[0] / 2], (1, 17, 1))
                return points, np.full((1, 17), 0.85)
        fake = types.SimpleNamespace(Body=FakeBody)
        with tempfile.TemporaryDirectory() as tmp:
            det = Path(tmp) / "det.onnx"
            pose = Path(tmp) / "pose.onnx"
            det.write_bytes(b"fake")
            pose.write_bytes(b"fake")
            with mock.patch.object(adapter, "DETECTOR", det), mock.patch.object(
                adapter, "POSE", pose
            ), mock.patch.dict(sys.modules, {"rtmlib": fake}):
                obj = adapter.create_tracker()
                result = obj.process(np.zeros((240, 320, 3), dtype=np.uint8))
                obj.close()
        self.assertEqual(result.task, "body")
        self.assertEqual(len(result.subjects), 1)
        self.assertEqual(len(result.subjects[0].keypoints), 17)
        self.assertAlmostEqual(result.subjects[0].keypoints[0].x, .5)
        self.assertIsNone(result.subjects[0].keypoints[0].depth_mm)
        self.assertEqual(captured["device"], "cpu")
        self.assertEqual(captured["backend"], "onnxruntime")
        self.assertEqual(captured["det"], str(det))

    def test_empty_people_is_valid(self):
        import numpy as np
        body = adapter.RTMPoseBody.__new__(adapter.RTMPoseBody)
        body._body = lambda _: (np.empty((0, 17, 2)), np.empty((0, 17)))
        result = body.process(np.zeros((16, 16, 3), dtype=np.uint8))
        self.assertEqual(result.subjects, ())

    def test_invalid_image_refused_before_inference(self):
        import numpy as np
        body = adapter.RTMPoseBody.__new__(adapter.RTMPoseBody)
        body._body = lambda _: self.fail("Should never run")
        with self.assertRaises(TypeError):
            body.process("not an RGB frame")
        with self.assertRaises(ValueError):
            body.process(np.zeros((20, 30), dtype=np.uint8))

    def test_nonfinite_keypoints_never_leak_to_api(self):
        import numpy as np
        body = adapter.RTMPoseBody.__new__(adapter.RTMPoseBody)
        points = np.full((1, 17, 2), 4.0)
        points[0, 0, 0] = np.nan
        body._body = lambda _: (points, np.ones((1, 17)))
        result = body.process(np.zeros((20, 30, 3), dtype=np.uint8))
        self.assertEqual(result.subjects[0].keypoints[0].confidence, 0)
