# Kinect2-Linux

**Open source · Linux · Kinect v2 / Kinect for Windows v2**

Eksperymentalny zestaw narzędzi i zalążek SDK dla Microsoft Kinect v2. Cel: **proste uruchomienie** i **pełny dostęp do oryginalnych danych** RGB, IR, Depth i czterech mikrofonów. Żadne narzędzie zewnętrzne (EasyEffects, MediaPipe, Howdy) nie jest obowiązkowym elementem ścieżki przechwytywania. Projekt **nie jest jeszcze pełnym, plug-and-play SDK 2.0**; plan migracji jest w [docs/REBUILD-PLAN.md](docs/REBUILD-PLAN.md).

> Projekt społecznościowy, nieoficjalny; nie jest częścią Microsoft ani OpenKinect. Nie służy obecnie do bezpiecznej autoryzacji biometrycznej.

**English:** Kinect2-Linux is an unofficial MIT-licensed Linux project for
Microsoft Kinect v2. The working prototype provides RGB, IR, Depth and native
4-channel ALSA access, plus an experimental C++ broker and Python frame client.
It is **not yet a plug-and-play 1.0 release**. Contributors and hardware testers
are welcome: [Get involved](docs/COMMUNITY.md) ·
[Contributing](CONTRIBUTING.md) ·
[Open issues](https://github.com/KacperPiotrowski/Kinect2Linux/issues).

## Aktualny stan — 17 października 2026 (`main`)

| Funkcja | Stan i ograniczenia |
| --- | --- |
| Kinect v2 USB | Wykrywany przez diagnostykę |
| RGB | 1920×1080, YUYV, `/dev/video11`, most z aktywacją na żądanie; Firefox i przechwycenie klatki FFmpeg przetestowane; podgląd `ffplay` bywa czarny |
| IR | 512×424, `/dev/video10` przez V4L2; płynny podgląd potwierdzony przez testującego |
| Depth | 512×424, float32 w mm; test 120/120 par IR+Depth, bez luk sekwencji |
| Audio | Natywny odczyt ALSA: 4 kanały, 16 kHz, S32_LE; bez obowiązkowego downmixu |
| Python SDK | Eksperymentalny `FrameClient` odbiera rzeczywiste klatki RGB/IR/Depth przez Unix socket i sealed memfd; wysokopoziomowe, stabilne API jeszcze nie jest wydane |
| Wielu klientów brokera | Transport 2 × RGB + 2 × IR od jednego brokera jest scalony (PR #11), przetestowany na sprzęcie; automatyczne uruchamianie strumieni po subskrypcji jest w **Draft PR #15**, jeszcze nie w `main` |
| Body/Face Tracking | Eksperymenty osobno, MediaPipe wstrzymane; brak stabilnego API |

Wyniki pochodzą z lokalnych testów na jednym sprzęcie, **nie** z oficjalnej certyfikacji. Szczegóły: [punkt odniesienia](docs/BASELINE-2026-10-16.md).

## Szybki start (obecny prototyp — Arch Linux)

Założenia: Kinect v2 z zasilaczem i USB 3.0; biblioteka `libfreenect2-omp` budowana przez `tools/bootstrap_libfreenect2_omp.sh` (lub opcjonalna stara biblioteka w `../libfreenect2-omp`); `v4l2loopback`, `python3`, `numpy`, `opencv` i narzędzie `flock` (z `util-linux`). Nie dostarczamy w tym repozytorium sterownika OpenKinect ani modułu jądra. Ścieżkę biblioteki można ustawić przez `LIBFREENECT2_DIR`.

```bash
./kinect2 status         # tylko diagnostyka: nie otwiera sensora
./kinect2 devices
./kinect2 clients
./kinect2 doctor
./kinect2 build          # most IR, jeśli istnieje libfreenect2-omp
```

### Odtwarzalny build libfreenect2-omp (scalony PR #13)

Jeżeli nie masz lokalnych nagłówków `libfreenect2`, nie musisz ich
kopiować ręcznie. Można pobrać
**przypięte źródła OpenKinect razem z `include/`** i nałożyć
zweryfikowaną poprawkę OpenMP z lokalnej wersji użytkownika:

```bash
bash tools/bootstrap_libfreenect2_omp.sh
bash tools/build_broker.sh --with-hardware
```

Pierwsze pobranie wymaga internetu, a kompilacja wymaga zależności
CMake/libusb/TurboJPEG; nie zmienia istniejącej kopii `../libfreenect2-omp`.
**Budowa i podstawowy przechwyt na fizycznym Kinekcie zostały przetestowane
na Arch Linux; instalator i wielodystrybucyjne testy pozostają planowane.** Szczegóły: [docs/LIBFREENECT2-OMP-SETUP.md](docs/LIBFREENECT2-OMP-SETUP.md).

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

## Eksperymentalny podgląd wielu klientów (PR #11 scalony)

Kod znajdujący się już w `main` potrafi dostarczać rzeczywiste klatki
**dwóm niezależnym podglądom RGB i dwóm podglądom IR** przez jeden proces
brokera i jeden uchwyt USB. W wersji `main` demonstracja nadal ręcznie
uruchamia i zatrzymuje sesję przechwytywania (przełączniki
`--allow-device-control --frame-preview`); nie ma pełnego automatycznego
zarządzania sprzętem po odejściu ostatniego klienta.
W [Draft PR #15](https://github.com/KacperPiotrowski/Kinect2Linux/pull/15)
powstaje jawny tryb `--auto-streams`, sprawdzony z 4 odbiorcami
na fizycznym sensorze. Ten PR nie jest jeszcze scalony.
**Firefox/OBS przez istniejące `/dev/video11` i broker nie mogą obecnie
współdzielić tego samego otwartego sensora**; integrację obsługi V4L2
wewnątrz jednej docelowej usługi opisuje
[issue #16](https://github.com/KacperPiotrowski/Kinect2Linux/issues/16).
Instrukcja techniczna: [cztery okna podglądu](docs/FOUR-CLIENT-PREVIEW.md).

## Dokumentacja i przykłady

- [Plan przebudowy](docs/REBUILD-PLAN.md) — architektura wspólnego rdzenia i IPC.
- [Status API](docs/STATUS.md) oraz [Live Status](docs/LIVE-STATUS.md) — odczyt bez otwierania USB.
- [RGB on-demand](docs/RGB-ON-DEMAND.md) — aktualna konfiguracja wirtualnej kamery.
- [Eksperymentalny Point Cloud](src/kinect2_cloud.cpp) + [przeglądarka PLY](tools/kinect2_cloud_view.py) — osobne narzędzia, poza rdzeniem SDK.
- Narzędzia Pythona: `tools/kinect2_status.py`, `tools/audio_raw_analyze.py`, `face/preview.py`. Publiczne API Python powstanie w ramach przebudowy rdzenia.
- [Eksperymenty Face3D, Howdy, MediaPipe](docs/EXPERIMENTS.md) — opcjonalne, nie do uwierzytelniania.
- [Dołącz do projektu / Get involved](docs/COMMUNITY.md) oraz [współtworzenie](CONTRIBUTING.md), [zależności](docs/DEPENDENCIES.md), [licencje](THIRD_PARTY.md).
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
