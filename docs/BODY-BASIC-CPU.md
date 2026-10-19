# Experimental Basic Body Tracking on CPU — RTMPose-s + YOLOX-tiny

This is a **separate, optional, stacked experiment** based on the OFF/lazy API
in PR #28. It does not replace/modify the operating C++ broker, V4L2 webcam
or microphone. No MediaPipe, custom inference engine, graphics card or Kinect
USB owner is added.

**Expected first milestone:** Kinect live RGB with a responsive green 2D
COCO skeleton (17 joints) and measured inference FPS. NOT 3D skeleton, not
Microsoft's proprietary SDK 2.0 algorithm and not yet a supported Basic default.
Measured results on the maintainer's CPU will decide whether the model is
usable before merging.

## 0. Read-only setup status

```bash
cd ~/Projekty/kinect/Kinect2Linux-body-test
python3 tools/prepare_rtmpose_body.py
```

Do not run any `basic activate`, stop brokers or switch your active checkout.
The preview is an independent RGB subscriber through `FrameClient`.

## 1. Optional dependencies in a standalone environment

```bash
python3 -m venv .venv-body-cpu
. .venv-body-cpu/bin/activate
python -m pip install 'rtmlib==0.0.16' 'onnxruntime==1.31.0'
```

`rtmlib` (Apache-2.0) supplies the existing CPU pose/detector runtime;
`onnxruntime` supports 3.14 x86_64. These packages are not Kinect2Linux
core requirements. Do not install them with `sudo` or in system Python.

## 2. Explicit model provisioning (network opt-in)

Review the official upstream model URLs in
`tools/prepare_rtmpose_body.py`, then run:

```bash
python3 tools/prepare_rtmpose_body.py --download
```

This step downloads exactly two official OpenMMLab ONNX model archives into
private temp space, copies only the ONNX entries into `models/`, and does NOT
start tracking. Source archive provenance/checksum/licensing still need final
audit before distribution. The weights must never be committed to Git.
Downloading is **explicit** and happens before the first preview.
Normal tracking will not download anything.

YOLOX-tiny 416x416 provides person detection, RTMPose-s 256x192 predicts
17 body keypoints. These are 2D RGB points, NOT Kinect Depth millimetres.

## 3. Run live Kinect 2D skeleton test

With the existing broker active as before:

```bash
PYTHONPATH=sdk/python python3 tools/demo_basic_body_cpu.py --max-frames 90
```

Optional headless benchmark:

```bash
PYTHONPATH=sdk/python python3 tools/demo_basic_body_cpu.py --max-frames 90 --no-preview
```

Q, Escape or closing the GUI window ends the client. Existing Firefox V4L2
readers, IR/Depth consumers and audio remain unaffected. Client uses the
broker's newest RGB frames and can skip stale packets rather than cause
unbounded queueing. Report median/worst inference time and FPS; initial
model load is included in the first timing and may be slow.

## Tests without Kinect or optional inference runtime

```bash
PYTHONPATH=sdk/python python3 -m unittest discover -s tests -p 'test_rtmpose_body_adapter.py' -v
```

## Limitations

- No automatic Body Tracking Basic activation for all users; it remains
  experimental until measured on physical CPU and verified across installs.
- No skeletal 3D joints. Depth may be added after RGB/Depth registration.
- No guaranteed FPS; user-facing performance labels await measurements.
- No identity, biometrics, PAM/Howdy configuration.
- Currently manual explicit model download and separate venv.
- Turning tracking OFF still imports no models or third-party AI modules.
- No custom engine/plugins. Advanced models can be evaluated separately.
