#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/bin"
CXX="${CXX:-g++}"
FLAGS=(-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror -I"$ROOT")
"$CXX" "${FLAGS[@]}" \
  "$ROOT/src/kinect_broker.cpp" "$ROOT/core/sensor_backend.cpp" \
  -o "$ROOT/bin/kinect2-broker"
"$CXX" "${FLAGS[@]}" \
  "$ROOT/tests/native/test_sensor_backend.cpp" "$ROOT/core/sensor_backend.cpp" \
  -o "$ROOT/bin/test_sensor_backend"
printf "Built broker and offline sensor tests in %s\n" "$ROOT/bin"
