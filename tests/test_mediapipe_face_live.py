"""Offline tests for the optional MediaPipe RGB consumer (no MediaPipe or USB)."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "mediapipe_face_live", ROOT / "tools" / "mediapipe_face_live.py"
)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class Snapshot:
    kind = "rgb"
    bytes_per_pixel = 4
    width = 6
    height = 3
    host_time_us = 1000000

    def __init__(self):
        # B=7 G=31 R=119, X=255 per pixel.
        self.mapping = bytearray([7, 31, 119, 255] * (self.width * self.height))
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


class FaceLiveOfflineTests(unittest.TestCase):
    def test_bgrx_to_srgb_and_scale_keeps_own_bytes(self):
        frame = Snapshot()
        rgb = live.rgb_from_snapshot(frame, scale=3)
        self.assertEqual(rgb.shape, (1, 2, 3))
        self.assertTrue(rgb.flags.c_contiguous)
        self.assertEqual(rgb[0, 0].tolist(), [119, 31, 7])
        # Source changes after RGB conversion do not mutate inference input.
        frame.mapping[:] = bytes(len(frame.mapping))
        self.assertEqual(rgb[0, 0].tolist(), [119, 31, 7])

    def test_full_scale_and_bad_inputs(self):
        frame = Snapshot()
        self.assertEqual(live.rgb_from_snapshot(frame, scale=1).shape, (3, 6, 3))
        for n in (0, 5, -1, 1.5, True):
            with self.subTest(scale=n), self.assertRaises(ValueError):
                live.rgb_from_snapshot(frame, scale=n)
        frame.kind = "depth"
        with self.assertRaisesRegex(ValueError, "RGB"):
            live.rgb_from_snapshot(frame)

    def test_timestamps_strictly_increase(self):
        self.assertEqual(live.next_timestamp_ms(1_234_000, -1), 1234)
        self.assertEqual(live.next_timestamp_ms(1_234_000, 1234), 1235)
        self.assertEqual(live.next_timestamp_ms(2_000_000, 3000), 3001)

    def test_demo_uses_video_mode_and_independent_rgb_subscriber(self):
        received = []
        images = []

        class FakeCamera:
            def __init__(self, stream, timeout):
                self.assertion = (stream, timeout)
                received.append(self)
                self.calls = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def receive_latest(self):
                self.calls += 1
                return Snapshot(), self.calls - 1

        class FakeDetector:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def detect_for_video(self, image, timestamp_ms):
                images.append((image, timestamp_ms))
                return types.SimpleNamespace(face_landmarks=[[types.SimpleNamespace(
                    x=0.3, y=0.4)]])

            @classmethod
            def create_from_options(cls, options):
                self.assertIsNotNone(options)
                return cls()

        fake_vision = types.SimpleNamespace(
            RunningMode=types.SimpleNamespace(VIDEO="VIDEO"),
            FaceLandmarkerOptions=lambda **kw: kw,
            FaceLandmarker=FakeDetector,
        )
        mp = types.SimpleNamespace(
            tasks=types.SimpleNamespace(
                vision=fake_vision,
                BaseOptions=lambda **kw: kw,
            ),
            ImageFormat=types.SimpleNamespace(SRGB="SRGB"),
            Image=lambda image_format, data: types.SimpleNamespace(
                format=image_format, pixels=np.array(data, copy=True)
            ),
        )
        args = argparse.Namespace(model=Path("/tmp/fake-face-model.task"),
                                  max_frames=2, scale=3)
        with patch.object(live, "FrameClient", FakeCamera):
            self.assertEqual(live.run(args, mp), 0)
        self.assertEqual(received[0].assertion, ("rgb", 2.0))
        self.assertEqual(received[0].calls, 2)
        self.assertEqual(len(images), 2)
        self.assertEqual([item[1] for item in images], [1000, 1001])
        self.assertEqual(images[0][0].pixels.shape, (1, 2, 3))
        self.assertEqual(images[0][0].pixels[0, 0].tolist(), [119, 31, 7])


if __name__ == "__main__":
    unittest.main()
