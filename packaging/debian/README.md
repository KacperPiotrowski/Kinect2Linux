# Experimental Debian/Ubuntu binary package

This directory builds a **developer-testing .deb** for **amd64** using
`dpkg-deb` and `dpkg-shlibdeps`. It is NOT an official Debian source package
and is not yet published to any APT repository.

The recipe is modeled on the Arch AUR pilot and contains:
- a hardware-capable native C++ broker and worker
- a pinned OpenKinect/libfreenect2 build, with the reviewed CPU OpenMP patch
- Python control/frames SDK in `/usr/lib/python3/dist-packages`
- a systemd **user** service which is NEVER enabled by installation
- a private `/usr/lib/kinect2linux/libfreenect2.so.*` library

No Microsoft Kinect SDK 2.0 binaries, model files, kernel drivers or USB device
rules are included. The builder uses a temporary Git-archive copy of the
current commit, builds and tests without touching the existing checkout,
then puts the binary .deb under `dist/`. The build **fetches OpenKinect over
the network**. It requires a C++23 compiler, git, cmake, ninja,
dpkg-dev, the TurboJPEG and libusb development packages, and JSON headers.

For Ubuntu 24.04 container smoke testing, use the CI workflow in
`.github/workflows/deb-package.yml`. On a Debian/Ubuntu development host:

```bash
sudo apt update
sudo apt install --no-install-recommends \
  build-essential git ca-certificates cmake ninja-build pkg-config \
  dpkg-dev python3 libusb-1.0-0-dev libturbojpeg0-dev \
  nlohmann-json3-dev
# From a Git checkout at the branch/commit being tested:
KINECT2_DEB_MAINTAINER='Your Name <you@example.org>' \
  bash packaging/debian/build-deb.sh
dpkg-deb --info dist/kinect2linux_*.deb
dpkg-deb --contents dist/kinect2linux_*.deb
```

The example maintainer field above is a **placeholder**. Replace it before
distribution. Never install the developer package alongside an active broker
until the existing user unit, installed file paths and USB ownership have been
checked. An existing `~/.config/systemd/user/kinect2-broker.service` wins
over the packaged `/usr/lib/systemd/user/` unit.

The optional V4L2 webcam remains **disabled**. Ubuntu 24.04 default
`v4l2loopback` and userspace tools may not support the broker's interface.
No claim of Ubuntu webcam compatibility follows from a successful .deb test.

Scope is currently amd64 Ubuntu 24.04 only; Debian 12/13 and ARM64 must each
pass their own builds, runtime checks and hardware tests. Before any official
repository release, switch to a Debian source package using debhelper, review
third-party licensing and ensure runtime dependencies are fully policy-compliant.
