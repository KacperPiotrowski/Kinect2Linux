# Broker-owned RGB webcam (experimental, PR #20)

Goal: **one C++ broker process and one Kinect v2 USB owner**. Firefox / OBS
consume `/dev/video11` through an in-process, optional V4L2 RGB output;
independent Python RGB / IR / Depth `FrameClient` subscribers use the same
already decoded frames. No standalone RGB service may hold the video writer
at the same time.

**Not yet verified on physical hardware**. Run the test below before
retiring the standalone RGB service. This is *not* the final 1.0 installer.

## Internals

- `--v4l2-rgb` enables an in-process `V4l2RgbOutput` (requires
  `--auto-streams --allow-device-control --frame-preview` and a hardware
  broker build). Without the flag the previously tested broker remains
  unchanged.
- The existing `/dev/video11` device is used **only** when its sysfs name
  matches `Kinect v2 RGB`. The output uses 1920×1080 YUYV422 with BT.601
  limited-range conversion from native BGRX. No `/dev/video10`, new V4L2
  device or additional USB handle.
- On-demand `v4l2loopback` client usage events trigger the **same**
  `AutoCapture` reconciliation as Python frame subscribers. V4L2 readers
  show separately under `get_status()["v4l2_rgb"]`, while
  `frame_preview.subscribers` still counts only SDK frame sockets.
- A dedicated worker converts and writes frames to V4L2. It uses exactly
  two preallocated native RGB buffers and a bounded latest-frame slot.
  It may drop its own stale frames; it does **not block the USB decoder**
  with colorspace conversion or V4L2 output writes.
- A black standby frame replaces stale webcam output when no browser
  is subscribed, and after a pause of more than 2 seconds without RGB.
  Device/write errors are visible in `v4l2_rgb.last_error`. Native SDK
  subscribers can continue even when V4L2 stops.
- `/dev/video11` still requires the existing `v4l2loopback` kernel
  module created at system startup. This *does not* mean a second
  Kinect image-capture service or physical USB owner.

## Safe physical test on the maintainer's Arch Linux

**Do not run this while the original RGB bridge is producing webcam frames.**
Close Firefox camera tab, OBS or other V4L2 readers first. Stop only the
legacy RGB *user* service (this is reversible):

```bash
systemctl --user stop kinect2-rgb-webcam.service
```

This leaves `kinect2-rgb-device.service` and the v4l2loopback kernel
device untouched. Stop any manual broker before restarting the user broker.

```bash
git fetch origin
git switch feat/broker-integrated-v4l2
git pull --ff-only
bash tools/build_broker.sh --with-hardware
./bin/test_v4l2_rgb
```

Run **one** experimental service with opt-in V4L2. Add a systemd user
drop-in manually (review existing drop-ins first; avoid overriding one):

```bash
mkdir -p ~/.config/systemd/user/kinect2-broker.service.d
cat > ~/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf <<'EOF'
[Service]
Environment=KINECT2_BROKER_V4L2=1
EOF
systemctl --user daemon-reload
systemctl --user restart kinect2-broker.service
systemctl --user is-active kinect2-broker.service
journalctl --user -u kinect2-broker.service -n 25 --no-pager
```

Expected service: `active` with `v4l2_rgb.enabled=true`,
`v4l2_rgb.ready=true`, `v4l2_rgb.streaming_clients=0`,
`sensor_open=false` until a browser or SDK client needs a stream.
If the broker fails to start, check whether the old standalone RGB writer
is still active; never delete USB lock or socket files to "fix" a conflict.

Now test in the following order:

1. Open Firefox camera test tab and choose `Kinect v2 RGB`.
   `v4l2_rgb.streaming_clients` should rise, and broker opens USB for RGB.
2. **While Firefox remains open**, start
   `python3 tools/demo_four_clients.py` (2 RGB + 2 IR).
   Check that all 5 consumers have moving video simultaneously.
3. Check SDK counters and `v4l2_rgb.frames`, `v4l2_rgb.dropped`,
   `frame_preview.subscribers`, `selected` and `sensor_open`.
   Ensure one broker process and no `device_busy` from a second owner.
4. Close both IR windows; RGB and Firefox must continue (a brief hardware
   blink/restart is possible). Close SDK RGB windows; browser keeps RGB alive.
5. Close browser permission/stream and all SDK apps; allow a few seconds.
   Expect `sensor_open=false`, `streaming=false`, both client counts zero,
   and `systemctl --user is-active kinect2-broker.service` = `active`.
6. Check Firefox again after everything is idle to confirm RGB resumes
   without stopping or restarting broker.

Status check:

```bash
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient
s = BrokerClient().get_status()
for key in ("v4l2_rgb", "frame_preview", "sensor_open",
            "streaming", "selected", "frame_counts", "sequence_gaps"):
    print(key, s[key])
PY
```

**Actual FPS in dim light may be 15 RGB / 30 IR+Depth**, as already
measured on this Kinect v2; do not mistake lighting-driven exposure for
a transport regression. The webcam worker's output FPS may be lower
than broker native frame counts if conversion cannot keep up.

## Rollback — no reinstall, no reboot

Close the Firefox camera and SDK previews. Disable only the experimental
drop-in, reload and restart broker, then start the existing RGB bridge:

```bash
mv ~/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf \
   ~/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf.disabled
systemctl --user daemon-reload
systemctl --user restart kinect2-broker.service
systemctl --user start kinect2-rgb-webcam.service
```

The old webcam remains on its original path and works on demand.
Until all the above hardware checks pass, **do not enable/disable or
remove the legacy service automatically**, and do not merge this PR.
Unrelated audio, Howdy, V4L2 IR and `/dev/video10` are unchanged.
