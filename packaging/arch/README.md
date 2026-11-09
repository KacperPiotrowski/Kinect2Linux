# Experimental Arch Linux AUR packaging

The `PKGBUILD` here is a **draft, not a published AUR package**. It builds
the hardware-enabled broker, the experimental Python client SDK, and a
**private, pinned and SHA-verified OpenMP-patched libfreenect2**. The shared
library is installed under `/usr/lib/kinect2linux`, not over the system's
libfreenect2. It packages no Kinect SDK 2.0 (Microsoft) binaries or models.

The binary package also includes the original `libfreenect2` `APACHE20`,
`GPL2` and `CONTRIB` notices under `/usr/share/doc/kinect2linux/libfreenect2/`.
This is a necessary packaging improvement, **not** a completed legal review.

The build is intentionally CPU-only. It does **not** install or load kernel
modules, write udev rules, enable webcam mode, configure audio, open USB,
start services, or overwrite files in `~/.config`.

## Local validation on Arch x86_64

From the repository root:

```bash
cd packaging/arch
bash -n PKGBUILD kinect2-broker-run
makepkg --printsrcinfo > .SRCINFO
makepkg --cleanbuild --syncdeps --check
```

**Inspect the PKGBUILD and dependencies before running makepkg.** The
`--syncdeps` option uses pacman to install missing build dependencies;
it can request privileged authentication. For strict isolation, validate
in an Arch clean chroot using `devtools`. Never run `makepkg` as root.
The recipe requires network access to fetch two Git sources (Kinect2Linux
and pinned OpenKinect/libfreenect2), so offline compilation from an empty
source cache is not supported. `.SRCINFO` is generated locally before AUR
publication; do not hand-write guessed metadata.

The package is a new, alternate way to install the project; it does not
migrate existing manually built installations. Inspect and reconcile any
pre-existing user broker unit before enabling the packaged service:

```bash
systemctl --user cat kinect2-broker.service
systemctl --user status kinect2-broker.service
```

If you deliberately want to use the packaged systemd user unit:

```bash
systemctl --user enable --now kinect2-broker.service
```

This starts a user-session service with USB **idle** until a client subscribes,
assuming USB permissions and the Kinect hardware work. The packaged unit
resides in `/usr/lib/systemd/user/`. Existing
`~/.config/systemd/user/kinect2-broker.service` takes precedence and must
be reviewed manually; package installation never changes or deletes it.

Python control API example:

```bash
python -c 'from kinect2_linux import BrokerClient; print(BrokerClient().get_status())'
```

No automatic virtual camera setup is included. Optional `/dev/video11`
integration requires a compatible host `v4l2loopback` and separately
configured device, plus a conscious `KINECT2_BROKER_V4L2=1` opt-in.
**Do not activate webcam mode** until compatibility and conflicts with
`kinect2-rgb-webcam.service` are checked; in particular Ubuntu's 0.12.x
driver is not automatically compatible with the current broker.

To stop without affecting any other service:

```bash
systemctl --user disable --now kinect2-broker.service
```

## AUR submission checklist (separate from this GitHub PR)

1. Verify `kinect2linux-git` does not already exist in AUR or official repos.
2. Validate on a clean Arch system, including native tests, `readelf`/`ldd`
   for the private `libfreenect2.so` and an opt-in real Kinect test.
3. Run `namcap` on the source package and built package and fix warnings.
4. Add a real AUR maintainer identity to `PKGBUILD`, generate `.SRCINFO`
   with `makepkg --printsrcinfo`, then review changes.
5. Publish `PKGBUILD`, `.SRCINFO` and licensing notes through your own
   AUR SSH-authenticated account. Do not upload built binaries to AUR.

The Debian/Ubuntu and RPM packaging tracks will follow once the install
layout and Linux runtime library paths pass tests on Arch.
