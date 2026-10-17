#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/bin"
CXX="${CXX:-g++}"
FLAGS=(-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror -I"$ROOT")
SRC=("$ROOT/src/kinect_broker.cpp" "$ROOT/core/sensor_backend.cpp"
     "$ROOT/core/device_session.cpp" "$ROOT/core/libfreenect2_hardware.cpp")
LINK=()
TARGET="$ROOT/bin/kinect2-broker"
if [[ $# -eq 1 && $1 == "--with-hardware" ]]; then
  LIB_DIR="$(readlink -f -- "${LIBFREENECT2_DIR:-$ROOT/../libfreenect2-omp}")"
  SO_DIR="$LIB_DIR/build-omp/lib"
  if [[ ! -f "$SO_DIR/libfreenect2.so" || ! -f "$LIB_DIR/include/libfreenect2/libfreenect2.hpp" ]]; then
    echo "Brak libfreenect2-omp: $LIB_DIR (wymaga build-omp)" >&2
    exit 1
  fi
  FLAGS+=(-DKINECT2_WITH_LIBFREENECT2 -I"$LIB_DIR/include" -I"$LIB_DIR/build-omp")
  LINK+=(-L"$SO_DIR" -Wl,-rpath,"$SO_DIR" -lfreenect2)
  TARGET="$ROOT/bin/kinect2-broker-hw"
elif [[ $# -ne 0 ]]; then
  echo "Usage: bash tools/build_broker.sh [--with-hardware]" >&2
  exit 2
fi
"$CXX" "${FLAGS[@]}" "${SRC[@]}" "${LINK[@]}" -o "$TARGET"
"$CXX" -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror -I"$ROOT" \
  "$ROOT/tests/native/test_sensor_backend.cpp" "$ROOT/core/sensor_backend.cpp" \
  -o "$ROOT/bin/test_sensor_backend"
"$CXX" -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror -I"$ROOT" \
  "$ROOT/tests/native/test_device_session.cpp" "$ROOT/core/device_session.cpp" \
  -o "$ROOT/bin/test_device_session"
printf "Built: %s and native tests\n" "$TARGET"
