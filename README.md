# Kinect2-Linux

**Open source · Linux · Kinect v2 / Kinect for Windows v2**

Eksperymentalny zestaw narzędzi i zalążek SDK dla Microsoft Kinect v2. Cel: **proste uruchomienie** i **pełny dostęp do oryginalnych danych** RGB, IR, Depth i czterech mikrofonów. Żadne narzędzie zewnętrzne (EasyEffects, MediaPipe, Howdy) nie jest obowiązkowym elementem ścieżki przechwytywania. Projekt **nie jest jeszcze pełnym, plug-and-play SDK 2.0**; plan migracji jest w [docs/REBUILD-PLAN.md](docs/REBUILD-PLAN.md).

> Projekt społecznościowy, nieoficjalny; nie jest częścią Microsoft ani OpenKinect. Nie służy obecnie do bezpiecznej autoryzacji biometrycznej.

## Aktualny stan — 16 października 2026

| Funkcja | Stan i ograniczenia |
| --- | --- |
| Kinect v2 USB | Wykrywany przez diagnostykę |
| RGB | 1920×1080, YUYV, `/dev/video11`, most z aktywacją na żądanie; Firefox i przechwycenie klatki FFmpeg przetestowane; podgląd `ffplay` bywa czarny |
| IR | 512×424, `/dev/video10` przez V4L2; płynny podgląd potwierdzony przez testującego |
| Depth | 512×424, float32 w mm; test 120/120 par IR+Depth, bez luk sekwencji |
| Audio | Natywny odczyt ALSA: 4 kanały, 16 kHz, S32_LE; bez obowiązkowego downmixu |
| Python | Narzędzia diagnostyczne i prototypy; docelowe wysokopoziomowe SDK Python jest planowane, jeszcze niezaimplementowane |
| Jednoczesny dostęp przez jeden rdzeń | **Planowane**, nie zaimplementowane |
| Body/Face Tracking | Eksperymenty osobno, MediaPipe wstrzymane; brak stabilnego API |

Wyniki pochodzą z lokalnych testów na jednym sprzęcie, **nie** z oficjalnej certyfikacji. Szczegóły: [punkt odniesienia](docs/BASELINE-2026-10-16.md).

## Szybki start (obecny prototyp — Arch Linux)

Założenia: Kinect v2 z zasilaczem i USB 3.0; sąsiedni katalog `../libfreenect2-omp` z kompilacją `build-omp` i biblioteką `libfreenect2.so`; `v4l2loopback`, `python3`, `numpy`, `opencv` i narzędzie `flock` (z `util-linux`). Nie dostarczamy w tym repozytorium sterownika OpenKinect ani modułu jądra. Ścieżkę biblioteki można ustawić przez `LIBFREENECT2_DIR`.

```bash
./kinect2 status         # tylko diagnostyka: nie otwiera sensora
./kinect2 devices
./kinect2 clients
./kinect2 doctor
./kinect2 build          # most IR, jeśli istnieje libfreenect2-omp
```

### Odtwarzalny build libfreenect2-omp — eksperyment (PR #13)

Jeżeli nie masz lokalnych nagłówków `libfreenect2`, nie musisz ich
kopiować ręcznie. Na gałęzi eksperymentalnej PR #13 można pobrać
**przypięte źródła OpenKinect razem z `include/`** i nałożyć
zweryfikowaną poprawkę OpenMP z lokalnej wersji użytkownika:

```bash
bash tools/bootstrap_libfreenect2_omp.sh
bash tools/build_broker.sh --with-hardware
```

Pierwsze pobranie wymaga internetu, a kompilacja wymaga zależności
CMake/libusb/TurboJPEG; nie zmienia istniejącej kopii `../libfreenect2-omp`.
**To nie jest jeszcze ukończony instalator ani potwierdzony na sprzęcie
build.** Szczegóły: [docs/LIBFREENECT2-OMP-SETUP.md](docs/LIBFREENECT2-OMP-SETUP.md).

### IR i Depth

