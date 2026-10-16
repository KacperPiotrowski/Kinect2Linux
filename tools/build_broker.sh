#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/bin"
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -Werror \
  "$ROOT/src/kinect_broker.cpp" -o "$ROOT/bin/kinect2-broker"
printf 'Built control-only broker: %s\n' "$ROOT/bin/kinect2-broker"
