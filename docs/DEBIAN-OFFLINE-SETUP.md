# Debian / Ubuntu: offline broker build (no Kinect required)

This guide builds **only the hardware-free broker** and runs synthetic tests.
It does not open USB, create /dev/video* devices, load kernel modules or
enable systemd units. There is no reason to run these commands with sudo,
except for the explicit package installation step.

**Validation status:** Ubuntu 24.04.5 LTS was tested independently by a
community contributor (Intel i7-10875H, kernel 6.8.0-51, g++ 13.3.0,
Python 3.12.3); installer and V4L2 bugs are tracked in issues #40–#45.
The complete command sequence below has **not yet been verified end-to-end
on a clean Ubuntu machine**. Please report results and sanitized logs in #18.

## Dependencies

Example for Ubuntu 24.04 and compatible Debian releases (package versions
can differ):

```bash
sudo apt update
sudo apt install --no-install-recommends \
  git build-essential cmake ninja-build pkg-config python3 \
  libusb-1.0-0-dev libturbojpeg0-dev nlohmann-json3-dev
```

C++23-capable `g++` is required; test with `g++ -std=c++23`. The offline
broker uses CMake + Ninja and `nlohmann/json.hpp`. TurboJPEG and libusb
development headers are additionally required for the hardware-capable build;
they are installed here so the installer's preflight can also pass.

## Clone and test with NO Kinect attached

```bash
git clone https://github.com/KacperPiotrowski/Kinect2Linux.git
cd Kinect2Linux
bash tools/build_broker.sh
./bin/test_frame_hub
python3 -m unittest discover -s tests -v
python3 tools/check_public_tree.py
```

Python tests may need optional packages from `requirements-test.txt`;
use a Python virtual environment before installing them. Graphical preview
and real RGB/IR/Depth capture are not exercised by this offline process.

The hardware broker `bash tools/build_broker.sh --with-hardware`, USB power
and permissions, runtime service activation, and V4L2 virtual camera setup
are **out of scope** for this guide.

## Troubleshooting

- `cmake` or `ninja` found but won't run: check `command -v cmake`,
  `cmake --version` and `ninja --version`; a stale `~/.local/bin` pip shim
  can shadow working `/usr/bin` tools (#40).
- Missing `nlohmann/json.hpp`: install `nlohmann-json3-dev` (#41).
- Missing `turbojpeg.h`: install `libturbojpeg0-dev`; missing libusb headers:
  install `libusb-1.0-0-dev` (#41).
- Default Ubuntu 24.04 `v4l2loopback` 0.12.7 has a **distribution
  backport** of CLIENT_USAGE with a legacy event ID. The new broker tries
  both upstream and Ubuntu event IDs; run `bin/kinect2-v4l2-probe --probe`
  after creating the named device and before enabling the broker. Do not
  rely on the version number alone. The older `v4l2loopback-ctl` lacks
  dynamic `add`, so the root device setup creates both cameras with a
  single module load when initially unloaded. The offline broker does
  **not** require v4l2loopback (#42, #44).
- If `modprobe` is missing on Ubuntu, install `kmod`; on Debian/Ubuntu it
  is normally under `/usr/sbin/modprobe`, not `/usr/bin/modprobe` (#43).

For hardware setup, see [INSTALL.md](INSTALL.md); maintainers should test
changes on Arch as well as Ubuntu before claiming full distribution support.
