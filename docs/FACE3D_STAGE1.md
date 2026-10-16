# Kinect2-Linux — Face3D Stage 1

**Experimental preview. Not biometric authentication.**

This add-on adds only three files to the existing Kinect2-Linux project:
`face3d`, `src/kinect_face3d_stream.cpp`, `face/live3d.py`.
It does **not** replace the working Kinect bridge, edit Howdy, create a daemon,
change PAM, or write face scans to disk.

## Installation

Extract archive from within `~/Projekty/kinect/Kinect2-Linux`, preserving paths.

```bash
cd ~/Projekty/kinect/Kinect2-Linux
chmod +x face3d
./face3d
```

Requirements: existing `../libfreenect2-omp/build-omp`, `g++`, `python3`,
`numpy`, `opencv-python` (`python-opencv` on Arch), optional `dlib`.
Build on the first run is automatic. Later: `./face3d build` for explicit rebuild.

**Stop `./kinect2 run` before launching `./face3d`.** Both commands use the
same `kinect2-sensor.lock` advisory lock. The sensor is opened only by the
C++ subprocess. No `/dev/video10` or virtual camera is needed.

- Left pane: live infrared, 8-bit **display only**.
- Right pane: synchronized Depth in false color; black indicates no valid depth.
- Face rectangle: detection (not recognition).
- `Z`: median axial distance in the center of a detected face rectangle,
  in millimeters. `valid`: fraction of valid depth pixels inside that ROI.
- Both sensor planes travel through the pipe as full `float32` data.
- GUI/capture and detector run independently; old frames are discarded.

Exit through **Q** or **Esc** in the window, or **Ctrl+C** in the terminal.
The Python launcher terminates the sensor subprocess and releases Kinect.

## Known limits

This is a **single-camera, no-authentication** research stage. It does not
perform identity matching, real head pose, 3D facial matching, or reliable
presentation-attack/liveness detection. The face rectangle may include
background; a Depth median alone is not proof of a live person. IR/Depth
pixel correspondence uses the common depth sensor geometry, not RGB
registration or high-precision biometric calibration.

Real face enrollment with automatic rotation checking and an independent
security review come next, before any PAM integration. Keep password sign-in.
