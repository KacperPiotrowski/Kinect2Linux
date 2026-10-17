#!/usr/bin/env bash
# Single Kinect USB owner: user-managed broker, no independent V4L2 producer.
set -euo pipefail

SELF="$(readlink -f -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SELF")/.." && pwd)"
BROKER="$ROOT/bin/kinect2-broker-hw"

if [[ $EUID -eq 0 ]]; then
  echo 'Run the Kinect broker as your normal user, not root.' >&2
  exit 2
fi
if [[ -z "${XDG_RUNTIME_DIR:-}" || ! -d "$XDG_RUNTIME_DIR" ]]; then
  echo 'Missing XDG_RUNTIME_DIR (use systemd --user in a logged-in session).' >&2
  exit 2
fi
if [[ ! -x "$BROKER" ]]; then
  echo "Missing hardware-enabled broker: $BROKER" >&2
  echo 'Build it with: bash tools/bootstrap_libfreenect2_omp.sh && bash tools/build_broker.sh --with-hardware' >&2
  exit 2
fi
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export OMP_DYNAMIC=FALSE
exec "$BROKER" --allow-device-control --frame-preview --auto-streams
