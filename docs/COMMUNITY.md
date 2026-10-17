# Join Kinect2-Linux / Dołącz do Kinect2-Linux

Kinect2-Linux is a community-driven, unofficial **MIT-licensed Linux project
for Microsoft Kinect v2**. We are working toward a useful, easy-to-install
version 1.0 with one C++ USB broker, independent native RGB/IR/Depth clients
and optional system webcam compatibility (V4L2). We welcome feedback,
testing, documentation and focused pull requests — not just code!

**Release status:** this is **work in progress**, not a finished 1.0 SDK.
The project is not affiliated with Microsoft or OpenKinect.

## What's already working / Co już działa

- Native Kinect v2 RGB 1920×1080, IR and Depth 512×424 (libfreenect2,
  with a pinned-source OpenMP patch) tested on **one physical device on Arch
  Linux**; observed 30 FPS per stream under adequate lighting.
- A C++ broker with one physical USB owner can send raw frames to multiple
  independent Python viewers over a private Unix socket + sealed memfd.
  Automatic capture lifecycle and 2 RGB + 2 IR client support are now on `main`.
- **Broker-owned** RGB output `/dev/video11` works in Firefox concurrently
  with two SDK RGB and two IR clients on one tested Arch Linux/KDE computer.
  The legacy standalone RGB bridge remains available for rollback, but must
  not run alongside broker-owned V4L2. Native ALSA microphones remain separate.

**Recently merged:**
- [PR #15](https://github.com/KacperPiotrowski/Kinect2Linux/pull/15):
  automatic subscription-driven sensor capture and idle USB release.
- [PR #20](https://github.com/KacperPiotrowski/Kinect2Linux/pull/20):
  optional, in-process V4L2 RGB output. Firefox + 4 SDK clients and
  KDE login after reboot were smoke-tested on one physical Kinect.

**In progress:**
- [Issue #12](https://github.com/KacperPiotrowski/Kinect2Linux/issues/12):
  clean-clone installation, release-quality acceptance and contributor docs.
- Community packaging, multi-distribution tests and an opt-in installer.

The final installer and cross-distribution compatibility still need work.
No body-tracking, MediaPipe, Howdy/PAM integration or GPU acceleration
is required for the core release.

## How you can contribute / Jak pomóc

**Have a Kinect v2? / Masz Kinect v2?**
- Verify compatibility on Fedora, Debian, Ubuntu, openSUSE or other Linux
  distributions; include distribution, kernel, compiler, CPU and USB setup.
- Compare RGB/IR/Depth FPS and dropped sensor sequence counts, especially
  under different lighting. Do not confuse GUI FPS with broker sensor FPS.
- Check that a local client can close without terminating other viewers,
  and that the sensor releases USB after the last client leaves.

**No Kinect? / Nie masz Kinecta?**
- Improve the English documentation, package/dependency guidance and
  hardware-free setup, or add isolated, deterministic offline tests.
- Help improve sample clients and error messages without changing the
  wire format or introducing new USB-owning processes.
- Start with issues tagged `good first issue` or `help wanted`.

### Workflow

1. Browse [Issues](https://github.com/KacperPiotrowski/Kinect2Linux/issues)
   and comment with what you can test or implement.
2. For changes, fork the repository and open a small, focused pull request.
   Use [CONTRIBUTING.md](../CONTRIBUTING.md) and run the available offline
   tests. CI cannot replace real Kinect tests.
3. For failures, include minimal reproduction steps, expected/actual result,
   versions and redacted logs. Never publish sensor serials, usernames,
   personal paths, biometric data, face images or raw audio recordings.
4. Maintainers review and **manually** decide on merge after applicable
   offline and physical hardware tests. Larger ideas should begin in an issue.

### Running tests without Kinect

On Linux, with build dependencies installed (CMake, Ninja, C++ compiler,
`nlohmann-json`, Python and requirements in `requirements-test.txt`):

```bash
bash tools/build_broker.sh           # hardware-free build
./bin/test_frame_hub                 # synthetic RGB / IR delivery
python3 -m unittest discover -s tests -v
python3 tools/check_public_tree.py
```

Avoid starting real USB capture while the system's standalone V4L2
webcam service is actively using the same Kinect.

## Share the project / Powiedz innym

When posting about the project, please link to the GitHub repository
and describe the current prototype accurately rather than calling it
a complete Kinect driver or a finished plug-and-play 1.0 release.
Real benchmark numbers should include CPU, streams, lighting and test
conditions. Communities interested in Linux hardware, open-source
device drivers, robotics and computer vision are especially relevant.

Repository: https://github.com/KacperPiotrowski/Kinect2Linux

### Short English invitation

> **Working on Kinect v2 support for Linux — looking for testers and contributors**
>
> Kinect2-Linux is an open-source, MIT-licensed project bringing native
> RGB, IR and Depth data from Kinect v2 to Linux. The current experimental
> C++ broker has demonstrated Firefox plus four independent Python viewers
> (2 RGB + 2 IR) through one USB broker on Arch Linux. We're working
> toward a safe, reproducible installer and wider Linux testing.
>
> It's not 1.0 yet. If you have a Kinect v2, use another Linux distro,
> or enjoy C++/Python/documentation work, feedback and small PRs are
> very welcome! https://github.com/KacperPiotrowski/Kinect2Linux

### Krótkie polskie zaproszenie

> **Kinect v2 na Linuksie — szukamy testerów i współtwórców!**
>
> Kinect2-Linux to nieoficjalny projekt open source (MIT) umożliwiający
> korzystanie z natywnego RGB, IR i Depth. Jeden broker C++ potrafi już
> przekazywać klatki do czterech niezależnych okien Pythona, bez
> wielokrotnego otwierania USB. Firefox i cztery okna
> SDK mogą już współdzielić Kinecta na testowanym Arch Linuksie;
> następny krok to prosty instalator i testy na innych dystrybucjach.
>
> To wciąż prototyp, nie gotowe 1.0. Masz Kinect v2, inny Linux,
> pomysł na test albo chcesz pomóc przy kodzie lub dokumentacji?
> Zapraszamy! https://github.com/KacperPiotrowski/Kinect2Linux
