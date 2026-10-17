#!/usr/bin/env bash
# Guided opt-in installation. Never runs sudo, installs packages, or disables legacy services.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "\${BASH_SOURCE[0]}")/.." && pwd)"
LEGACY=kinect2-rgb-webcam.service
BROKER=kinect2-broker.service
DEVICE=/dev/video11
NAME_FILE=/sys/class/video4linux/video11/name
DROPIN="$HOME/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf"
USER_UNIT="$HOME/.config/systemd/user/kinect2-broker.service"

usage() {
  cat <<'USAGE'
Usage: bash tools/install_kinect2.sh [--check | --prepare | --activate | --help]
  --check     Read-only inspection of build tools and webcam/service states (default).
  --prepare   Compile pinned libfreenect2-omp and broker, run native tests,
              install user service WITHOUT enabling or starting it.
  --activate  Explicitly enable/start broker V4L2, only if legacy webcam
              is stopped/disabled and the verified RGB device exists.
Review docs/INSTALL.md before activation. Installer never invokes sudo or pacman.
USAGE
}
log() { printf '[kinect2] %s\n' "$*"; }
fail() { printf '[kinect2] ERROR: %s\n' "$*" >&2; exit 2; }
check_user() {
  [[ $(uname -s) == Linux ]] || fail "Only Linux is supported."
  [[ $EUID -ne 0 ]] || fail "Run as your ordinary user, not sudo."
  [[ -n \${HOME:-} && -d $HOME ]] || fail "Missing HOME directory."
}
service_state() { systemctl --user "$1" "$2" 2>/dev/null || true; }

preflight() {
  check_user
  local missing=0 command_name camera_name
  log 'Read-only prerequisite check'
  for command_name in git g++ cmake ninja pkg-config systemctl; do
    if command -v "$command_name" >/dev/null 2>&1; then
      log "OK: $command_name"
    else
      log "MISSING: $command_name"; missing=1
    fi
  done
  if command -v v4l2loopback-ctl >/dev/null 2>&1; then
    log 'OK: v4l2loopback-ctl'
  else
    log 'INFO: v4l2loopback tools required for a new /dev/video11.'
  fi
  if [[ -c $DEVICE ]]; then
    camera_name=$(cat "$NAME_FILE" 2>/dev/null || true)
    if [[ $camera_name == 'Kinect v2 RGB' ]]; then
      log 'OK: /dev/video11 = Kinect v2 RGB'
    else
      log 'WARNING: foreign /dev/video11; do NOT overwrite it.'
    fi
  else
    log 'INFO: /dev/video11 absent; see docs/INSTALL.md.'
  fi
  if command -v systemctl >/dev/null 2>&1; then
    log "Broker: active=$(service_state is-active "$BROKER"), enabled=$(service_state is-enabled "$BROKER")"
    log "Legacy RGB: active=$(service_state is-active "$LEGACY"), enabled=$(service_state is-enabled "$LEGACY")"
  fi
  (( ! missing )) || fail 'Missing build tools: see docs/INSTALL.md.'
  log 'Preflight complete; no changes made.'
}
prepare() {
  preflight
  [[ $(service_state is-active "$BROKER") != active ]] ||
    fail 'Broker is running; refusing to rewrite its unit. Stop it manually only when idle.'
  bash "$ROOT/tools/bootstrap_libfreenect2_omp.sh"
  bash "$ROOT/tools/build_broker.sh" --with-hardware
  "$ROOT/bin/test_auto_capture"
  "$ROOT/bin/test_v4l2_rgb"
  bash "$ROOT/tools/install_broker_user.sh"
  log 'Prepared, without autostart. Review device setup, then --activate.'
}
activate() {
  check_user
  command -v systemctl >/dev/null 2>&1 || fail 'systemctl required.'
  [[ -x $ROOT/bin/kinect2-broker-hw ]] || fail 'Run --prepare first (missing hardware broker).'
  [[ -f $USER_UNIT && ! -L $USER_UNIT ]] || fail 'Managed user unit missing; run --prepare.'
  grep -Fxq '# Managed by Kinect2-Linux broker installer.' "$USER_UNIT" ||
    fail 'Refusing unmanaged broker unit.'
  [[ -c $DEVICE ]] || fail '/dev/video11 missing; set up explicitly (docs/INSTALL.md).'
  [[ $(cat "$NAME_FILE" 2>/dev/null || true) == 'Kinect v2 RGB' ]] ||
    fail 'Refusing unexpected /dev/video11 device.'
  local active enabled
  active=$(service_state is-active "$LEGACY")
  enabled=$(service_state is-enabled "$LEGACY")
  [[ $active != active && $active != activating ]] ||
    fail 'Legacy RGB service active. Stop it manually after closing readers.'
  [[ $enabled != enabled && $enabled != enabled-runtime ]] ||
    fail 'Legacy RGB autostart enabled. Disable it manually first.'
  [[ $(service_state is-active "$BROKER") != active ]] ||
    fail 'Broker already active; refusing to restart existing client streams.'
  [[ ! -L $DROPIN ]] || fail "Refusing symlinked configuration: $DROPIN"
  if [[ -e $DROPIN ]]; then
    cmp -s "$DROPIN" <(printf '[Service]\nEnvironment=KINECT2_BROKER_V4L2=1\n') ||
      fail "Refusing to overwrite different configuration: $DROPIN"
  else
    (umask 077; mkdir -p "$(dirname -- "$DROPIN")";
     set -C; printf '[Service]\nEnvironment=KINECT2_BROKER_V4L2=1\n' > "$DROPIN")
  fi
  systemctl --user daemon-reload
  systemctl --user enable --now "$BROKER"
  log 'Broker V4L2 activated. Verify Firefox and automatic USB idle release.'
  log 'Rollback instructions: docs/INSTALL.md.'
}
[[ $# -le 1 ]] || { usage >&2; exit 2; }
case "\${1:---check}" in
  -h|--help) usage ;;
  --check) preflight ;;
  --prepare) prepare ;;
  --activate) activate ;;
  *) usage >&2; exit 2 ;;
esac
