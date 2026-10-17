#!/usr/bin/env bash
# Explicit opt-in setup of ONE primary user broker service.
# Never enable/disable any legacy webcam service automatically.
set -euo pipefail

usage() {
  echo "Usage: bash tools/install_broker_user.sh [--enable]" >&2
  echo "  default: install user unit but do NOT enable or start it" >&2
  echo "  --enable: explicitly enable and start this broker unit" >&2
}
if [[ $# -gt 1 || ( $# -eq 1 && "${1:-}" != "--enable" ) ]]; then
  usage
  exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Install the Kinect user service as your normal user, without sudo.' >&2
  exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/tools/run_broker_service.sh"
BROKER="$ROOT/bin/kinect2-broker-hw"
if [[ ! -f "$SCRIPT" || ! -x "$BROKER" ]]; then
  echo "Hardware-enabled broker is missing. Build it first:" >&2
  echo '  bash tools/bootstrap_libfreenect2_omp.sh' >&2
  echo '  bash tools/build_broker.sh --with-hardware' >&2
  exit 2
fi
command -v systemctl >/dev/null || {
  echo 'systemctl not found; this installer requires systemd --user.' >&2
  exit 2
}

umask 077
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
link="$HOME/.local/bin/kinect2-broker-run"
unit="$HOME/.config/systemd/user/kinect2-broker.service"

# Do not silently replace any unrelated executable, symlink or user unit.
if [[ -e "$link" || -L "$link" ]]; then
  if [[ ! -L "$link" || "$(readlink -f -- "$link")" != "$SCRIPT" ]]; then
    echo "Refusing to overwrite existing path: $link" >&2
    exit 2
  fi
fi
if [[ -e "$unit" || -L "$unit" ]]; then
  if [[ -L "$unit" || ! -f "$unit" ]] ||
     ! grep -Fxq '# Managed by Kinect2-Linux broker installer.' "$unit"; then
    echo "Refusing to overwrite existing user unit: $unit" >&2
    exit 2
  fi
fi

if [[ ! -L "$link" ]]; then
  ln -s -- "$SCRIPT" "$link"
fi
cat > "$unit" <<'UNIT'
# Managed by Kinect2-Linux broker installer.
# Experimental until the in-process V4L2 adapter is hardware-validated.
[Unit]
Description=Kinect v2 single USB broker (RGB/IR/Depth)
Documentation=man:systemd.service(5)
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
ExecStart=/usr/bin/bash %h/.local/bin/kinect2-broker-run
UMask=0077
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
NoNewPrivileges=true

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
echo "[OK] Installed optional user unit: $unit"
if [[ "${1:-}" == "--enable" ]]; then
  # Explicit caller opt-in. Legacy webcam stays untouched, so they cannot
  # capture USB simultaneously; the broker stays idle with zero subscribers.
  systemctl --user enable --now kinect2-broker.service
  echo '[OK] Enabled and started the broker user service.'
else
  echo 'No service started or enabled. To opt in:'
  echo '  systemctl --user enable --now kinect2-broker.service'
fi
echo 'Legacy webcam service and v4l2loopback configuration were NOT changed.'
echo 'Inspect logs: journalctl --user -u kinect2-broker.service -n 40'
