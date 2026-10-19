"""Offline SDK buffer contract; no camera, USB or OpenCV needed."""
import importlib.util
import mmap
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from kinect2_linux.frame_client import FrameSnapshot, FrameProtocolError
from kinect2_linux.frame_arrays import frame_to_numpy


@unittest.skipUnless(importlib.util.find_spec("numpy") is not None,
                     "optional NumPy dependency not installed")
class SDKFrameArraysTests(unittest.TestCase):
    def make_frame(self, kind, data, width=2, height=1, bpp=4):
        backing = tempfile.TemporaryFile()
        backing.write(data)
        backing.flush()
        mapping = mmap.mmap(backing.fileno(), len(data), access=mmap.ACCESS_READ)
        backing.close()
        return FrameSnapshot(kind, width, height, bpp, 7, 123, mapping)

    def test_rgb_is_bgrx_and_default_copy_survives_close(self):
        frame = self.make_frame("rgb", bytes((1, 2, 3, 255, 10, 20, 30, 0)))
        array = frame_to_numpy(frame)
        self.assertEqual(array.shape, (1, 2, 4))
        self.assertEqual(array.dtype.name, "uint8")
        self.assertEqual(array[0, 0].tolist(), [1, 2, 3, 255])
        frame.close()
        self.assertEqual(array[0, 1].tolist(), [10, 20, 30, 0])
        self.assertTrue(array.flags.writeable)

    def test_ir_and_depth_keep_float32_without_rescaling(self):
        for stream in ("ir", "depth"):
            with self.subTest(stream=stream):
                frame = self.make_frame(stream, struct.pack("<ff", 123.5, 1500.25))
                array = frame.as_numpy()
                frame.close()
                self.assertEqual(array.shape, (1, 2))
                self.assertEqual(array.dtype.name, "float32")
                self.assertEqual(array.tolist(), [[123.5, 1500.25]])

    def test_zero_copy_is_readonly_and_borrows_frame_mapping(self):
        frame = self.make_frame("depth", struct.pack("<ff", 800., 900.))
        view = frame.as_numpy(copy=False)
        self.assertFalse(view.flags.writeable)
        self.assertEqual(view[0, 1], 900.)
        del view  # required before the mmap owner closes
        frame.close()

    def test_refuses_unknown_kind_and_invalid_geometry(self):
        for kind, width, height, bpp, data in (
            ("other", 2, 1, 4, b"\x00" * 8),
            ("rgb", 2, 1, 1, b"\x00" * 8),
            ("ir", 0, 1, 4, b"\x00" * 8),
            ("depth", 2, 1, 4, b"\x00" * 4),
        ):
            with self.subTest(kind=kind, width=width, bpp=bpp, size=len(data)):
                frame = self.make_frame(kind, data, width, height, bpp)
                with self.assertRaises(FrameProtocolError):
                    frame_to_numpy(frame)
                frame.close()

    def test_rejects_non_boolean_copy_flag(self):
        frame = self.make_frame("ir", b"\x00" * 8)
        try:
            for flag in (0, 1, "false", None):
                with self.subTest(flag=flag), self.assertRaises(TypeError):
                    frame_to_numpy(frame, copy=flag)
        finally:
            frame.close()


if __name__ == "__main__":
    unittest.main()
