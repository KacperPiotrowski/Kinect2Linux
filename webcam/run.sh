#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SCRIPT")/.." && pwd)"
APP="$ROOT/bin/kinect_rgb_bridge"
CAMERA="${KINECT_RGB_DEVICE:-/dev/video11}"
LOCK="${XDG_RUNTIME_DIR:-$ROOT}/kinect2-sensor.lock"
[[ -x "$APP" ]] || { echo "Missing RGB bridge. Run: bash webcam/build.sh" >&2; exit 1; }
[[ -c "$CAMERA" ]] || { echo "Missing $CAMERA. Run: sudo bash webcam/install-device.sh" >&2; exit 1; }
if [[ "$CAMERA" == "/dev/video11" ]]; then
  label="$(cat /sys/class/video4linux/video11/name 2>/dev/null || true)"
  [[ "$label" == "Kinect v2 RGB" ]] || { echo "Unexpected device at $CAMERA: '$label'" >&2; exit 1; }
fi
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export OMP_DYNAMIC=FALSE
export KINECT_RGB_LOCK="$LOCK"
# Read-only runtime snapshot for ./kinect2 status (never stored in the Git repo).
export KINECT_RGB_STATE="${KINECT_RGB_STATE:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kinect2-rgb-state.json}"
exec "$APP" "$CAMERA"
