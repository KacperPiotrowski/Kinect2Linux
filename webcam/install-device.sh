#!/usr/bin/env bash
# One-time root setup of /dev/video11 only; no change to /dev/video10.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run: sudo bash webcam/install-device.sh' >&2
  exit 1
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for cmd in /usr/bin/modprobe /usr/bin/v4l2loopback-ctl /usr/bin/systemctl; do
  [[ -x "$cmd" ]] || { echo "Missing $cmd (install v4l2loopback-utils)" >&2; exit 1; }
done
install -D -o root -g root -m 0755 "$ROOT/device-onboot.sh" /usr/local/libexec/kinect2-rgb-device
cat > /etc/systemd/system/kinect2-rgb-device.service <<'UNIT'
[Unit]
Description=Create Kinect v2 RGB virtual camera (/dev/video11)
After=systemd-udev-trigger.service

[Service]
Type=oneshot
ExecStart=/usr/local/libexec/kinect2-rgb-device
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now kinect2-rgb-device.service
printf '[OK] RGB virtual camera prepared: /dev/video11\n'
