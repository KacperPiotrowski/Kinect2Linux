"""Offline tests for warmed RGB throughput diagnostics (no physical Kinect)."""
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "benchmark_capture.py"
spec = importlib.util.spec_from_file_location("capture_benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)


def snapshot(rgb, ir, depth, gaps=(0, 0, 0)):
    return {
        "frame_counts": {"rgb": rgb, "ir": ir, "depth": depth},
        "sequence_gaps": dict(zip(("rgb", "ir", "depth"), gaps)),
        "streaming": True,
        "selected": {"rgb": True, "ir_depth": True},
    }


class CaptureBenchmarkTests(unittest.TestCase):
    def test_rate_uses_warmed_counter_deltas(self):
        before = snapshot(100, 50, 50, (10, 2, 2))
        after = snapshot(310, 325, 325, (14, 2, 2))
        result = benchmark.compute_result("combined", before, after, 10, 3, 20)
        self.assertEqual(result["rgb_frames"], 210)
        self.assertEqual(result["rgb_fps"], 21)
        self.assertEqual(result["ir_fps"], 27.5)
        self.assertEqual(result["depth_fps"], 27.5)
        self.assertEqual(result["rgb_gaps"], 4)
        self.assertEqual(result["cpu_percent"], 170)

    def test_no_cpu_metrics_without_proc_access(self):
        result = benchmark.compute_result("rgb", snapshot(0, 0, 0),
                                          snapshot(30, 0, 0), 2, None, None)
        self.assertIsNone(result["cpu_percent"])
        self.assertEqual(result["rgb_fps"], 15)
        self.assertEqual(result["ir_fps"], 0)

    def test_refuses_missing_or_reset_counters(self):
        before = snapshot(100, 0, 0)
        with self.assertRaisesRegex(ValueError, "invalid/reset"):
            benchmark.compute_result("x", before, snapshot(50, 0, 0),
                                     5, None, None)
        after = snapshot(120, 1, 1)
        del after["sequence_gaps"]
        with self.assertRaisesRegex(ValueError, "lacks sequence_gaps"):
            benchmark.compute_result("x", before, after, 5, None, None)
        with self.assertRaisesRegex(ValueError, "positive"):
            benchmark.compute_result("x", before, before, 0, None, None)

    def test_rejects_reconfigured_or_stopped_streams(self):
        correct = snapshot(10, 0, 0)
        correct["selected"] = {"rgb": True, "ir_depth": False}
        benchmark.check_capture_status(correct, {"rgb": True, "ir_depth": False})
        with self.assertRaisesRegex(RuntimeError, "selection"):
            benchmark.check_capture_status(correct, {"rgb": True, "ir_depth": True})
        correct["streaming"] = False
        with self.assertRaisesRegex(RuntimeError, "not reporting"):
            benchmark.check_capture_status(correct, {"rgb": True, "ir_depth": False})


if __name__ == "__main__":
    unittest.main()
