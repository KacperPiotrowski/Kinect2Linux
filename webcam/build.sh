#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/tools/libfreenect2_path.sh"
LIB_DIR="$(kinect2_libfreenect2_dir "$ROOT")"
SO="$LIB_DIR/build-omp/lib/libfreenect2.so"
[[ -f "$SO" ]] || { echo "Missing libfreenect2 OpenMP: $SO" >&2; exit 1; }
mkdir -p "$ROOT/bin"
g++ -std=c++11 -O2 -Wall -Wextra \
  -I"$LIB_DIR/include" -I"$LIB_DIR/build-omp" \
  "$ROOT/src/kinect_rgb_bridge.cpp" \
  -L"$LIB_DIR/build-omp/lib" -Wl,-rpath,"$LIB_DIR/build-omp/lib" \
  -lfreenect2 -o "$ROOT/bin/.kinect_rgb_bridge.new"
mv -f "$ROOT/bin/.kinect_rgb_bridge.new" "$ROOT/bin/kinect_rgb_bridge"
echo "[OK] Built: $ROOT/bin/kinect_rgb_bridge"
