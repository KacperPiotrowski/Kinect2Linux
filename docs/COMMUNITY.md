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
  The 2 RGB + 2 IR demo and offline transport tests are already on `main`.
- Legacy standalone RGB webcam output `/dev/video11` is usable in Firefox
  when the standalone bridge owns the Kinect (not when the broker owns it).
  Native ALSA microphones remain separate.

**In progress:**
- [PR #15](https://github.com/KacperPiotrowski/Kinect2Linux/pull/15):
  automatic subscription-driven sensor capture and resilience to temporary
  missing frames; **Draft, not merged yet**.
- [Issue #16](https://github.com/KacperPiotrowski/Kinect2Linux/issues/16):
  one broker user service with an in-process V4L2 adapter, so browser and
  SDK clients can coexist without opening USB twice.
- [Issue #12](https://github.com/KacperPiotrowski/Kinect2Linux/issues/12):
  clean-clone install, API documentation and release acceptance testing.

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
> C++ broker already streams real frames to four independent Python
> viewers (2 RGB + 2 IR) through one USB connection. We're working
> toward one systemd user service, V4L2 webcam compatibility and an
> easy-to-install SDK.
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
> wielokrotnego otwierania USB. Następne kroki to integracja V4L2 dla
> Firefoksa, usługa systemd i prosty instalator.
>
> To wciąż prototyp, nie gotowe 1.0. Masz Kinect v2, inny Linux,
> pomysł na test albo chcesz pomóc przy kodzie lub dokumentacji?
> Zapraszamy! https://github.com/KacperPiotrowski/Kinect2Linux
