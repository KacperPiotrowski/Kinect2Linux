#!/usr/bin/env bash
# One-time root setup of /dev/video11 only; no change to /dev/video10.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run: sudo bash webcam/install-device.sh' >&2
  exit 1
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for cmd in modprobe v4l2loopback-ctl systemctl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    case "$cmd" in
      modprobe) package=kmod ;;
      v4l2loopback-ctl) package=v4l2loopback-utils ;;
      systemctl) package=systemd ;;
    esac
    echo "Missing $cmd (install $package)" >&2
    exit 1
  fi
done
# Check compatibility before writing a systemd unit or loading a module.
bash "$ROOT/check-loopback.sh" --installed
install -D -o root -g root -m 0755 "$ROOT/check-loopback.sh" /usr/local/libexec/kinect2-v4l2-check
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
