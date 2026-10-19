# Tracking models: Basic, Advanced, OFF (first infrastructure slice)

**One interface, zero required AI dependencies.** Tracking is always optional
and never runs inside the physical Kinect USB broker. The SDK's RGB/IR/Depth
frames and audio still work if every tracking module is disabled or a model
fails to load.

## Product decisions

- **Basic:** no model-picker UI. A single validated **lightweight CPU-friendly**
  model per capability (body, hands, face) should just work. The intended
  experience resembles the immediate, responsive skeleton viewer from Kinect
  SDK 2.0 for Windows, **not** a port or redistribution of its proprietary
  tracking implementation.
- **Advanced:** explicitly select a reviewed higher-accuracy built-in model
  where one exists. More accurate is not necessarily faster on CPU.
- **OFF:** no AI imports, inference, model allocation or subprocess.
- **Lazy:** configuration alone must never load a model. First frame for an
  enabled task triggers creation of that task's selected model. Switching to
  another model releases the old one; the replacement loads on first use.
- **No homegrown inference engine, arbitrary plugins or model importer.**
  Adapters will use external, separately licensed model runtimes. Each
  candidate/weight requires provenance, license and CPU benchmark review.

## First PR: interface only — do not mistake it for working skeleton tracking

`sdk/python/kinect2_linux/tracking.py` provides `TrackingSession`,
`TrackingResult`, `TrackedSubject`, `Keypoint`, `available_models`,
and a private allowlist for built-in reviewed adapters. **No model is installed
or registered yet.** OFF works today. Basic/Advanced do not perform inference
until separate model-adapter PRs land; an attempted enabled `process()` fails
clearly with `TrackingUnavailable`. No fallback silently downloads anything.

```python
from kinect2_linux.tracking import TrackingSession

with TrackingSession("body", mode="off") as tracker:
    assert tracker.process(None) is None  # no model import, no sensor opened
```

This code does not touch USB, systemd, V4L2, PipeWire or PAM. The adapter
input is an already acquired frame from a broker consumer, not a command to
open the physical Kinect. When models are added, adapters must return a shared
`TrackingResult` with keypoints in normalized image coordinates. Physical
`depth_mm` must be populated **only** using a calibrated, synchronized depth
measurement; model-inferred relative depth must not be labeled millimetres.

## Acceptance gates for the next, separate adapter PR

1. Body tracking first: test one light CPU model, measured on the maintainer's
   Arch Linux Kinect v2, while V4L2 and the broker stay unaffected.
2. Verify FPS, median and tail latency, CPU/RAM, correct left/right anatomy,
   occlusions and skeleton stability; compare with actual samples, not
   unsubstantiated ratings such as P=1.2.
3. Only after Basic is usable: optional accurate Advanced model selection.
   Hands and face adapters follow independently.
4. Keep alternate profiles and OFF available, with no up-front imports of
   every model. No mandatory MediaPipe dependency and no auto-download.

The Basic / Advanced CLI work in PR #27 is separate; this API does not change
its command-line behavior or the existing working camera/microphone paths.
