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

## Body preview after first on-hardware test

The first live inference detected 1 person and completed 10 frames. Reported
overall 3.56 inferred FPS, median inference 70.3 ms, max 171.2 ms. That is
**not** evidence that CPU inference itself is 3.56 FPS; measure broker frame
waiting separately from BGR resizing, warm inference and GUI drawing before
making performance changes.

- The old torso outline connected shoulders and hips as a square. This preview
  now uses shoulder and hip bars with an **illustrative center spine**.
- Off-screen or low-confidence joints are not joined to other joints. This
  does **not** increase the actual model accuracy or reconstruct missing legs.
- **To display full legs, they must fit the RGB field of view.** Stand far
  enough back that both feet remain visible; the preview preserves 16:9 aspect
  ratio and does not crop the physical image.
- Face landmarks here mean COCO nose/eyes/ears, not face identification.
- CPU percentages need context (one process core vs overall CPU usage).
  The benchmark now reports separate median RGB wait, BGR resize, warm inference
  and GUI times. That is diagnostic instrumentation, not a claimed speedup.

## CPU multithreading A/B experiment (Oct 2026)

The 900-frame GUI trial on Ryzen 9 7900 reported 11.37 inferred FPS,
64.4 ms median inference, 267 MiB process RSS and **2219% process CPU**.
A `taskset -c 0-7` test still reported ~2159% CPU, 70 process threads, and
explicit CPU affinity masks for multiple threads outside 0-7. This confirmed
that simply setting process-level affinity was **not effective** in this case.

RTMLib 0.0.16 does not expose `onnxruntime.SessionOptions` through `Body`.
The maintainer confirmed by live GUI that **4 intra-op threads and disabled
idle spinning** preserve the desired tracking behavior on Ryzen 9 7900. A
`btop` snapshot during that run showed **8% system-wide CPU** and about
**183% CPU for the Python process**, vs earlier ~98% system-wide and
~2200% Python CPU. These are different sample moments, not a controlled
FPS equivalence benchmark, but the measured CPU reduction is substantial.
The Python process remained around **270 MiB RSS**.

Therefore this experimental Basic profile now **defaults to 4 CPU threads
and no spinning**. The adapter uses RTMLib's unchanged YOLOX/RTMPose
preprocessing and postprocessing. It first creates both upstream sessions,
then rebuilds them with bounded `SessionOptions.intra_op_num_threads` and
spinning disabled. This double session creation costs extra startup time:
compare **warmed inference** and steady-state CPU, not first-frame latency.
There is no need to type any tuning flags for everyday Basic use.

Setting `--ort-threads 0 --ort-spin` recreates the previous untuned RTMLib
behavior **only for an explicit benchmark**. The default configuration for
direct `TrackingSession("body", mode="basic")` use is also bounded unless
the application overrides `KINECT2_BODY_ORT_THREADS` and
`KINECT2_BODY_ORT_NO_SPIN` explicitly.

```bash
# Everyday Basic: the hardware-tested settings are already the default.
python tools/demo_basic_body_cpu.py --max-frames 300

# Optional A/B tests, only if you deliberately want to compare variants:
python tools/demo_basic_body_cpu.py --max-frames 300 --ort-threads 8 --ort-no-spin
python tools/demo_basic_body_cpu.py --max-frames 300 --ort-threads 0 --ort-spin
```

No `taskset` is needed for these trials; the explicit ORT thread count itself
disables ORT's default automatic thread affinities. Both sessions are limited,
not only the process main thread. This does **not** constrain OpenCV or BLAS
threading separately, and system CPU can still be influenced by other
applications. Watch process `%CPU`, RSS, OS-level CPU, `inferred_fps`,
`warm_median_inference_ms` and `average_process_cpu_percent_of_one_core`.
Treat the results as an **A/B measurement**, not an already-proven speedup.

For consistent results, repeat the same duration for baseline and tuned runs.
Original behavior is recovered only with **both** `--ort-threads 0`
and `--ort-spin`. No broker restarts or system-wide settings needed.
The ONNX models themselves remain unchanged; no claim is made of improved
accuracy or of a measured end-to-end FPS gain.
