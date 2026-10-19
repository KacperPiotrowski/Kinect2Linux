"""CPU-only offline tests: no AI models, cameras, USB or dependencies."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk/python"))
from kinect2_linux import tracking as t  # noqa: E402


class FakeBackend:
    def __init__(self, record, task="body"):
        self.record = record
        self.task = task

    def process(self, frame):
        self.record.append(("process", frame))
        return t.TrackingResult(self.task, ())

    def close(self):
        self.record.append(("close", None))


class TrackingTests(TestCase):
    def setUp(self):
        self.events = []
        self.basic_backend = FakeBackend(self.events)
        self.accurate_backend = FakeBackend(self.events)
        basic_module = mock.Mock()
        accurate_module = mock.Mock()

        def basic_factory():
            self.events.append(("load", "light"))
            return self.basic_backend

        def accurate_factory():
            self.events.append(("load", "accurate"))
            return self.accurate_backend

        basic_module.create_tracker = basic_factory
        accurate_module.create_tracker = accurate_factory
        self.specs = {
            "light": t._ModelSpec("body", "test.light"),
            "accurate": t._ModelSpec("body", "test.accurate"),
            "hand": t._ModelSpec("hands", "test.hand"),
        }
        self.imports = mock.patch.object(
            t.importlib, "import_module",
            side_effect=lambda path: self._import(path, basic_module, accurate_module),
        )
        self.models = mock.patch.dict(t._BUILTIN_MODELS, self.specs, clear=True)
        self.defaults = mock.patch.dict(t._DEFAULT_MODELS, {
            ("body", "basic"): "light",
            ("body", "advanced"): "accurate",
        }, clear=True)
        for patcher in (self.imports, self.models, self.defaults):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _import(self, name, basic, accurate):
        self.events.append(("import", name))
        return {"test.light": basic, "test.accurate": accurate}[name]

    def test_off_never_imports_models_or_allocates_backend(self):
        session = t.TrackingSession("body")
        self.assertIsNone(session.process(object()))
        self.assertFalse(session.loaded)
        session.close()
        self.assertEqual(self.events, [])

    def test_lazy_basic_one_import_reused(self):
        session = t.TrackingSession("body", "basic")
        self.assertEqual(self.events, [])
        self.assertFalse(session.loaded)
        self.assertEqual(session.process("frame1").task, "body")
        self.assertEqual(session.process("frame2").task, "body")
        self.assertEqual(self.events, [
            ("import", "test.light"), ("load", "light"),
            ("process", "frame1"), ("process", "frame2"),
        ])
        session.close()
        self.assertEqual(self.events[-1], ("close", None))

    def test_switching_to_off_releases_without_next_import(self):
        session = t.TrackingSession("body", "basic")
        session.process("frame")
        session.configure("off")
        self.assertFalse(session.loaded)
        self.assertIsNone(session.process("ignored"))
        self.assertEqual(self.events[-1], ("close", None))
        self.assertEqual(len([e for e in self.events if e[0] == "import"]), 1)

    def test_switch_to_advanced_only_loads_when_used(self):
        session = t.TrackingSession("body", "basic")
        session.process("first")
        session.configure("advanced")
        self.assertEqual(self.events[-1], ("close", None))
        self.assertFalse(session.loaded)
        session.process("second")
        self.assertIn(("import", "test.accurate"), self.events)
        self.assertEqual(len([e for e in self.events if e[0] == "import"]), 2)
        session.close()

    def test_explicit_advanced_model_choice(self):
        session = t.TrackingSession("body", "advanced", model_id="light")
        self.assertEqual(self.events, [])
        session.process("a")
        self.assertIn(("import", "test.light"), self.events)
        session.close()

    def test_unreviewed_model_rejected_without_destroying_running_one(self):
        session = t.TrackingSession("body", "basic")
        session.process("first")
        with self.assertRaises(ValueError):
            session.configure("advanced", model_id="downloaded-from-anywhere")
        self.assertTrue(session.loaded)
        self.assertEqual(session.mode, "basic")
        self.assertNotIn(("close", None), self.events)
        session.close()

    def test_basic_rejects_model_picker_and_wrong_task(self):
        with self.assertRaises(ValueError):
            t.TrackingSession("body", "basic", model_id="accurate")
        with self.assertRaises(ValueError):
            t.TrackingSession("hands", "advanced", model_id="light")
        self.assertEqual(self.events, [])

    def test_known_models_list_never_imports(self):
        self.assertEqual(t.available_models("body"), ("accurate", "light"))
        self.assertEqual(t.available_models("hands"), ("hand",))
        self.assertEqual(self.events, [])

    def test_no_installed_default_fails_only_when_used(self):
        with mock.patch.dict(t._DEFAULT_MODELS, {}, clear=True):
            session = t.TrackingSession("body", "basic")
            self.assertFalse(session.loaded)
            with self.assertRaisesRegex(t.TrackingUnavailable, "No reviewed"):
                session.process("frame")
            self.assertEqual(self.events, [])
            session.close()

    def test_close_is_idempotent_and_prevents_reopening(self):
        session = t.TrackingSession("body", "basic")
        session.process("frame")
        session.close()
        session.close()
        self.assertEqual(self.events.count(("close", None)), 1)
        with self.assertRaises(RuntimeError):
            session.process("more")
        with self.assertRaises(RuntimeError):
            session.configure("off")

    def test_failed_import_can_be_retried_and_does_not_affect_broker(self):
        with mock.patch.object(t.importlib, "import_module", side_effect=ImportError("missing")):
            session = t.TrackingSession("body", "basic")
            with self.assertRaises(t.TrackingUnavailable):
                session.process("frame")
            self.assertFalse(session.loaded)
        self.assertEqual(self.events, [])
        session.close()

    def test_incorrect_adapter_output_is_rejected(self):
        backend = FakeBackend(self.events, task="face")
        with mock.patch.object(t.importlib, "import_module") as module:
            module.return_value.create_tracker.return_value = backend
            session = t.TrackingSession("body", "basic")
            with self.assertRaisesRegex(TypeError, "matching TrackingResult"):
                session.process("frame")
            session.close()
