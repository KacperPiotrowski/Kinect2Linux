# Experimental single-user broker service (systemd --user)

The intended Kinect2-Linux 1.0 architecture has **ONE main image-capture
service**: `kinect2-broker.service`. It is the sole Kinect USB owner for
RGB / IR / Depth, and starts physical capture *only while clients subscribe*.
The service may be running after KDE login with **USB closed** and nearly
zero idle capture load. We do not need to open a terminal on every login.

> **Pre-release opt-in, not the final installer.** This feature is stacked on
> [PR #15](https://github.com/KacperPiotrowski/Kinect2Linux/pull/15);
> its `--auto-streams` hardware mode is not merged into `main` yet.
> The optional V4L2 module for Firefox / OBS **is not yet integrated**:
> [issue #16](https://github.com/KacperPiotrowski/Kinect2Linux/issues/16).
> Do not claim the system browser can share the Kinect with independent SDK
> clients today.

## What changes, and what stays unchanged?

- `kinect2-broker.service` runs a native hardware-enabled broker as
  **your normal user**, not root, with `--allow-device-control
  --frame-preview --auto-streams`.
- The broker socket is `$XDG_RUNTIME_DIR/kinect2-broker.sock`, frame
  socket `$XDG_RUNTIME_DIR/kinect2-frames.sock`, and cooperative USB lock
  `$XDG_RUNTIME_DIR/kinect2-sensor.lock`.
- An app connecting with `FrameClient("rgb")`, `FrameClient("ir")`, or
  `FrameClient("depth")` makes the broker open only the needed hardware
  streams. On the last disconnect it stops them, closes USB and releases
  the cooperative lock.
- The **existing standalone** `kinect2-rgb-webcam.service`, the
  `kinect2-rgb-device.service` boot-time v4l2loopback setup,
  `/dev/video10`, `/dev/video11`, PipeWire, audio ALSA, and webcam
  permissions are **not touched** by this installer.

The standalone RGB bridge and this broker use the same exclusive sensor
lock and **cannot both capture frames at the same time**. While no
`FrameClient` is subscribed, the broker uses no USB and the old RGB bridge
can serve Firefox. If Firefox already opened the Kinect, subscribed broker
clients will wait for `device_busy`; the broker never steals USB.

## One-time experimental setup (Arch Linux hardware-tested prerequisites)

Make sure the **physical** Kinect v2 works and has the required normal-user
USB permissions. Finish earlier libfreenect2 setup before installing:

```bash
bash tools/bootstrap_libfreenect2_omp.sh
bash tools/build_broker.sh --with-hardware

# Inspection first: prepares ~/.config/systemd/user/ but does NOT start:
bash tools/install_broker_user.sh

# Explicitly opt in when you are ready:
systemctl --user enable --now kinect2-broker.service
```

Equivalent one-step opt-in after hardware build:

```bash
bash tools/install_broker_user.sh --enable
```

The installer refuses to overwrite an unrelated
`~/.config/systemd/user/kinect2-broker.service` or launcher symlink.
It does not disable other services, remove lock files or use `sudo`.
The launcher pins conservative OpenMP defaults (`OMP_NUM_THREADS=4`,
`OMP_DYNAMIC=FALSE`). These are editable through the service environment
if future benchmarking recommends it.

`systemctl --user enable` causes the service to start on future
**user-session logins**, not before any user signs in. A final version 1.0
installer must automate this one-time setup and verify behavior across a
reboot. The existing v4l2loopback module's boot setup remains independent
of who owns Kinect USB.

## Smoke test

Ensure there is no separate manually launched broker on the same sockets.
Then:

```bash
systemctl --user status kinect2-broker.service --no-pager
journalctl --user -u kinect2-broker.service -n 50 --no-pager

# With zero FrameClients, expected: broker responds, USB=False,
# streaming=False, all subscription counters zero.
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient
s = BrokerClient().get_status()
print("USB:", s["sensor_open"])
print("STREAMING:", s["streaming"])
print("CLIENTS:", s["frame_preview"])
PY

# Stop active Firefox/legacy V4L2 consumers *before* hardware testing.
python3 tools/demo_four_clients.py
```

Closing one SDK preview must not close the other previews. Closing all
four must return the broker to `sensor_open: False` even while the
systemd service itself stays `active (running)`.

If a manually launched broker already exists, exit it cleanly before
starting this service. Avoid deleting socket/lock files manually.
If service startup fails, inspect journal errors before retrying:
the broker refuses to replace an existing control socket. A genuinely
stale Unix socket after a killed process is a separate recovery case;
do not unlink paths belonging to a live broker.

## Disable / rollback

```bash
systemctl --user disable --now kinect2-broker.service
```

The old RGB webcam service is still present and untouched. This
rollback only stops the broker service; you can continue the previous
standalone workflow. It does not remove libfreenect2, services, loopback
devices or repository files.

## Offline checks (no physical Kinect)

```bash
bash -n tools/run_broker_service.sh tools/install_broker_user.sh
python3 -m unittest tests.test_broker_user_service -v
```

The unit installer tests use a fake `systemctl` and a dummy
hardware broker and never modify actual user services.
