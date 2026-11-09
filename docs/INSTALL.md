# Kinect2-Linux — guided installer (experimental Linux)

**Status:** first installer prototype; hardware-smoke-tested broker on one Arch
Linux/KDE machine, **not** a general-purpose 1.0 installer. Ubuntu 24.04.5
community testing reported issues #40–#45; a clean end-to-end Ubuntu installation
is not yet validated. Run commands from the project root, as your
normal user unless explicitly noted. Audio ALSA remains separate. No MediaPipe
or face recognition is required.

## 1. Safe preflight

~~~bash
bash tools/install_kinect2.sh --check
~~~

Read-only checks for Git, compiler, CMake, Ninja, pkg-config, systemd,
v4l2loopback utilities, the named /dev/video11 and whether two conflicting
RGB services are active/enabled. This command never opens USB or changes a
service. On Arch, typical build packages are:

~~~bash
sudo pacman -S --needed git gcc cmake ninja pkgconf libusb libjpeg-turbo nlohmann-json
~~~

This is a **manual example**, not a command the installer runs.

For Ubuntu 24.04, install build dependencies manually:
~~~bash
sudo apt install git build-essential cmake ninja-build pkg-config python3 \
  libusb-1.0-0-dev libturbojpeg0-dev nlohmann-json3-dev
~~~
The preflight checks whether CMake/Ninja execute, the compiler supports a
basic C++23 source, and the required development headers are available.
For a hardware-free build and offline tests, see
[DEBIAN-OFFLINE-SETUP.md](DEBIAN-OFFLINE-SETUP.md).

For the RGB webcam you also need a v4l2loopback kernel module matching your
kernel and v4l2loopback-ctl utilities (packages vary with kernel/repository).
**The broker V4L2 integration requires working CLIENT_USAGE events**, not
a particular version string. Upstream v4l2loopback >= 0.13 uses the newer
private event ID. Ubuntu 24.04 backports CLIENT_USAGE to some 0.12.7
packages, using a legacy event ID; stock upstream 0.12 does not provide
that event. The broker now tries both IDs and refuses to activate unless
the kernel actually accepts the subscription.

Inspect the module version without writing anything:
~~~bash
bash webcam/check-loopback.sh --installed
bash webcam/check-loopback.sh --loaded
~~~
The version check is **advisory only**. After building the broker and setting
up the RGB virtual device, test the real feature without opening Kinect USB:
~~~bash
bin/kinect2-v4l2-probe --probe
~~~
This briefly opens /dev/video11 as a V4L2 read-only client and subscribes
to both supported event IDs. It can trigger an existing on-demand producer,
so stop the legacy webcam service before probing. Do not infer compatibility
from a module version alone. The installer never installs or upgrades
kernel modules. The Kinect needs working power, USB 3.0 and
**normal-user USB permissions**.
The installer intentionally does not create generic/insecure udev rules or
modify your device ACLs. Review your distribution's USB permissions first.

## 2. Prepare the reproducible build (no privileged operations)

~~~bash
bash tools/install_kinect2.sh --prepare
~~~

This fetches the pinned official libfreenect2 source, verifies the reviewed
OpenMP patch by source hash, builds libfreenect2 and the hardware broker,
runs native automatic-subscription and V4L2 conversion tests, then
registers an opt-in user service. It **does not enable or start** the
service, replace unrelated user units, install packages or use sudo.
It refuses to modify the user unit if the broker is already active.

For an absent /dev/video11, review webcam/install-device.sh and
webcam/device-onboot.sh first. The single, separate privileged system
setup is explicitly selected by you:

~~~bash
sudo bash webcam/install-device.sh
~~~

This prepares **both** named virtual cameras and installs the
`kinect2-rgb-device.service` one-shot unit, without touching Kinect USB.
When v4l2loopback is not loaded, it creates IR /dev/video10 and RGB
/dev/video11 together with one `modprobe devices=2 video_nr=10,11`.
This works with Ubuntu's 0.12.7 even though its `v4l2loopback-ctl` has
no dynamic `add` command. When the module is **already loaded**, the
script preserves IR /dev/video10 and adds RGB only if the installed
`v4l2loopback-ctl` supports `add`. Otherwise it refuses and explains
manual recovery, rather than leaving a half-configured persistent service.

