#!/usr/bin/env bash
# Shared path selection for legacy RGB / IR / Depth / Face3D launchers.
# Caller must define ROOT (absolute Kinect2Linux repository path) before sourcing.
# Never downloads sources, compiles dependencies or opens the USB device.
kinect2_libfreenect2_dir() {
  local repo_root="${1:?expected repo root}" selected
  if [[ -n "${LIBFREENECT2_DIR:-}" ]]; then
    selected="$LIBFREENECT2_DIR"
  elif [[ -f "$repo_root/third_party/libfreenect2-omp/include/libfreenect2/libfreenect2.hpp" ]]; then
    selected="$repo_root/third_party/libfreenect2-omp"
  else
    selected="$repo_root/../libfreenect2-omp"
  fi
  readlink -f -- "$selected"
}
