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

## Aktualny stan — 18 października 2026 (`main`)

| Funkcja | Stan i ograniczenia |
| --- | --- |
| Kinect v2 USB | Wykrywany przez diagnostykę |
| RGB | 1920×1080 przez `/dev/video11` z V4L2 obsługiwanym **wewnątrz brokera** (`--v4l2-rgb`); Firefox razem z 2 odbiorcami RGB i 2 IR przetestowany na Arch Linux |
| IR | 512×424 jako natywne klatki do odbiorców brokera; osobny starszy most V4L2 `/dev/video10` pozostaje opcjonalny i nie jest częścią wspólnego brokera |
| Depth | 512×424, float32 w mm; test 120/120 par IR+Depth, bez luk sekwencji |
| Audio | Natywny odczyt ALSA: 4 kanały, 16 kHz, S32_LE; bez obowiązkowego downmixu |
| Python SDK | Eksperymentalny `FrameClient` odbiera rzeczywiste klatki RGB/IR/Depth przez Unix socket i sealed memfd; wysokopoziomowe, stabilne API jeszcze nie jest wydane |
| Wielu klientów brokera | PR #15 i #20 są scalone: automatyczne otwieranie/zamykanie USB oraz Firefox + 2×RGB + 2×IR przez jednego brokera. Potwierdzono restart KDE i zwolnienie USB w stanie bez klientów (jeden testowany komputer) |
| Body/Face Tracking | Eksperymenty osobno, MediaPipe wstrzymane; brak stabilnego API |

Wyniki pochodzą z lokalnych testów na jednym sprzęcie, **nie** z oficjalnej certyfikacji. Szczegóły: [punkt odniesienia](docs/BASELINE-2026-10-16.md).

## Basic / Advanced — jeden projekt, jeden broker

**Basic ukrywa złożoność, nie funkcje. Advanced udostępnia kontrolę, nie
osobny produkt.** Dostęp do Howdy i innych integracji docelowo będzie możliwy
z obu widoków (opcjonalnie i bez automatycznej modyfikacji PAM).

Pierwszy krok to działający interfejs CLI nad istniejącą infrastrukturą,
**jeszcze nie gotowa graficzna instalacja plug-and-play**:

```bash
./kinect2 basic check      # tylko diagnostyka
./kinect2 basic prepare    # buduje broker bez uruchamiania
./kinect2 basic activate   # aktywuje kamerkę i istniejące profile mikrofonowe
./kinect2 advanced status  # ta sama infrastruktura, pełna diagnostyka
```

Basic udostępnia RGB i istniejący profil `Kinect2_Stereo`; surowe 4ch,
IR/Depth i SDK pozostają dostępne. Kamera w tym etapie nadal nazywa się
`Kinect v2 RGB`; nazwa ogólna `USB Camera` wymaga osobnego bezpiecznego
wdrożenia. **Przed `activate`** konieczne jest obecne przygotowanie
`/dev/video11` i rozwiązanie konfliktu starego producenta RGB. Żadne
polecenie nie uruchamia sudo ani nie zmienia domyślnego źródła audio.
[Pełny opis, ograniczenia i rollback](docs/BASIC-ADVANCED.md).

## Modele śledzenia: Basic / Advanced / OFF (eksperyment)

Śledzenie sylwetki jest **opcjonalne** i działa poza brokerem USB.
Interfejs `TrackingSession` obsługuje **OFF** (bez ładowania modeli),
**Basic** (sprawdzany na sprzęcie lekki model CPU) oraz **Advanced**
(możliwość wyboru z listy zweryfikowanych modeli, gdy będą dostępne).
Wszystkie modele są ładowane dopiero przy pierwszej potrzebnej klatce.

Eksperymentalny Body Tracking **YOLOX-tiny + RTMPose-s**, z 17 punktami
szkieletu 2D i obsługą wielu osób, przeszedł testy na fizycznym Kinect v2.
Domyślny profil testowy używa jednego wątku inferencji na sesję ONNX Runtime,
bez aktywnego oczekiwania (*spinning*); nie jest to pomiar wydajności na
każdym komputerze. Modele i zależności są **opcjonalne** i wymagają osobnego
przygotowania. Nie są automatycznie uruchamiane przez CLI Basic, a dłonie
i twarz nie mają jeszcze adapterów w nowym interfejsie.

[Opis interfejsu](docs/TRACKING-MODELS.md) ·
[Instrukcja eksperymentu Body CPU](docs/BODY-BASIC-CPU.md).

## Szybki start (obecny prototyp — Arch Linux)


### Instalator krok po kroku (eksperymentalny, Arch Linux)

Przed pierwszą instalacją przeczytaj
[pełną instrukcję i rollback](docs/INSTALL.md). Skrypt nie używa
automatycznie `sudo` ani `pacman`, nie usuwa starych usług i nie
przejmuje USB bez Twojej zgody.