**Never unload v4l2loopback while applications still use it.** If a
pre-existing module has only IR and lacks dynamic `add`, close all clients,
identify any other applications using it, then (only when safe) manually
run `sudo modprobe -r v4l2loopback` and repeat the device setup. The
installer never unloads modules or replaces foreign nodes.

## 3. Opt in to the ONE V4L2-owning broker

Close Firefox/OBS/SDK video tabs first. A separate legacy bridge and the
broker cannot both be producers on /dev/video11. Inspect:

~~~bash
systemctl --user is-active kinect2-rgb-webcam.service
systemctl --user is-enabled kinect2-rgb-webcam.service
~~~

If you want to replace the legacy producer, **you** must make the explicit
decision and execute (the installer never does this):

~~~bash
systemctl --user disable --now kinect2-rgb-webcam.service
bash tools/install_kinect2.sh --activate
~~~

Activation verifies the hardware broker binary, a managed user unit,
the exact name of /dev/video11, and the old bridge's disabled/stopped
state. It refuses conflicting configuration and never restarts an already
active broker, which might be serving other applications. It uses the
`kinect2-v4l2-probe` capability test **before writing any new drop-in
or enabling autostart**. This probe supports upstream and Ubuntu-backported
client usage events. It then writes the opt-in KINECT2_BROKER_V4L2=1
systemd drop-in and enables the user broker. It checks that the service
remains active shortly after startup. If it exits, the installer disables
autostart and removes the drop-in only if it just created that exact file.
It never overwrites or deletes an unrelated user configuration.
The user unit starts upon login, **not before login**, and should not
hold USB while there are no camera clients.

## 4. Verify after activation / restart

~~~bash
systemctl --user is-active kinect2-broker.service
systemctl --user is-active kinect2-rgb-webcam.service
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient
s = BrokerClient().get_status()
print('V4L2:', s['v4l2_rgb'])
print('USB:', s['sensor_open'])
print('SDK:', s['frame_preview'])
PY
~~~

Idle expectation: active broker, inactive legacy RGB, V4L2 ready=True,
streaming_clients=0, sensor_open=False. Next: open Firefox camera
Kinect v2 RGB, then run four independent viewers:

~~~bash
python3 tools/demo_four_clients.py
~~~

The demo requires NumPy and an OpenCV build with GUI support. All five
should show live images without a competing USB owner. On an error, inspect:

~~~bash
journalctl --user -u kinect2-broker.service -n 50 --no-pager
~~~

Never delete Unix sockets or USB lockfiles to resolve a device_busy state.

## Rollback (does not uninstall or delete the device)

Close all video clients. Disable the broker, then disable the experiment
drop-in **if it was created by this setup**:

~~~bash
systemctl --user disable --now kinect2-broker.service
mv ~/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf \
   ~/.config/systemd/user/kinect2-broker.service.d/50-v4l2-experimental.conf.disabled
systemctl --user daemon-reload
~~~

If you previously used the legacy producer, you may then explicitly
re-enable it with:

~~~bash
systemctl --user enable --now kinect2-rgb-webcam.service
~~~

Do **not** enable both producers. These rollback commands do not remove
the device service, alter USB ACLs or uninstall compiled artifacts.

## Known gaps and contributor opportunities

- Repeat the install from a truly clean clone and test on a second machine.
- Recheck Ubuntu issues #40–#45 with the stock Ubuntu 24.04 v4l2loopback
  first; capability testing (both event IDs), correctly named IR/RGB devices
  and clean service activation are required. A module upgrade is only a
  fallback if the actual feature probe fails.
- Validate USB permissions/udev guidance, kernel-module packaging and recovery
  across Linux distributions; no automatic distro package installation yet.
- Long-running memory/CPU stability, USB hot-unplug/replug, restart during
  capture and independent privacy-black tests remain release gates.
- The experimental Python FrameClient exists, but a polished public pip SDK
  and body/face tracking are optional community work, not installer blockers.
- Share **sanitized** logs only: never publish sensor serial numbers, private
  paths, identifiable face images, calibration files or recorded speech.
