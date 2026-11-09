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
if [[ -x /usr/bin/systemctl ]]; then
  SYSTEMCTL=/usr/bin/systemctl
elif [[ -x /bin/systemctl ]]; then
  SYSTEMCTL=/bin/systemctl
else
  echo 'Missing systemctl: a systemd installation is required.' >&2
  exit 2
fi
# Dynamic add tools are not required for the initial dual-device modprobe.
# Validate/create the pair before writing a persistent system unit. A loaded
# old module without RGB will give safe recovery instructions and exit here.
bash "$ROOT/device-onboot.sh"
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
"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" enable --now kinect2-rgb-device.service
"$SYSTEMCTL" is-active --quiet kinect2-rgb-device.service ||
  { echo 'Device setup service did not remain active; inspect journalctl -u kinect2-rgb-device.' >&2; exit 2; }
printf '[OK] Kinect IR and RGB virtual cameras prepared: /dev/video10, /dev/video11\n'
