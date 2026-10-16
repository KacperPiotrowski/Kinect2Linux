#!/usr/bin/env bash
# Installed root-owned at /usr/local/libexec/kinect2-rgb-device.
# It never accesses user-owned project scripts as root.
set -euo pipefail
# If this module was not loaded yet, preserve the existing IR convention.
# Avoid creating a random extra /dev/video0 (which would look like a second camera).
if [[ ! -d /sys/module/v4l2loopback ]]; then
  /usr/bin/modprobe v4l2loopback video_nr=10 card_label=Kinect-v2-IR exclusive_caps=1
fi
if [[ -e /dev/video11 ]]; then
  label="$(cat /sys/class/video4linux/video11/name 2>/dev/null || true)"
  if [[ "$label" != "Kinect v2 RGB" ]]; then
    echo "Refusing to reuse /dev/video11: '$label' (not Kinect v2 RGB)" >&2
    exit 1
  fi
else
  /usr/bin/v4l2loopback-ctl add -x 1 -n 'Kinect v2 RGB' /dev/video11
fi
# Never unload the module, remove devices, or alter an already loaded /dev/video10.
