"""Hardware-free tests for producer/consumer behavior."""
import pathlib
import sys
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'face'))
from preview import LatestFrame
import numpy as np


class LatestFrameTests(unittest.TestCase):
    def test_latest_replaces_stale_frames_and_is_copied(self):
        slot = LatestFrame()
        image = np.full((3, 4, 3), 15, np.uint8)
        slot.publish(image)
        image[:] = 99
        number, _, first = slot.get()
        self.assertEqual(number, 1)
        self.assertEqual(int(first[0,0,0]), 15)
        for i in range(2, 101):
            slot.publish(np.full((3,4,3), i, np.uint8))
        number, _, latest = slot.get(last_number=1)
        self.assertEqual(number, 100)
        self.assertEqual(int(latest[0,0,0]), 100)

    def test_slow_analyzer_does_not_block_capture(self):
        slot = LatestFrame()
        consumed = []
        start = time.monotonic()
        def slow_analysis():
            last = -1
            while time.monotonic()-start < 0.43:
                packet = slot.get(last, wait=0.04)
                if packet:
                    last = packet[0]
                    consumed.append(last)
                    time.sleep(0.09)
        consumer = threading.Thread(target=slow_analysis)
        consumer.start()
        for n in range(20):
            slot.publish(np.full((4,4,3), n, np.uint8))
            time.sleep(0.02)
        consumer.join(timeout=2)
        self.assertEqual(slot.number, 20)
        self.assertLess(len(consumed), slot.number)
        self.assertGreater(len(consumed), 1)
        self.assertGreaterEqual(max(consumed), 14)

if __name__ == '__main__':
    unittest.main()
