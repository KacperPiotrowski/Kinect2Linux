"""Optional Vulkan hardware/software-ICD parity tests.

Run through the dedicated CI job (Mesa lavapipe) or set both:
KINECT2_VULKAN_RUNNER, KINECT2_VULKAN_SHADER.
"""
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mask-reference"))
from mask_reference import (  # noqa: E402
    MAX_TILES, REDUCED_WIDTH, SOURCE_HEIGHT, SOURCE_WIDTH,
    TILES_HEIGHT, TILES_WIDTH, preprocess_r16_uint,
)

RUNNER = os.environ.get("KINECT2_VULKAN_RUNNER")
SHADER = os.environ.get("KINECT2_VULKAN_SHADER")


def make_image(points=(), fill=0):
    data = bytearray(SOURCE_WIDTH * SOURCE_HEIGHT * 2)
    if fill:
        data[:] = struct.pack("<H", fill) * (SOURCE_WIDTH * SOURCE_HEIGHT)
    for x, y, value in points:
        struct.pack_into("<H", data, 2 * (y * SOURCE_WIDTH + x), value)
    return bytes(data)


def expected_tile_masks(reference):
    """A separate tile-level view of the CPU reference's reduced mask."""
    result = bytearray(MAX_TILES)
    for tile_y in range(TILES_HEIGHT):
        for tile_x in range(TILES_WIDTH):
            i = (2 * tile_y) * REDUCED_WIDTH + 2 * tile_x
            result[tile_y * TILES_WIDTH + tile_x] = (
                reference.reduced_mask[i]
                | reference.reduced_mask[i + 1]
                | reference.reduced_mask[i + REDUCED_WIDTH]
                | reference.reduced_mask[i + REDUCED_WIDTH + 1]
            )
    return bytes(result)


def list_from_tile_masks(tile_masks):
    """Preserve observed X-first traversal with row-major numeric tile IDs."""
    return tuple(
        y * TILES_WIDTH + x
        for x in range(TILES_WIDTH)
        for y in range(TILES_HEIGHT)
        if tile_masks[y * TILES_WIDTH + x]
    )


@unittest.skipUnless(RUNNER and SHADER, "Vulkan runner/shader not configured")
class TestVulkanTileMasks(unittest.TestCase):
    def run_and_compare(self, source):
        reference = preprocess_r16_uint(source)
        expected = expected_tile_masks(reference)
        with tempfile.TemporaryDirectory(prefix="kinect2-vulkan-test-") as work:
            work = Path(work)
            source_path = work / "input.r16"
            masks_path = work / "output.bin"
            source_path.write_bytes(source)
            command = [RUNNER, SHADER, str(source_path), str(masks_path)]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(
                proc.returncode, 0,
                f"Vulkan runner failed ({proc.returncode}):\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}",
            )
            actual = masks_path.read_bytes()
        self.assertEqual(len(actual), MAX_TILES)
        self.assertEqual(actual, expected)
        self.assertEqual(list_from_tile_masks(actual), reference.worklist)

    def test_empty(self):
        self.run_and_compare(make_image())

    def test_full(self):
        self.run_and_compare(make_image(fill=0x8007))

    def test_low_three_bits_and_or(self):
        self.run_and_compare(make_image([
            (0, 0, 1), (2, 0, 2), (0, 2, 4),
            (8, 0, 0x8000), (16, 0, 0x8005), (24, 0, 0xFFFF),
        ]))

    def test_last_pixel_and_odd_coordinates(self):
        self.run_and_compare(make_image([
            (510, 422, 7), (511, 423, 7), (1, 0, 7), (0, 1, 7),
        ]))

    def test_nontrivial_worklist_order(self):
        self.run_and_compare(make_image([
            (0, 0, 1), (0, 8, 3), (8, 0, 4),
            (504, 416, 2), (510, 422, 1),
        ]))

    def test_seeded_sparse_random(self):
        rng = random.Random(0xC0FFEE)
        points = [
            (rng.randrange(SOURCE_WIDTH),
             rng.randrange(SOURCE_HEIGHT),
             rng.randrange(65536))
            for _ in range(3000)
        ]
        self.run_and_compare(make_image(points))


if __name__ == "__main__":
    unittest.main()
