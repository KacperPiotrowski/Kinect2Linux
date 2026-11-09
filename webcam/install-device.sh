#!/usr/bin/env bash
# One-time explicit privileged setup of named virtual devices.
# Never loads Kinect USB, unloads modules or alters existing foreign nodes.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run: sudo bash webcam/install-device.sh' >&2
  exit 1
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x /usr/bin/modprobe && ! -x /usr/sbin/modprobe ]]; then
  echo 'Missing modprobe: install kmod.' >&2
  exit 2
fi
if [[ ! -x /usr/bin/systemctl && ! -x /bin/systemctl ]]; then
  echo 'Missing systemctl: a systemd installation is required.' >&2
  exit 2
fi
# Dynamic add tools are not required for the initial dual-device modprobe.
# A loaded old module will report safe manual recovery steps instead.
install -D -o root -g root -m 0755 "$ROOT/device-onboot.sh" /usr/local/libexec/kinect2-rgb-device
cat > /etc/systemd/system/kinect2-rgb-device.service <<'UNIT'
[Unit]
Description=Create Kinect v2 RGB and IR virtual cameras (/dev/video10,11)
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
systemctl is-active --quiet kinect2-rgb-device.service ||
  { echo 'Device setup service did not remain active; inspect journalctl -u kinect2-rgb-device.' >&2; exit 2; }
printf '[OK] Kinect IR and RGB virtual cameras prepared: /dev/video10, /dev/video11\n'
