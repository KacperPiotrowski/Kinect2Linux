#!/usr/bin/env bash
# Read-only compatibility preflight for broker RGB on v4l2loopback.
# --installed: inspect the loaded module or the module for this kernel.
# --loaded: require the running module (used before broker activation).
set -euo pipefail

fail() {
  printf 'Kinect2 V4L2: %s\n' "$*" >&2
  exit 2
}

case "${1:---loaded}" in
  --loaded|--installed) mode="${1:---loaded}" ;;
  *) fail 'Usage: check-loopback.sh [--loaded|--installed]' ;;
esac

if [[ -d /sys/module/v4l2loopback ]]; then
  [[ -r /sys/module/v4l2loopback/version ]] ||
    fail 'Loaded v4l2loopback has no readable version; cannot verify CLIENT_USAGE support.'
  version=$(cat /sys/module/v4l2loopback/version)
else
  [[ $mode == --installed ]] ||
    fail 'v4l2loopback is not loaded; prepare the named virtual RGB camera first.'
  command -v modinfo >/dev/null 2>&1 || fail 'modinfo unavailable (install kmod).'
  version=$(modinfo -F version v4l2loopback 2>/dev/null) ||
    fail 'Cannot inspect v4l2loopback module for this kernel (install compatible DKMS module).'
fi

if [[ ! $version =~ ^([0-9]+)\.([0-9]+)(\.[0-9]+)?([-+].*)?$ ]]; then
  fail "Unrecognized v4l2loopback version '$version'; cannot confirm CLIENT_USAGE compatibility."
fi
major=${BASH_REMATCH[1]}
minor=${BASH_REMATCH[2]}
if (( 10#$major == 0 && 10#$minor < 13 )); then
  fail "v4l2loopback $version is unsupported: broker RGB requires CLIENT_USAGE events (>= 0.13). Ubuntu 24.04 packages 0.12.7; upgrade the module and tools explicitly before enabling V4L2."
fi
printf 'Kinect2 V4L2: compatible v4l2loopback version %s (minimum 0.13; event support confirmed at broker start).\n' "$version"
