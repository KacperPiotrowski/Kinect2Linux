#!/usr/bin/env bash
# Installed root-owned at /usr/local/libexec/kinect2-rgb-device.
# Never unload an existing module, delete devices, or touch USB.
set -euo pipefail

fail() { printf 'Kinect2 V4L2 device setup: %s\n' "$*" >&2; exit 2; }
find_modprobe() {
  if [[ -x /usr/bin/modprobe ]]; then printf '/usr/bin/modprobe';
  elif [[ -x /usr/sbin/modprobe ]]; then printf '/usr/sbin/modprobe';
  else fail 'modprobe missing (install kmod).'; fi
}
modprobe_cmd=$(find_modprobe)

label() { cat "/sys/class/video4linux/$1/name" 2>/dev/null || true; }
check_name() {
  local device=$1 expected=$2
  [[ -c /dev/$device && ! -L /dev/$device ]] || fail "/dev/$device does not exist as a character device."
  [[ $(label "$device") == "$expected" ]] ||
    fail "Refusing /dev/$device: expected '$expected', got '$(label "$device")'."
}

if [[ ! -d /sys/module/v4l2loopback ]]; then
  # Both cameras must be created atomically on v4l2loopback 0.12.x, whose
  # userspace tools cannot dynamically add devices. Tested by Ubuntu reporter.
  [[ ! -e /dev/video10 && ! -L /dev/video10 &&
     ! -e /dev/video11 && ! -L /dev/video11 ]] ||
    fail 'v4l2loopback unloaded but /dev/video10 or /dev/video11 exists; refusing to claim foreign nodes.'
  "$modprobe_cmd" v4l2loopback devices=2 video_nr=10,11 \
    card_label='Kinect-v2-IR,Kinect v2 RGB' exclusive_caps=1,1 ||
    fail 'Could not load v4l2loopback with both named devices.'
else
  # Never replace or unload an existing IR loopback in a running session.
  check_name video10 'Kinect-v2-IR'
  if [[ ! -e /dev/video11 && ! -L /dev/video11 ]]; then
    ctl=''
    if [[ -x /usr/bin/v4l2loopback-ctl ]]; then ctl=/usr/bin/v4l2loopback-ctl;
    elif [[ -x /usr/sbin/v4l2loopback-ctl ]]; then ctl=/usr/sbin/v4l2loopback-ctl;
    fi
    [[ -n $ctl ]] || fail 'Missing v4l2loopback-ctl (install v4l2loopback-utils). Cannot add RGB to a loaded module; close camera clients and plan a safe module reload.'
    # Check the advertised command, not the numeric module version.
    help_text=$("$ctl" --help 2>&1 || true)
    if ! grep -Eq '(^|[[:space:]])add([[:space:]]|$)' <<< "$help_text"; then
      fail 'This v4l2loopback-ctl has no dynamic add command. Close readers of /dev/video10; after checking other consumers, unload the module yourself (modprobe -r v4l2loopback), then retry. The installer will never unload it automatically.'
    fi
    "$ctl" add -x 1 -n 'Kinect v2 RGB' /dev/video11 ||
      fail 'Dynamic creation of RGB failed. Inspect the loaded module and /dev/video11 before retrying.'
  fi
fi

check_name video10 'Kinect-v2-IR'
check_name video11 'Kinect v2 RGB'
echo 'Kinect2 V4L2 device setup: /dev/video10 IR and /dev/video11 RGB verified.'
