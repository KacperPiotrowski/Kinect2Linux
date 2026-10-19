"""Optional tracking facade: off by default, one API, lazy built-in models.

No model is bundled or loaded by this module. All inference backends are
separate consumers of Kinect2Linux frame streams, never Kinect USB owners.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Protocol

TASKS = frozenset(("body", "hands", "face"))
MODES = frozenset(("off", "basic", "advanced"))


class TrackingUnavailable(RuntimeError):
    """No reviewed model is available, or the chosen adapter failed to load."""


@dataclass(frozen=True)
class Keypoint:
    name: str
    x: float  # normalized image coordinate, 0..1
    y: float  # normalized image coordinate, 0..1
    confidence: float | None = None
    depth_mm: float | None = None  # real, calibrated depth only; never guessed 3D


@dataclass(frozen=True)
class TrackedSubject:
    kind: str  # person, hand, face
    keypoints: tuple[Keypoint, ...]
    identifier: int | None = None  # optional, local tracking ID, not identity


@dataclass(frozen=True)
class TrackingResult:
    task: str
    subjects: tuple[TrackedSubject, ...]
    timestamp_ns: int | None = None


class TrackingBackend(Protocol):
    """Adapter contract for a reviewed, external inference model."""

    def process(self, frame: object) -> TrackingResult: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class _ModelSpec:
    task: str
    module: str
    factory: str = "create_tracker"


# Populated ONLY when individually reviewed and tested built-in adapters land.
# No arbitrary Python module path or user-defined engine loading is supported.
_BUILTIN_MODELS: dict[str, _ModelSpec] = {
    # Optional external runtime and two manually provisioned ONNX weights.
    "rtmpose-body-light": _ModelSpec("body", "kinect2_linux.tracking_rtmpose_body"),
}
_DEFAULT_MODELS: dict[tuple[str, str], str] = {
    ("body", "basic"): "rtmpose-body-light",
}


def available_models(task: str) -> tuple[str, ...]:
    """List installed built-in model IDs without importing any AI package."""
    if task not in TASKS:
        raise ValueError(f"Unknown tracking task: {task}")
    return tuple(sorted(name for name, spec in _BUILTIN_MODELS.items()
                        if spec.task == task))


class TrackingSession:
    """A single lazy tracker for body, hands or face.

    'off' needs no dependencies and never invokes inference.
    'basic' uses a future validated lightweight built-in default.
    'advanced' can select a validated built-in model explicitly.

    The first process() call is the only place that imports/creates a model.
    Switching modes disposes the old model without preloading the next one.
    """

    def __init__(self, task: str, mode: str = "off", model_id: str | None = None):
        if task not in TASKS:
            raise ValueError(f"Unknown tracking task: {task}")
        self.task = task
        self.mode = "off"
        self.model_id: str | None = None
        self._backend: TrackingBackend | None = None
        self._loaded_model: str | None = None
        self._closed = False
        self.configure(mode, model_id=model_id)

    @property
    def loaded(self) -> bool:
        return self._backend is not None

    def configure(self, mode: str, *, model_id: str | None = None) -> None:
        if self._closed:
            raise RuntimeError("TrackingSession is closed.")
        if mode not in MODES:
            raise ValueError(f"Unknown tracking mode: {mode}")
        if mode != "advanced" and model_id is not None:
            raise ValueError("Explicit model selection is available only in Advanced.")
        if model_id is not None:
            spec = _BUILTIN_MODELS.get(model_id)
            if spec is None or spec.task != self.task:
                raise ValueError(f"Unknown built-in {self.task} model: {model_id}")
        if (mode, model_id) == (self.mode, self.model_id):
            return
        self._release()
        self.mode, self.model_id = mode, model_id

    def _resolve_model(self) -> tuple[str, _ModelSpec]:
        model = self.model_id or _DEFAULT_MODELS.get((self.task, self.mode))
        if model is None:
            raise TrackingUnavailable(
                f"No reviewed built-in {self.task} model for {self.mode} yet."
            )
        spec = _BUILTIN_MODELS.get(model)
        if spec is None or spec.task != self.task:
            raise TrackingUnavailable(f"Built-in model unavailable: {model}")
        return model, spec

    def process(self, frame: object) -> TrackingResult | None:
        if self._closed:
            raise RuntimeError("TrackingSession is closed.")
        if self.mode == "off":
            return None
        if self._backend is None:
            model, spec = self._resolve_model()
            try:
                factory = getattr(importlib.import_module(spec.module), spec.factory)
                backend = factory()
            except Exception as exc:
                raise TrackingUnavailable(f"Failed to load built-in model: {model}") from exc
            if not callable(getattr(backend, "process", None)) or not callable(
                getattr(backend, "close", None)
            ):
                close = getattr(backend, "close", None)
                if callable(close):
                    close()
                raise TrackingUnavailable(f"Invalid built-in model adapter: {model}")
            self._backend = backend
            self._loaded_model = model
        result = self._backend.process(frame)
        if not isinstance(result, TrackingResult) or result.task != self.task:
            raise TypeError("Tracking adapter must return a matching TrackingResult.")
        return result

    def _release(self) -> None:
        backend = self._backend
        self._backend = None
        self._loaded_model = None
        if backend is not None:
            backend.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._release()

    def __enter__(self) -> TrackingSession:
        if self._closed:
            raise RuntimeError("TrackingSession is closed.")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
