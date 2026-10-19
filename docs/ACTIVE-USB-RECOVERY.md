# Active USB loss: broker fail-fast recovery (draft)

**Status: DRAFT, offline-tested only; do not deploy to the physical Kinect
station before explicit hardware approval and verification.** See #32.

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
- The prior physically observed hang is not yet proven fixed.

**Required before merging/deploying:** CI green, maintainer review, a
controlled service switchover only after explicit consent, and physical
retest of active unplug/replug. Verify PID changes once, broker status
responds after restart, no persistent socket or USB lock prevents new
subscribers, a fresh IR subscriber receives frames, Firefox and 4 SDK
clients still work, and normal idle USB release still works. Record
behavior if libfreenect2 blocks before the watchdog sees device absence.