```bash
bash tools/install_kinect2.sh --check    # tylko odczyt, bez zmian
bash tools/install_kinect2.sh --prepare  # zbuduj i przygotuj wyłączoną usługę
# Po osobnym skonfigurowaniu /dev/video11 i zatrzymaniu legacy:
bash tools/install_kinect2.sh --activate # jawnie uruchom brokera RGB
```

To **pierwsza wersja instalatora do testów społeczności**, a nie
potwierdzona instalacja plug-and-play na wielu dystrybucjach.


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

### IR i Depth — starsza ścieżka legacy

Dla nowych integracji preferuj brokera i odbiorców `FrameClient`.
Poniższe komendy opisują wcześniejsze mosty i nie służą do
równoległego uruchamiania z aktywnym brokerem.

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

Dla wspólnego brokera i Firefoksa użyj [BROKER-V4L2-RGB](docs/BROKER-V4L2-RGB.md).
Poniższa instalacja starego mostu to ścieżka legacy i nie powinna
pracować równocześnie z nowym brokerem.

Instalacja urządzenia i usług **zmienia konfigurację systemu**. Wykonuj ją świadomie (nie jest potrzebna do poleceń `status/devices/clients`). Instrukcja: [docs/RGB-ON-DEMAND.md](docs/RGB-ON-DEMAND.md). Kod uruchomieniowy: `webcam/`. Samo wykrycie `/dev/video11` nie oznacza aktualnego przesyłania klatek.

### Mikrofony

Mikrofony ALSA działają niezależnie od mostu RGB. **Natywne 4ch pozostają bez zmian**, a dwa opcjonalne źródła PipeWire (`Kinect2_Mono` i `Kinect2_Stereo`) można uruchomić jawnie przez `python3 tools/kinect2_audio_profiles.py start`. Nie przełączamy domyślnego wejścia. Instrukcje, autostart i rollback: [docs/AUDIO.md](docs/AUDIO.md).

## Eksperymentalne procesy potomne i build przyrostowy

Nowy broker (opcjonalnie) może sam uruchomić i nadzorować pomocniczy
proces bez USB. CMake + Ninja kompiluje osobno zmienione moduły.
Szczegóły i test offline: [CHILD-WORKERS.md](docs/CHILD-WORKERS.md).

**Uwaga do FPS:** pomiar RGB 30 FPS uzyskano przy mocniejszym
oświetleniu, natomiast w słabszym świetle automatyczna ekspozycja
korelowała z RGB 15 FPS. W obu warunkach IR i Depth osiągały
około 30 FPS; dane z jednego stanowiska nie są ogólną gwarancją.

## Wspólny broker RGB/IR/Depth — eksperymentalna konfiguracja z `main`

Po scaleniu [PR #15](https://github.com/KacperPiotrowski/Kinect2Linux/pull/15)
i [PR #20](https://github.com/KacperPiotrowski/Kinect2Linux/pull/20),
broker może być jedynym właścicielem fizycznego Kinecta, uruchamiać
strumienie na żądanie i zasilać zarówno Firefox przez `/dev/video11`,
jak i odbiorców Python `FrameClient`. Na jednym Arch Linux/KDE
sprawdzono działanie **Firefoksa + czterech podglądów SDK**
oraz automatyczny start brokera po restarcie.

**To nadal wersja przed wydaniem 1.0.** Instalacja wymaga jawnego
skonfigurowania `v4l2loopback`, biblioteki `libfreenect2-omp`,
uprawnień USB, usługi `systemd --user` i zatrzymania starego,
odrębnego producenta RGB. Nie uruchamiaj równolegle starego mostu
`kinect2-rgb-webcam.service` z brokerem używającym `--v4l2-rgb`.
Procedury i rollback:
[broker i Firefox](docs/BROKER-V4L2-RGB.md),
[usługa użytkownika](docs/BROKER-USER-SERVICE.md),
[cztery podglądy](docs/FOUR-CLIENT-PREVIEW.md).
Dostępny jest [eksperymentalny instalator prowadzony](docs/INSTALL.md),
bez automatycznych operacji administratora; nie jest to jeszcze instalacja „jednym kliknięciem”.

## Dokumentacja i przykłady

- [Instalacja (Arch Linux, eksperymentalna)](docs/INSTALL.md) — check, prepare, activate, powrót.
- [Plan przebudowy](docs/REBUILD-PLAN.md) — architektura wspólnego rdzenia i IPC.
- [Status API](docs/STATUS.md) oraz [Live Status](docs/LIVE-STATUS.md) — odczyt bez otwierania USB.
- [RGB on-demand (legacy)](docs/RGB-ON-DEMAND.md) i [wspólny broker V4L2](docs/BROKER-V4L2-RGB.md) — starszy producent RGB kontra nowy broker.
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
