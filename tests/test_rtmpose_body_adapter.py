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
            ), mock.patch.dict(sys.modules, {"rtmlib": fake}), mock.patch.dict(
                os.environ, {adapter.THREADS_ENV: "0", adapter.NO_SPIN_ENV: "0"}
            ):
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


    def test_out_of_frame_joint_confidence_is_zero(self):
        import numpy as np
        body = adapter.RTMPoseBody.__new__(adapter.RTMPoseBody)
        points = np.full((1, 17, 2), 5.0)
        points[0, 15] = [8.0, 50.0]  # ankle below a 16x16 frame
        body._body = lambda _: (points, np.ones((1, 17)))
        result = body.process(np.zeros((16, 16, 3), dtype=np.uint8))
        joint = result.subjects[0].keypoints[15]
        self.assertEqual(joint.confidence, 0.0)
        self.assertLessEqual(joint.y, 1.0)


    def test_hardware_selected_basic_defaults_are_lazy_and_bounded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(adapter._cpu_tuning(), (1, True))
        # Advanced can still explicitly restore an untuned RTMLib baseline.
        with mock.patch.dict(os.environ, {
            adapter.THREADS_ENV: "0", adapter.NO_SPIN_ENV: "0"
        }, clear=True):
            self.assertEqual(adapter._cpu_tuning(), (0, False))

    def test_cpu_tuning_rejects_invalid_values(self):
        for value in ("-1", "foo", "999", "4.5"):
            with self.subTest(value=value), mock.patch.dict(
                os.environ, {adapter.THREADS_ENV: value}, clear=False
            ):
                with self.assertRaises(t.TrackingUnavailable):
                    adapter._cpu_tuning()
        with mock.patch.dict(os.environ, {adapter.NO_SPIN_ENV: "maybe"}):
            with self.assertRaises(t.TrackingUnavailable):
                adapter._cpu_tuning()

    def test_defaults_do_not_import_onnxruntime(self):
        with mock.patch.dict(os.environ, {
            adapter.THREADS_ENV: "0",
            adapter.NO_SPIN_ENV: "0",
        }):
            self.assertEqual(adapter._cpu_tuning(), (0, False))
        # No runtime to retune means no additional model imports or allocation.
        with mock.patch.dict(sys.modules, {"onnxruntime": None}):
            adapter._retune_ort_sessions(object(), 0, False)

    def test_retuned_sessions_use_explicit_cpu_threads_without_affinity(self):
        fake_ort = types.SimpleNamespace()
        instances = []

        class FakeOptions:
            def __init__(self):
                self.intra_op_num_threads = 0
                self.inter_op_num_threads = 0
                self.execution_mode = None
                self.entries = {}

            def add_session_config_entry(self, key, value):
                self.entries[key] = value

        def fake_session(path, *, sess_options, providers):
            instances.append((path, sess_options, providers))
            return object()

        fake_ort.SessionOptions = FakeOptions
        fake_ort.ExecutionMode = types.SimpleNamespace(ORT_SEQUENTIAL="SEQUENTIAL")
        fake_ort.InferenceSession = fake_session
        detector = types.SimpleNamespace(session=object())
        poser = types.SimpleNamespace(session=object())
        body = types.SimpleNamespace(det_model=detector, pose_model=poser)
        with mock.patch.dict(sys.modules, {"onnxruntime": fake_ort}):
            adapter._retune_ort_sessions(body, 4, True)
        self.assertEqual(len(instances), 2)
        self.assertEqual([p[2] for p in instances],
                         [["CPUExecutionProvider"], ["CPUExecutionProvider"]])
        self.assertEqual([p[0] for p in instances], [str(adapter.DETECTOR), str(adapter.POSE)])
        self.assertTrue(all(p[1].intra_op_num_threads == 4 for p in instances))
        self.assertTrue(all(p[1].inter_op_num_threads == 1 for p in instances))
        self.assertEqual(instances[0][1].execution_mode, "SEQUENTIAL")
        self.assertEqual(instances[0][1].entries, {
            "session.intra_op.allow_spinning": "0",
            "session.inter_op.allow_spinning": "0",
        })
        self.assertIsNotNone(detector.session)
        self.assertIsNotNone(poser.session)

    def test_retune_refuses_unsupported_rtmlib_layout(self):
        fake_ort = types.SimpleNamespace(SessionOptions=lambda: object())
        with mock.patch.dict(sys.modules, {"onnxruntime": fake_ort}):
            with self.assertRaisesRegex(t.TrackingUnavailable, "Unsupported RTMLib"):
                adapter._retune_ort_sessions(object(), 4, True)

    def test_nonfinite_keypoints_never_leak_to_api(self):
        import numpy as np
        body = adapter.RTMPoseBody.__new__(adapter.RTMPoseBody)
        points = np.full((1, 17, 2), 4.0)
        points[0, 0, 0] = np.nan
        body._body = lambda _: (points, np.ones((1, 17)))
        result = body.process(np.zeros((20, 30, 3), dtype=np.uint8))
        self.assertEqual(result.subjects[0].keypoints[0].confidence, 0)
