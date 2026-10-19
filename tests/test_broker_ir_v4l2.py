"""Offline tests: no Kinect, V4L2 access, Howdy, PAM or actual devices."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ir_bridge", ROOT / "tools/broker_ir_v4l2.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IRBridgeTests(unittest.TestCase):
    def test_read_only_check_does_not_open_bridge(self):
        with mock.patch.object(module, "check_device") as check, mock.patch.object(
            module, "bridge"
        ) as bridge:
            self.assertEqual(module.main(["--check"]), 0)
            check.assert_called_once()
            bridge.assert_not_called()

    def test_v4l2_ioctl_layout(self):
        self.assertEqual(module.ctypes.sizeof(module.V4L2Format), 208)
        self.assertEqual(module.VIDIOC_S_FMT, 0xC0D05605)

    def test_refuses_wrong_ir_name(self):
        with mock.patch.object(module.Path, "read_text", return_value="USB Camera\n"):
            with self.assertRaisesRegex(RuntimeError, "unexpected"):
                module.check_device()

    def test_refuses_regular_file_named_as_video_device(self):
        with mock.patch.object(module.Path, "read_text", return_value="Kinect-v2-IR\n"), \
             mock.patch.object(module.os, "stat",
                               return_value=types.SimpleNamespace(st_mode=0o100644)):
            with self.assertRaisesRegex(RuntimeError, "character"):
                module.check_device()

    def test_yuyv_format_settings_and_validation(self):
        def good_ioctl(fd, code, data, mutate):
            self.assertEqual(code, module.VIDIOC_S_FMT)
            view = module.V4L2Format.from_buffer(data)
            self.assertEqual((view.fmt.pix.width, view.fmt.pix.height), (512, 424))
            self.assertEqual(view.fmt.pix.pixelformat, module.YUYV)
            return 0
        with mock.patch.object(module.fcntl, "ioctl", side_effect=good_ioctl):
            module.configure(4)

    def test_rejects_wrong_negotiated_size(self):
        def bad_ioctl(fd, code, data, mutate):
            module.V4L2Format.from_buffer(data).fmt.pix.width = 320
            return 0
        with mock.patch.object(module.fcntl, "ioctl", side_effect=bad_ioctl):
            with self.assertRaisesRegex(RuntimeError, "refused"):
                module.configure(4)

    def test_black_size_and_yuyv_chroma(self):
        value = module.black_frame()
        self.assertEqual(len(value), module.OUTPUT_BYTES)
        self.assertEqual(value[:8], bytes((16, 128, 16, 128)) * 2)

    def test_ir_float_to_yuyv_and_nonfinite(self):
        import numpy as np
        array = np.full((424, 512), 300.0, dtype=np.float32)
        array[::4, ::4] = 700.0
        array[-1, -1] = np.nan
        converted = module.IRConverter().convert(array)
        self.assertEqual(len(converted), module.OUTPUT_BYTES)
        self.assertEqual(converted[1::2], b"\x80" * (424 * 512))
        self.assertEqual(converted[-2], 0)
        self.assertGreater(converted[0], 0)

    def test_ir_rejects_wrong_shape(self):
        import numpy as np
        with self.assertRaisesRegex(ValueError, "424x512"):
            module.IRConverter().convert(np.zeros((5, 5), dtype=np.float32))

    def test_write_never_retries_partial_frame(self):
        with mock.patch.object(module.os, "write", return_value=2) as writer:
            with self.assertRaisesRegex(OSError, "short write"):
                module.write_frame(4, module.black_frame())
            writer.assert_called_once()

    def test_full_writer_drop_on_nonblocking(self):
        with mock.patch.object(module.os, "write",
                               side_effect=BlockingIOError):
            self.assertFalse(module.write_frame(4, module.black_frame()))
