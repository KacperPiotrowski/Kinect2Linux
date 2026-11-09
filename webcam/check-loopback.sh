#!/usr/bin/env bash
# Diagnostic ONLY; a version is never proof of kernel CLIENT_USAGE support.
# Probe the running /dev/video11 by VIDIOC_SUBSCRIBE_EVENT before activation.
set -euo pipefail
fail() { printf 'Kinect2 V4L2: %s\n' "$*" >&2; exit 2; }
case "${1:---loaded}" in
  --loaded|--installed) mode="${1:---loaded}" ;;
  *) fail 'Usage: check-loopback.sh [--loaded|--installed]' ;;
esac

if [[ -d /sys/module/v4l2loopback ]]; then
  [[ -r /sys/module/v4l2loopback/version ]] ||
    fail 'v4l2loopback is loaded but its version cannot be read.'
  version=$(cat /sys/module/v4l2loopback/version)
else
  [[ $mode == --installed ]] ||
    fail 'v4l2loopback is not loaded; prepare /dev/video11 before probing CLIENT_USAGE.'
  command -v modinfo >/dev/null 2>&1 ||
    fail 'modinfo unavailable (install kmod).'
  version=$(modinfo -F version v4l2loopback 2>/dev/null) ||
    fail 'Cannot inspect v4l2loopback module for this kernel.'
fi
[[ -n $version ]] || fail 'Module version was empty.'
printf 'Kinect2 V4L2: version %s. This does NOT prove event compatibility.\n' "$version"
if [[ $version == 0.12.* ]]; then
  echo 'Kinect2 V4L2: 0.12.x may support Ubuntu-backported CLIENT_USAGE; stock upstream 0.12.x does not.'
fi
echo 'Kinect2 V4L2: before activation run the built bin/kinect2-v4l2-probe with /dev/video11 present.'
