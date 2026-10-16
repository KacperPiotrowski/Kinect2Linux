#!/usr/bin/env bash
# Install a per-user service that starts RGB producer on KDE login.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo 'Run as your regular user, without sudo.' >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$ROOT/bin/kinect_rgb_bridge" ]] || { echo 'Build first: bash webcam/build.sh' >&2; exit 1; }
[[ -c /dev/video11 ]] || { echo 'Create device first: sudo bash webcam/install-device.sh' >&2; exit 1; }
[[ "$(cat /sys/class/video4linux/video11/name 2>/dev/null || true)" == 'Kinect v2 RGB' ]] || {
  echo '/dev/video11 is not our Kinect v2 RGB loopback.' >&2; exit 1;
}
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
ln -sfn "$ROOT/webcam/run.sh" "$HOME/.local/bin/kinect2-rgb-run"
cat > "$HOME/.config/systemd/user/kinect2-rgb-webcam.service" <<'UNIT'
[Unit]
Description=Kinect v2 RGB webcam for KDE/PipeWire
Documentation=man:systemd.service(5)
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=%h/.local/bin/kinect2-rgb-run
Restart=always
RestartSec=12

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now kinect2-rgb-webcam.service
echo '[OK] RGB webcam startup enabled for KDE user session.'
echo 'Status: systemctl --user status kinect2-rgb-webcam.service'
