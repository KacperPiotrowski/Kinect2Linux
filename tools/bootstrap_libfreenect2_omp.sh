#!/usr/bin/env bash
# Reproducible, opt-in source restoration from reviewed public upstream.
# Never alters an existing ../libfreenect2-omp checkout.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/third_party/libfreenect2-omp"
PATCH="$ROOT/third_party/patches/libfreenect2-omp-cpu-depth.patch"
UPSTREAM="https://github.com/OpenKinect/libfreenect2.git"
# Official OpenKinect master (2020-03-01), identified by comparing the
# supplied libfreenect2-omp archive against exact upstream Git blobs.
PIN="fd64c5d9b214df6f6a55b4419357e51083f15d93"
UPSTREAM_CPU="85966b7dd39a1977b6f2f2b3a203f35a0d9f65e0"
PATCHED_CPU="14756995f96687336e6614d83f99028cc680c4d5"
SOURCE_ONLY=false

if [[ $# -gt 1 || ( $# -eq 1 && "${1}" != "--source-only" ) ]]; then
  echo "Usage: bash tools/bootstrap_libfreenect2_omp.sh [--source-only]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then SOURCE_ONLY=true; fi

for tool in git; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing dependency: $tool" >&2
    exit 2
  fi
done

mkdir -p "$ROOT/third_party"
if [[ -e "$DEST" || -L "$DEST" ]]; then
  if [[ ! -d "$DEST/.git" ]]; then
    echo "Refusing to touch an existing non-Git path: $DEST" >&2
    exit 2
  fi
  CURRENT="$(git -C "$DEST" rev-parse HEAD)"
  if [[ "$CURRENT" != "$PIN" ]]; then
    echo "Existing checkout at $DEST uses $CURRENT, expected $PIN." >&2
    echo "Refusing to overwrite it; inspect or move it yourself." >&2
    exit 2
  fi
  if [[ ! -f "$DEST/include/libfreenect2/libfreenect2.hpp" ]]; then
    echo "Pinned checkout has missing headers; refusing to auto-repair." >&2
    exit 2
  fi
  ACTUAL="$(git -C "$DEST" hash-object src/cpu_depth_packet_processor.cpp)"
  if [[ "$ACTUAL" == "$UPSTREAM_CPU" ]]; then
    git -C "$DEST" apply --check "$PATCH"
    git -C "$DEST" apply "$PATCH"
  elif [[ "$ACTUAL" != "$PATCHED_CPU" ]]; then
    echo "Found an unknown CPU depth source; will not overwrite it: $DEST" >&2
    exit 2
  fi
else
  # Clone into a temporary sibling, verify its code and only then publish.
  TEMP="$(mktemp -d "$ROOT/third_party/.libfreenect2-omp.XXXXXXXX")"
  trap 'if [[ -n "${TEMP:-}" && -d "$TEMP" ]]; then rm -rf -- "$TEMP"; fi' EXIT
  git clone --quiet "$UPSTREAM" "$TEMP"
  git -C "$TEMP" checkout --quiet --detach "$PIN"
  ACTUAL="$(git -C "$TEMP" hash-object src/cpu_depth_packet_processor.cpp)"
  if [[ "$ACTUAL" != "$UPSTREAM_CPU" ||
        ! -f "$TEMP/include/libfreenect2/libfreenect2.hpp" ]]; then
    echo "Downloaded upstream did not match expected headers/sources." >&2
    exit 2
  fi
  git -C "$TEMP" apply --check "$PATCH"
  git -C "$TEMP" apply "$PATCH"
  if [[ "$(git -C "$TEMP" hash-object src/cpu_depth_packet_processor.cpp)" != "$PATCHED_CPU" ]]; then
    echo "Unexpected patched source hash; aborting." >&2
    exit 2
  fi
  mv -- "$TEMP" "$DEST"
  TEMP=""
fi

if [[ "$(git -C "$DEST" hash-object src/cpu_depth_packet_processor.cpp)" != "$PATCHED_CPU" ]]; then
  echo "CPU OpenMP patch verification failed." >&2
  exit 2
fi
echo "Restored pinned upstream source + verified OpenMP patch: $DEST"

if [[ "$SOURCE_ONLY" == true ]]; then
  echo "Source-only mode: no compilation or hardware access."
  exit 0
fi

for tool in cmake ninja; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing build dependency: $tool" >&2
    exit 2
  fi
done

# Explicit CPU-only baseline. No -march=native and no mandatory dedicated GPU.
# Older upstream CMake still needs explicit CMake-4 policy compatibility.
cmake -S "$DEST" -B "$DEST/build-omp" -G Ninja \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_OPENNI2_DRIVER=OFF \
  -DENABLE_OPENCL=OFF \
  -DENABLE_OPENGL=OFF \
  -DENABLE_CUDA=OFF \
  -DENABLE_VAAPI=OFF \
  -DENABLE_TEGRAJPEG=OFF \
  -DCMAKE_CXX_FLAGS="-fopenmp" \
  -DCMAKE_SHARED_LINKER_FLAGS="-fopenmp"
cmake --build "$DEST/build-omp" --parallel "${KINECT2_BUILD_JOBS:-4}"
if [[ ! -f "$DEST/build-omp/lib/libfreenect2.so" ]]; then
  echo "libfreenect2.so not found after build; check upstream CMake output." >&2
  exit 1
fi
echo "Built local OpenMP library: $DEST/build-omp/lib/libfreenect2.so"
echo "Next: bash tools/build_broker.sh --with-hardware"
