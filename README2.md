# Kinect2-Linux — Spatial / stage 1

Single Kinect v2 IR/Depth snapshot -> calibrated XYZ point cloud (`.ply`) plus sensor intrinsics (`.calibration.json`).

This is a **development tool**, not body tracking, face recognition, multi-Kinect synchronization or a security check.

## Install

Extract this ZIP into `~/Projekty/kinect/Kinect2-Linux` (files only added in `src/` and `tools/`). Existing source files need not be replaced.

## Compile

```sh
cd ~/Projekty/kinect/Kinect2-Linux
mkdir -p bin research-data
g++ -std=c++11 -O2 \
  -I../libfreenect2-omp/include -I../libfreenect2-omp/build-omp \
  src/kinect2_cloud.cpp \
  -L../libfreenect2-omp/build-omp/lib \
  -Wl,-rpath,"$PWD/../libfreenect2-omp/build-omp/lib" \
  -lfreenect2 -o bin/kinect2_cloud
```

## Capture

Stop any running Kinect bridge first. Use the SAME `flock` lock file as `./kinect2 run` and `./kinect2 depth`:

```sh
OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE \
  flock -n -F "${XDG_RUNTIME_DIR:-$PWD}/kinect2-sensor.lock" \
  ./bin/kinect2_cloud research-data/single-kinect.ply
```

Expected output files:
- `research-data/single-kinect.ply`: single point cloud with coordinates in metres, expressed in that sensor's local frame. Point colour is *artificial* greyscale based on depth, not RGB.
- `research-data/single-kinect.ply.calibration.json`: factory IR camera intrinsics + serial and a single-frame sequence/timestamp.

No RGB stream is needed; the tool performs lens correction with `libfreenect2::Registration`.

## Explore in 3D

Requires `python-opencv` and `python-numpy` (already used for earlier Kinect experiments):

```sh
python tools/kinect2_cloud_view.py research-data/single-kinect.ply
```

Yaw/Pitch/Zoom sliders rotate and zoom an *offline snapshot*. Press Q or Esc to exit. No Kinect is held open during viewing.

## Limitations / planned multi-sensor extension

- A single snapshot cannot be used to claim full 3D model completeness, depth accuracy, or immunity to spoofing.
- For fusion, every sensor will need its own calibration plus a measured rigid transform into the **shared** coordinate system. Serial number alone is not enough.
- Depth sequence numbers and timestamps from separate Kinect v2 devices are not automatically synchronized. Time association must be implemented and tested.
- A 4-Kinect setup usually needs separate USB3 host controllers, sufficient PCIe bandwidth and external power for each adapter.
- This tool does not send image data to Howdy/PAM.
- Point clouds containing people's faces/bodies can be sensitive. Keep them local; do not publish scans without explicit consent.

## Source testing status

C++ syntax checked against API-shaped stubs and published libfreenect2 signatures; Python syntax and PLY parser verified. Real Kinect integration must be tested on the user's machine.
