#!/usr/bin/env bash
# Experimental binary .deb builder, not an official Debian source package.
# Does not install software on the host, use sudo, enable services or open USB.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
die() { printf 'Kinect2Linux DEB: %s\n' "$*" >&2; exit 2; }

for cmd in git tar cmake ninja c++ dpkg dpkg-deb dpkg-shlibdeps \
           install python3; do
  command -v "$cmd" >/dev/null 2>&1 || die "Missing build tool: $cmd"
done

[[ $(dpkg --print-architecture) == amd64 ]] ||
  die 'This initial package is amd64 only; ARM64 needs its own compilation and tests.'
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null ||
  die 'Build from a Git checkout; the checked-in commit is the package source.'

revision=$(git -C "$ROOT" rev-list --count HEAD)
sha=$(git -C "$ROOT" rev-parse --short=8 HEAD)
version="${KINECT2_DEB_VERSION:-0.0~git${revision}.${sha}-1}"
dpkg --validate-version "$version" >/dev/null 2>&1 ||
  die "Invalid Debian version: $version"
maintainer="${KINECT2_DEB_MAINTAINER:?Set KINECT2_DEB_MAINTAINER to a real package maintainer before building.}"
out="${KINECT2_DEB_OUT:-$ROOT/dist}"
mkdir -p -- "$out"
out=$(realpath "$out")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/src" "$work/debian/kinect2linux/DEBIAN"
# Work only on an isolated export; never modify the user's existing clone.
git -C "$ROOT" archive HEAD | tar -xf - -C "$work/src"

src="$work/src"
stage="$work/debian/kinect2linux"
export KINECT2_BUILD_JOBS="${KINECT2_BUILD_JOBS:-2}"
bash "$src/tools/bootstrap_libfreenect2_omp.sh"
cmake -S "$src" -B "$work/broker-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DKINECT2_ENABLE_HARDWARE=ON \
  -DKINECT2_PYTHON_INSTALL_DIR=lib/python3/dist-packages \
  -DLIBFREENECT2_DIR="$src/third_party/libfreenect2-omp"
cmake --build "$work/broker-build" --parallel "$KINECT2_BUILD_JOBS"
ctest --test-dir "$work/broker-build" --output-on-failure

# The single CMake install manifest owns binaries, private lib, SDK and unit.
# DESTDIR stages files into the temporary package root without touching /usr.
DESTDIR="$stage" cmake --install "$work/broker-build" --prefix /usr

install -Dm644 "$src/LICENSE" \
  "$stage/usr/share/doc/kinect2linux/copyright"
install -Dm644 "$src/THIRD_PARTY.md" \
  "$stage/usr/share/doc/kinect2linux/THIRD_PARTY.md"
install -Dm644 "$src/packaging/debian/README.md" \
  "$stage/usr/share/doc/kinect2linux/DEBIAN-README.md"

# Required metadata so dpkg-shlibdeps can resolve bundled private library
# without treating it as an external dependency.
cat > "$work/debian/control" <<EOF
Source: kinect2linux
Section: utils
Priority: optional
Maintainer: $maintainer
Standards-Version: 4.7.0

Package: kinect2linux
Architecture: amd64
Description: Kinect v2 experimental Linux sensor broker and Python client SDK
EOF
printf 'libfreenect2 0.2 kinect2linux (= %s)\n' "$version" \
  > "$work/debian/shlibs.local"

(
  cd "$work"
  # Discover actual runtime library requirements from the built ELF objects.
  # The private libfreenect2 remains inside this same binary package.
  dpkg-shlibdeps -O \
    -l"$stage/usr/lib/kinect2linux" \
    -xkinect2linux \
    -e"$stage/usr/bin/kinect2-broker-hw" \
    -e"$stage/usr/bin/kinect2-worker" \
    -e"$stage/usr/lib/kinect2linux/libfreenect2.so.0.2.0" \
    > "$work/shlibs-output"
)
shlibs=$(sed -n 's/^shlibs:Depends=//p' "$work/shlibs-output")
[[ -n "$shlibs" ]] || die 'Cannot determine runtime Depends with dpkg-shlibdeps.'
cat > "$stage/DEBIAN/control" <<EOF
Package: kinect2linux
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: $maintainer
Depends: python3 (>= 3.10), $shlibs
Recommends: systemd
Suggests: v4l2loopback-dkms, v4l2loopback-utils
Description: Experimental Kinect v2 Linux RGB/IR/Depth USB broker
 An opt-in Kinect v2 single USB owner with Python SDK and a privately
 patched libfreenect2. No webcam kernel modules, udev changes, services
 or USB access are enabled by installing this binary package.
EOF
chmod 0644 "$stage/DEBIAN/control"
output="$out/kinect2linux_${version}_amd64.deb"
dpkg-deb --root-owner-group --build "$stage" "$output"
dpkg-deb --field "$output" Package Version Architecture Depends
echo "Built: $output"
echo "No host package installation, service activation or USB access performed."
