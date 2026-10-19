# Kinect2Linux: optional broker IR -> Howdy camera experiment

The current system exposes RGB to Firefox at /dev/video11 from a single broker.
IR is available to independent SDK subscribers as 512x424 float32 frames.
The legacy ./kinect2 run bridge opens Kinect USB directly and **must NOT**
run beside the broker.

This PR introduces an **opt-in, foreground-only, one-way IR V4L2 producer**:
broker FrameClient("ir") -> percentile normalization -> YUYV422 -> /dev/video10.
It never opens physical USB, creates devices, installs services, sets system
defaults, invokes Howdy, changes PAM, or runs inference. It is not face
recognition, liveness protection, or a secure biometric authentication system.

## Hardware preparation and safety

Before any stream test, check that Howdy is not actively wired into any
authentication flow. A Howdy config line \`disabled = false\` means Howdy
is enabled in its own config, **not** that PAM integration is absent. Use
read-only inspection:

\`\`\`bash
grep -RnsE 'pam_(python|howdy)|howdy' /etc/pam.d 2>/dev/null || true
\`\`\`

Do not edit PAM/SDDM, enroll faces, or run Howdy tests yet.
Ensure the old \`kinect_ir_bridge\` is not running; two IR writers to
/dev/video10 should never be started.

Start with a read-only check of device identity:

\`\`\`bash
python3 tools/broker_ir_v4l2.py --check
\`\`\`

Expect \`/dev/video10: Kinect-v2-IR\`. The check does not open the device.

## Explicitly start a short broker IR trial (only after review)

\`\`\`bash
python3 tools/broker_ir_v4l2.py --run --max-frames 90
\`\`\`

Requires numpy and the broker with automatic frame subscriptions enabled.
Writes 512x424 YUYV422 into the existing /dev/video10, without acquiring
a second Kinect USB handle. The Kinect broker can continue serving Firefox
RGB concurrently. Stops automatically after 90 successfully written frames.
The entire bridge can be stopped with Ctrl+C. If data stalls for two seconds,
a black image is written to avoid intentionally leaving the most recent
good IR frame as the live image; this is not liveness protection.

For ongoing manual diagnosis, omit \`--max-frames\` and use Ctrl+C.
**IR remains subscribed while the bridge runs**, even without any Howdy
reader. Auto-start or on-demand reader detection is future, separate work.

Check for actual IR data with a *regular camera viewer* before testing Howdy.
No PAM or authentication integration belongs to this experiment.

## Offline tests

\`\`\`bash
PYTHONPATH=sdk/python python3 -m unittest discover \
  -s tests -p 'test_broker_ir_v4l2.py' -v
\`\`\`

## Limitations

- /dev/video10 must already exist with the exact name Kinect-v2-IR.
- Uses Linux x86_64 V4L2 ioctl layout; explicitly refuses a different struct size.
- Depends on numpy for IR float32 intensity scaling, not on AI/MediaPipe.
- No service, login-screen integration, user switching, or sudo authentication.
  The broker lives in the signed-in user session; SDDM before login cannot
  assume it is active or reachable.
- Howdy may need an explicit compatible capture resolution and access
  permissions; this PR doesn't edit /etc/howdy/config.ini.
- Howdy face identification must be validated separately and reviewed for
  security before enabling PAM. Kinect depth is NOT liveness validation.
