# Broker-owned RGB webcam (experimental, PR #20)

Goal: **one C++ broker process and one Kinect v2 USB owner**. Firefox / OBS
consume `/dev/video11` through an in-process, optional V4L2 RGB output;
independent Python RGB / IR / Depth `FrameClient` subscribers use the same
already decoded frames. No standalone RGB service may hold the video writer
at the same time.

**Hardware smoke-tested on one physical Kinect v2 on Arch Linux/KDE (2026-10-18),
including Firefox + four SDK clients, idle USB release and reboot/login.**
This does not establish cross-distribution compatibility, sustained stability,
or a finished version 1.0 installer; complete remaining acceptance checks
before merging or retiring the standalone RGB service.

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


## Hardware observations (2026-10-18; maintainer report)

- A single Firefox reader caused `streaming_clients=1`, `sensor_open=true`, `selected.rgb=true`, `selected.ir_depth=false`; no SDK subscribers.
- All five live previews worked at once: Firefox plus two independent SDK RGB and two SDK IR viewers. `frame_preview.subscribers=4` while `v4l2_rgb.streaming_clients=1` and both hardware stream groups were selected.
- Removing both IR viewers automatically disabled the IR/Depth group without disrupting RGB. Removing both SDK RGB viewers left the browser video live.
- Closing the last browser reader resulted in `sensor_open=false`, `streaming=false`, both subscriber counts zero and a running broker service. Firefox recovered live image upon reopening.
- After reboot/login, user broker automatically started; the legacy RGB writer was inactive, `/dev/video11` existed under the right name, V4L2 reported ready and the USB sensor remained closed at idle. Firefox and four SDK viewers worked after reboot.
- Observed V4L2 `dropped=0`, `last_error=""` in sampled statuses. One transient `DepthPacketStreamParser: 7 packets were lost` warning appeared immediately after RGB-to-RGB+IR/Depth stream reconfiguration. In a later 20-second five-client steady-state run, RGB advanced by 300 frames, IR by 600, Depth by 600; sequence-gap counters increased by **zero** for all three streams.

**Additional 2026-10-18 acceptance results:** With Firefox and 2 RGB + 2 IR SDK windows active, a snapshot of broker process PID 2458 showed RSS=157724 KiB (~154 MiB) and `ps %CPU=14.8`; note that `ps %CPU` is an average since process start (15m44s elapsed), **not** instantaneous load under five clients. Over the next 20 seconds, frame advances were RGB 300 (~15 fps), IR 600 (~30 fps), Depth 600 (~30 fps), all with **0 new sequence gaps**. An additional Depth SDK process subscribed (SDK count rose from four to five), was deliberately killed, and disappeared from subscriptions (back to four), while Firefox still reported one reader and USB remained open; existing video viewers were reported running. V4L2 `dropped=0`, `last_error=""` throughout sampled status.

**Still not verified:** direct privacy-black behavior on a stalled sensor with a browser reader, multi-minute/hours stress and leak trends, instant peak CPU under load, independent manual-mode regression and multi-distribution install. Do not present these checks as passed.

### Optional targeted acceptance checks before merge

While Firefox and the four demo windows are active, inspect the broker process without restarting it:

```bash
pid=$(systemctl --user show -p MainPID --value kinect2-broker.service)
ps -p "$pid" -o pid,etime,%cpu,rss,cmd
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient
s = BrokerClient().get_status()
for key in ("frame_counts", "sequence_gaps", "v4l2_rgb", "frame_preview"):
    print(key, s[key])
PY
```

Capture another status after at least 30 seconds of stable streaming to
distinguish one-time reconfiguration warnings from sustained packet loss.
To test a client crash, terminate **only a separately launched test
FrameClient child process**, never the broker service or Firefox. Ensure its
subscriber count returns to baseline within a few seconds and the other
viewers continue.

The existing standalone bridge remains installed as a rollback option. A
successful test on one computer is not a guarantee of general plug-and-play.
