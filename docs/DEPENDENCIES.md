# Zależności i opcjonalne integracje

Projekt nie pobiera zewnętrznych bibliotek automatycznie. Nie deklarujemy, że każde wydanie każdej zależności będzie działało bez testu na sprzęcie.

| Komponent | Potrzebny do | Uwagi |
| --- | --- | --- |
| Linux + Kinect v2 z USB 3.0 / zasilaczem | Wszystko poza testami offline | Nie Kinect v1 |
| `libfreenect2-omp` (lokalny fork/build) + `g++` | Mosty C++ IR/RGB/Depth/Face3D | Oczekiwana biblioteka `../libfreenect2-omp/build-omp/lib/libfreenect2.so`; ewentualnie `LIBFREENECT2_DIR` |
| `v4l2loopback` + `v4l2loopback-ctl` | Wirtualne kamery `/dev/video10` i `/dev/video11` | Moduł zgodny z uruchomionym kernelem; dla RGB potrzebna obsługa eventów użytkowania |
| util-linux (`flock`), systemd user services | Blokada sensora i RGB on-demand | Obecny model użytkowy (Arch/KDE) |
| Python 3 + NumPy + OpenCV | Podgląd, testy Face3D, testy offline | Testy na CI instalują headless OpenCV |
| dlib, Howdy | Eksperymenty twarzy i rejestracji | Opcjonalne; **nie** są częścią podstawowego SDK; bez PAM |
| ALSA (`arecord`) | Natywny test audio 4ch | Bez wymogu PipeWire/EasyEffects |
| MediaPipe, Pillow i model `.task` | Wstrzymany, offline eksperyment | Nie należy instalować dla podstawowego Kinect SDK |

Wersje i sposób budowania lokalnego `libfreenect2-omp` muszą zostać opisane w osobnej instrukcji przenośnego builda przed pierwszym wydaniem. Aktualne launchery korzystają z lokalnego builda i nie obiecują gotowego plug-and-play.
