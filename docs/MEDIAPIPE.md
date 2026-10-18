# MediaPipe Face Landmarker — optional Kinect v2 RGB demo

**Status: experimental, separate Python process.** Initially prepared against
[MediaPipe 1.1.1](https://pypi.org/project/mediapipe/1.1.1/) (14 October 2026).
The API is documented, but **this integration has not yet been exercised
with the physical Kinect or an actual installed MediaPipe 1.1.1 runtime**.
Neither a published PyPI wheel nor passing mocked tests guarantees the
previous compatibility issue is fixed on this particular Arch Linux system.

This demo detects the **presence of a face, its landmarks and (internally)
expression blendshapes**. It does **not** determine someone's identity,
authenticate the user, prevent presentation attacks, or use Kinect Depth/IR.
It saves **no photographs, face templates or detections** and performs no
network uploads of camera frames. MediaPipe may separately send usage metrics;
see its [privacy notice](https://github.com/google-ai-edge/mediapipe#privacy-notice).
Only point a camera at people who agree to its use.

## Architecture and safety

```text
Kinect v2 USB -> single existing C++ broker -> RGB memfd / FrameClient
                                              -> optional Python Face Landmarker
                                              -> terminal / optional local GUI
```

- No new USB owner, no access to `/dev/video11`, no changes to kernel driver,
  V4L2, ALSA, Howdy/PAM or the always-on systemd service.
- Opt-in, out-of-process consumer of `FrameClient("rgb")`: closing the window
  or Ctrl+C closes **only its subscription**; other viewers continue.
- `receive_latest()` drops backlogged packets *for this client*; slow model
  inference cannot block the broker or other subscribers.
- Native Kinect RGB arrives as **1920×1080 BGRX**, four bytes per pixel. The
  client copies to MediaPipe **SRGB**, by default sampling every third pixel
  (640×360). MediaPipe does not receive raw RGB while that memfd is mapped.
- Model file is provided by the user and remains ignored by Git.
- MediaPipe `VIDEO` timestamps derive from broker host monotonic timestamps
  and are made strictly increasing. These are **not calibrated sensor timestamps**.
- No identity recognition, face enrollment, remote video transfer or automatic
  PAM/SDDM/sudo login. Do not use for security decisions.

## Setup — on Arch Linux in your persistent project checkout

Check out the **review branch** first; do not replace the running broker:

```bash
git fetch origin
git switch --track origin/feat/mediapipe-face-landmarker-broker
# If already on that branch: git pull --ff-only
```

Install the optional dependency **in its own virtual environment**, not the
system-wide Arch Python:

```bash
python3 -m venv .venv-mediapipe
. .venv-mediapipe/bin/activate
python -m pip install -r requirements-mediapipe.txt
```

Download the model from the official
[Face Landmarker model documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
to `models/face_landmarker.task`:

```bash
mkdir -p models
curl -fL --retry 3 -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

Review the model's license and provenance before redistributing; do not commit
the `.task` to this repo. Confirm the optional package and model are present
**without accessing Kinect**:

```bash
python tools/mediapipe_face_live.py --check
```

With the **existing broker already active** in automatic subscriber mode
(`kinect2-broker.service`, `--auto-streams --frame-preview`), use the
one-command smoke test:

```bash
python tools/mediapipe_face_live.py --max-frames 90
```

It prints `faces=N landmarks=M` every ten processed frames. Looking toward
the RGB lens in reasonable lighting should produce `faces=1` with many
landmarks; `faces=0` is an ordinary nondetection, not proof of a broken camera.

For an optional live window with points (requires a functional OpenCV GUI
HighGUI in that venv and an active KDE graphical session):

```bash
python tools/mediapipe_face_live.py --preview --max-frames 0
```

Press **Q**, **Escape** or close the window to exit. `--scale 1` feeds native
1920×1080 into the inference pipeline (more expensive); default `--scale 3`
lowers processing cost. The demo intentionally analyzes one face at a time.

If the broker isn't running, or is in manual mode without active RGB
capture, this demo cannot open the sensor itself. In automatic mode the
subscription activates RGB on demand. Never start a second Kinect capture
process or delete the broker's socket/USB lock to work around a failure.

## Acceptance before merge

- [ ] A real install of `mediapipe==1.1.1` and `--check` succeeds on Arch.
- [ ] Face detected on a real Kinect RGB frame, no unintended BGR/RGB swap.
- [ ] GUI close (X/Q/Esc) releases the subscriber and doesn't recreate window.
- [ ] Concurrent Firefox V4L2 and other `FrameClient` subscribers continue.
- [ ] Post-close broker can become idle and release USB as before.
- [ ] RAM/CPU and frame backlog sampled; no claims of fixed FPS until measured.
- [ ] Offline CI unit tests pass (no MediaPipe installation or USB required).

The existing saved-IR experiment `tools/mediapipe_ir_probe.py` remains
separate and **not** promoted to a supported feature.

**Rollback:** Ctrl+C/close the preview, `deactivate` the venv, and
`git switch main` if desired. No systemd changes or package removal needed.
