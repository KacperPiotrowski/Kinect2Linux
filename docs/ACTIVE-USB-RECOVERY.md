# Active USB loss: broker fail-fast recovery (preview)

**Status: tested on one physical Kinect v2 (Arch Linux/KDE, October 2026),
including supervised fail-fast restart and fresh IR after recovery. PR #33
remains a draft and is NOT merged or deployed to the installed original
broker service.** See #32 and #33.

## Failure observed on physical hardware

An IR FrameClient held one native Kinect v2 USB capture session.
After unplugging/replugging USB while frames were flowing:

- sysfs observed device count 1 -> 0 -> 1;
- frames stopped, even after the USB device reappeared;
- `sensor_open` and `streaming` remained true because they reflected the
  configured session, not successful frame delivery;
- after the subscriber departed the control broker stopped replying;
- the process stayed alive (`NRestarts=0`), with USB transfer
  `LIBUSB_ERROR_NO_DEVICE` and a thread waiting in a futex.

The pinned upstream OpenKinect `TransferPool::cancel()` loops until every
submitted transfer is marked stopped, with no timeout. We cannot prove that
this is the exact blocked instruction without a native stack trace, but the
design has an unbounded native teardown path after device removal.

**Do not add a timeout and free outstanding libusb transfers:** completing
`cancel()` without proving transfers are stopped can free callback-owned
memory while libusb still refers to it.

## Fail-fast behavior proposed in this branch

When the broker owns an *active* streaming session, it checks **read-only
sysfs USB enumeration** before subscriber reconciliation. If it has
previously observed at least one Kinect v2 while streaming and a subsequent
successful scan finds zero Kinect v2 devices:

1. Log a clear fatal USB-loss reason.
2. Unlink **only its own verified** frame and control socket inode names in
   the private user runtime directory; never remove an unknown path.
3. Call `_exit(75)` **without calling native USB stop/close**. Linux cleans up
   process descriptors, closes subscriber connections, releases advisory
   flock and USB resources, and sends the supervised helper its parent-death
   signal. We do not attempt to cancel/free libusb transfers in the dying
   process.
4. If installed through the documented user service,
   `Restart=on-failure` restarts the broker after the configured 5-second
   delay. A manually launched broker exits and requires its operator to
   relaunch it.

**Service restart is a failover, not transparent frame recovery.** Existing
`FrameClient` connections become invalid; clients must reconnect to the
new broker socket after the new service has started. Browser V4L2 readers
may need to reopen the camera. The current SDK does not auto-reconnect.

This path is intentionally restricted to confirmed *physical absence* of
the only connected Kinect. It does not recover a motionless sensor that
remains present in sysfs, a native deadlock occurring before enumeration, a
broker killed externally with stale socket paths, or multi-Kinect USB
topologies. A transient real USB reset may also trigger broker restart.

## Safety and release validation

- Neither the new code nor its tests open USB or alter PipeWire, ALSA, PAM,
  authentication, V4L2 configuration or user services.
- The emergency exit is **not run** during ordinary idle USB removal.
- It is triggered only by the broker's existing opt-in hardware
  `--auto-streams` mode with an active stream and verified presence loss.
- Offline unit coverage: `test_usb_disconnect_guard` for state transitions,
  `test_frame_hub` for owned socket path cleanup and preservation of
  a replacement pathname.
- The previously reproduced active-stream unplug scenario was contained on
  this test station: a confirmed USB disappearance exited with status 75,
  avoiding the previously observed stuck native teardown. This is not proof
  that all USB failure modes or native deadlocks are fixed.

## Physical acceptance results (October 19, 2026)

All observations below are from the maintainer's **single Kinect v2** test
station and a separate branch checkout, not a universal compatibility claim.

- **Build/CI:** hardware-enabled branch build succeeded against pinned local
  `libfreenect2-omp`; native CTest **8/8 PASS**. GitHub Actions for the
  tested source commit succeeded. Documentation changes need their own CI check.
- **Normal capture:** a single SDK IR client received a real `512x424`
  frame on PR #33, then auto-capture closed and released USB.
- **Manual fail-fast:** while IR was actively producing frames, a physical USB
  disconnect/reconnect was independently observed in sysfs as **1 -> 0 -> 1**.
  The IR client lost its IPC connection, the original broker PID exited,
  and both owned IPC socket pathnames were absent. A fresh manually launched
  PR #33 broker then successfully captured IR and returned to idle.
- **systemd failover:** a temporary user unit with `Restart=on-failure` logged
  `FATAL: active Kinect USB disappeared` and `status=75/TEMPFAIL`.
  The supervisor restarted the broker exactly once in this test:
  PID **283416 -> 283814**, `NRestarts=1`. A newly connected IR client
  received a real `512x424` frame, and USB was released afterward.
  **Existing FrameClient instances do not automatically reconnect.**
- **Firefox + SDK regression:** on a separate temporary PR #33 user unit
  with the in-process RGB V4L2 adapter on `/dev/video11`, Firefox displayed
  smooth video with no V4L2 `dropped` frames reported. During an 18-second
  overlapping test, Firefox + **2 RGB and 2 IR SDK subscribers** simultaneously
  received frames: each RGB client 505 frames, each IR client 524 frames,
  with strictly increasing publication timestamps and no receive exceptions.
  The V4L2 adapter wrote 506 additional frames and reported zero drops.
  After SDK clients exited, subscriber count returned to zero; closing
  Firefox returned the sensor to idle; the test broker shut down cleanly.
- **Sequence caveat:** while adding IR during RGB capture, both IR clients
  observed a native `sequence` transition **34 -> 0** at the second sample
  (then increasing), plus **7 IR** and **13 RGB** positive sequence gaps per
  SDK client during the 18-second test. A separate 12-frame IR diagnostic
  verified increasing publication times and distinct content hashes.
  Stream selection changes trigger native stop/restart, making a counter
  reset plausible, **but the exact cause has not been proven**. Do not
  advertise zero sequence gaps or uninterrupted native numbering.

Temporary test units were stopped and did not replace or edit the installed
`kinect2-broker.service`. No USB security parameters, USB lock-file paths,
audio configuration, or V4L2 kernel/device configuration were modified.

## Before merging or deploying

- Re-run CI for any commits after these hardware observations and review the
  final patch, including inode-checked cleanup and single-Kinect limitation.
- Review the expected client reconnect behavior and publication-sequence caveat
  with the SDK/API documentation; avoid promising transparent recovery.
- Restore and verify the original user broker after the V4L2 validation
  (the last recorded step stopped only the temporary PR #33 unit).
- A fresh installation on a different Linux machine and audio quality checks
  are separate wider release-readiness work, **not claimed as completed** by
  this USB-failsafe PR. Audio was deliberately not re-tested in this round.