Zatrzymaj klientów RGB i inne programy otwierające fizyczny sensor przed uruchomieniem mostu IR — **jeden proces jest obecnie właścicielem USB**. Przy nieobecnym `/dev/video10` skonfiguruj `v4l2loopback` zgodnie z instrukcjami systemowymi. W pierwszym terminalu:

```bash
./kinect2 run
```

W drugim terminalu:

```bash
./kinect2 preview          # IR V4L2 + niezależna analiza twarzy
```

Po zakończeniu mostu (Ctrl+C) możesz wykonać test Depth:

```bash
./kinect2 depth 120
```

### RGB jako kamera systemowa

Instalacja urządzenia i usług **zmienia konfigurację systemu**. Wykonuj ją świadomie (nie jest potrzebna do poleceń `status/devices/clients`). Instrukcja: [docs/RGB-ON-DEMAND.md](docs/RGB-ON-DEMAND.md). Kod uruchomieniowy: `webcam/`. Samo wykrycie `/dev/video11` nie oznacza aktualnego przesyłania klatek.

### Mikrofony

Mikrofony ALSA działają niezależnie od mostu RGB. Przetwarzanie 4ch → mono/stereo to **opcjonalna**, jawna operacja po stronie klienta. Przykład odczytu natywnego i bezpiecznej analizy: [docs/AUDIO.md](docs/AUDIO.md).

## Eksperymentalne procesy potomne i build przyrostowy

Nowy broker (opcjonalnie) może sam uruchomić i nadzorować pomocniczy
proces bez USB. CMake + Ninja kompiluje osobno zmienione moduły.
Szczegóły i test offline: [CHILD-WORKERS.md](docs/CHILD-WORKERS.md).

**Uwaga do FPS:** pomiar RGB 30 FPS uzyskano przy mocniejszym
oświetleniu, natomiast w słabszym świetle automatyczna ekspozycja
korelowała z RGB 15 FPS. W obu warunkach IR i Depth osiągały
około 30 FPS; dane z jednego stanowiska nie są ogólną gwarancją.

## Dokumentacja i przykłady

- [Plan przebudowy](docs/REBUILD-PLAN.md) — architektura wspólnego rdzenia i IPC.
- [Status API](docs/STATUS.md) oraz [Live Status](docs/LIVE-STATUS.md) — odczyt bez otwierania USB.
- [RGB on-demand](docs/RGB-ON-DEMAND.md) — aktualna konfiguracja wirtualnej kamery.
- [Point Cloud](docs/POINT-CLOUD.md) — eksperyment z chmurą punktów (nie część głównej ścieżki).
- Narzędzia Pythona: `tools/kinect2_status.py`, `tools/audio_raw_analyze.py`, `face/preview.py`. Publiczne API Python powstanie w ramach przebudowy rdzenia.
- [Eksperymenty Face3D, Howdy, MediaPipe](docs/EXPERIMENTS.md) — opcjonalne, nie do uwierzytelniania.
- [Współtworzenie](CONTRIBUTING.md), [zależności](docs/DEPENDENCIES.md), [licencje](THIRD_PARTY.md).
- `docs/history/` zawiera **nieaktualne** instrukcje zachowane wyłącznie jako historia.

## Testy bez urządzenia

```bash
python3 -m unittest discover -s tests -v
bash -n kinect2 face3d webcam/*.sh
```

Zależności testowe Pythona są wyszczególnione w `requirements-test.txt`; do części testów potrzebne są NumPy i OpenCV.

Nie wszystkie testy integracyjne da się wykonać bez fizycznego Kinecta. Budowa i uruchomienie C++ wymagają sprawdzenia na docelowym Linuksie przed wydaniem.

## Prywatność i licencja

**Nie dodawaj do repozytorium** nagrań głosu, obrazów twarzy, chmur punktów, plików kalibracyjnych z identyfikatorem sensora, osobistych logów i zewnętrznych wag modeli. Więcej w [CONTRIBUTING.md](CONTRIBUTING.md). Własny kod jest udostępniany na licencji [MIT](LICENSE); zależności zachowują własne licencje. Przed wydaniem binarnym konieczny jest niezależny przegląd prawny zależności i pochodzenia plików.
