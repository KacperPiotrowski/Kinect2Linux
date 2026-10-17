#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CXX="${CXX:-g++}"
MODE="${1:-}"

if [[ $# -gt 1 || ( -n "$MODE" && "$MODE" != "--with-hardware" ) ]]; then
  echo "Usage: bash tools/build_broker.sh [--with-hardware]" >&2
  exit 2
fi

PROFILE="offline"
HW_FLAG=OFF
if [[ "$MODE" == "--with-hardware" ]]; then
  PROFILE="hardware"
  HW_FLAG=ON
fi

BUILD_DIR="$ROOT/build/broker-$PROFILE"
LIB_DIR="$(readlink -f -- "${LIBFREENECT2_DIR:-$ROOT/../libfreenect2-omp}")"
cmake -S "$ROOT" -B "$BUILD_DIR" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$CXX" \
  -DKINECT2_ENABLE_HARDWARE="$HW_FLAG" \
  -DLIBFREENECT2_DIR="$LIB_DIR"
cmake --build "$BUILD_DIR" --parallel

if [[ "$HW_FLAG" == ON ]]; then
  echo "Built: $ROOT/bin/kinect2-broker-hw, worker and native tests (incremental)"
else
  echo "Built: $ROOT/bin/kinect2-broker, worker and native tests (incremental)"
fi
