import struct
import unittest
from mask_reference import (preprocess_r16_uint, compute_dispatch_groups,
                            SOURCE_WIDTH, SOURCE_HEIGHT, MAX_TILES)


def make_image(points=(), fill=0):
    buf = bytearray(SOURCE_WIDTH * SOURCE_HEIGHT * 2)
    if fill:
        buf[:] = struct.pack("<H", fill) * (SOURCE_WIDTH * SOURCE_HEIGHT)
    for x, y, val in points:
        struct.pack_into("<H", buf, (y * SOURCE_WIDTH + x) * 2, val)
    return bytes(buf)


class TestObservedPreprocessing(unittest.TestCase):
    def test_empty_source(self):
        r = preprocess_r16_uint(make_image())
        self.assertEqual(r.active_sample_count, 0)
        self.assertEqual(r.worklist, ())
        self.assertEqual(len(r.sampled_mask), 256 * 212)
        self.assertEqual(len(r.reduced_mask), 128 * 106)
        self.assertEqual(len(r.padded_worklist), MAX_TILES)

    def test_low_three_bits_only(self):
        r = preprocess_r16_uint(make_image([(0, 0, 0x8000), (2, 0, 0x8005)]))
        self.assertEqual(r.active_sample_count, 1)
        self.assertEqual(r.sampled_mask[:2], b"\x00\x05")
        self.assertEqual(r.reduced_mask[0], 5)
        self.assertEqual(r.worklist, (0,))

    def test_odd_pixel_coordinates_are_not_sampled(self):
        r = preprocess_r16_uint(make_image([(1, 0, 7), (0, 1, 7), (1, 1, 7)]))
        self.assertEqual(r.worklist, ())

    def test_boundary_last_tile(self):
        r = preprocess_r16_uint(make_image([(510, 422, 7)]))
        self.assertEqual(r.active_sample_count, 1)
        self.assertEqual(r.worklist, (MAX_TILES - 1,))

    def test_mask_or_is_bitwise_not_boolean(self):
        r = preprocess_r16_uint(make_image([(0, 0, 1), (2, 0, 2),
                                             (0, 2, 4)]))
        self.assertEqual(r.active_sample_count, 3)
        self.assertEqual(r.reduced_mask[0], 7)
        self.assertEqual(r.worklist, (0,))

    def test_visit_order_is_column_major_but_ids_are_row_major(self):
        r = preprocess_r16_uint(make_image([(0, 0, 1), (0, 8, 1),
                                             (8, 0, 1)]))
        self.assertEqual(r.worklist, (0, 64, 1))

    def test_dispatch_size(self):
        self.assertEqual(compute_dispatch_groups(0, has_output_buffer=True), 0)
        self.assertEqual(compute_dispatch_groups(5, has_output_buffer=True), 2)
        self.assertEqual(compute_dispatch_groups(MAX_TILES, has_output_buffer=True), 848)
        self.assertEqual(compute_dispatch_groups(0, has_output_buffer=False), 3392)

    def test_fully_active_source(self):
        r = preprocess_r16_uint(make_image(fill=0x8007))
        self.assertEqual(r.active_sample_count, 256 * 212)
        self.assertEqual(len(r.worklist), MAX_TILES)
        self.assertEqual(len(set(r.worklist)), MAX_TILES)
        self.assertEqual(r.worklist[:3], (0, 64, 128))
        self.assertEqual(r.worklist[-1], 3391)

    def test_input_length_validation(self):
        with self.assertRaises(ValueError):
            preprocess_r16_uint(b"\0" * 12)


if __name__ == "__main__":
    unittest.main()
