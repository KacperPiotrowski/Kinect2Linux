# Kinect2-Linux — działający punkt startowy (MVP 0.1)

**Status: eksperymentalny.** To zestaw uruchomieniowy wykorzystujący już przetestowane
na Arch Linux komponenty Kinecta v2. Nie jest gotowym systemem autoryzacji biometrycznej.

## Co działa / co pozostaje do zrobienia

| Funkcja | Status |
| --- | --- |
| Kinect v2 RGB 1080p30 (libfreenect2) | Zweryfikowane w oddzielnych testach |
| IR + Depth 512×424, 30 FPS z OpenMP | Zweryfikowane: 900 par, brak luk przy 4 wątkach |
| IR → V4L2 `/dev/video10` | Zweryfikowane: OpenCV `(424, 512, 3)` |
| Podgląd IR z analizą w osobnym wątku | Nowy prototyp, do testu na KDE Wayland |
| Prowadzone zbieranie 5 modeli Howdy | Skrypt, z ręcznym ustawianiem pozycji; do testu |
| Automatyczna ocena obrotu głowy | Jeszcze nie zaimplementowana |
| Weryfikacja 3D / odporność na spoofing | Jeszcze nie zaimplementowana |
| Systemowa usługa pre-login / PAM | Celowo nie wdrożone |
| Jednoczesne RGB+IR+Depth przez jeden proces | Do wykonania po testach stabilności |

## Warunki

- Linux/Arch, Kinect v2, skompilowany `libfreenect2-omp` z OpenMP.
- Działający `v4l2loopback` na `/dev/video10`.
- Python z `python-opencv`, `python-numpy`, opcjonalnie `python-dlib` (Howdy zapewnia własne dlib).
- `howdy-git` do `enroll`, `models`, `test`.

Przykładowe drzewo plików obok istniejących katalogów:

```text
~/Projekty/kinect/
├── libfreenect2/        # nietknięta wersja referencyjna
├── libfreenect2-omp/    # przetestowana poprawka OpenMP
└── Kinect2-Linux/       # ten projekt
```

## Najkrótsza droga do uruchomienia

```bash
cd ~/Projekty/kinect/Kinect2-Linux
./kinect2 doctor
./kinect2 build
./kinect2 run
```

`run` zostaje uruchomiony w pierwszym terminalu. W drugim:

```bash
cd ~/Projekty/kinect/Kinect2-Linux
./kinect2 preview
```

Jeśli `/dev/video10` nie istnieje, a DKMS odpowiada wersji uruchomionego kernela:

```bash
sudo modprobe v4l2loopback video_nr=10 card_label=Kinect-v2-IR exclusive_caps=1
```

Do podglądu nie trzeba `sudo`. Aby potwierdzić obsługę strumienia przez OpenCV:

```bash
python3 -c 'import cv2; c=cv2.VideoCapture("/dev/video10",cv2.CAP_V4L2); print(c.read()[0]); c.release()'
```

### Prowadzona rejestracja kilku ujęć w Howdy

**Uwaga:** na tym etapie ustawianie głowy jest ręczne. Skrypt prosi o wykonanie
kolejnych póz, ale nie weryfikuje jeszcze ich algorytmicznie. Nie należy tego
mylić z procesem Face ID.

Podczas działania mostu IR w drugim terminalu:

```bash
./kinect2 enroll
./kinect2 models
./kinect2 test
```

`enroll` wywołuje oficjalne `sudo howdy add` pięć razy, opisując pozy: przód,
lewo, prawo, góra, dół. Podczas każdego kroku wpisz zaproponowaną nazwę modelu.
Nie usuwa wcześniejszych modeli ani nie modyfikuje PAM. Wersje Howdy różnią
się sposobem doboru klatki — sprawdź wynik `models` oraz `test`.

**Nie włączaj jeszcze PAM/SDDM/sudo na podstawie wyników tego MVP.**
Standardowe Howdy nie weryfikuje tutaj głębi i może być podatne na podszywanie się.

## Zachowanie precyzji IR

Most wykorzystuje wartości float32 dostarczane przez `libfreenect2` i obcina
je do 8-bitowej luminancji **dopiero** przy wysyłaniu YUYV dla V4L2. To nie
jest surowy 12-bitowy ani 16-bitowy strumień dla analiz 3D. Pliki `*.f32`
z naszych wcześniejszych pomiarów zachowują pełne liczby z libfreenect2.
Odczyt Depth bezpośrednio do modułu rozpoznawania będzie następną częścią runtime.

## Układ projektu

- `src/kinect_ir_bridge.cpp` — oryginalny, sprawdzony kod IR→YUYV/V4L2.
- `face/preview.py` — trzy niezależne czynności: odbiór, detekcja i GUI.
  **Detekcja nie oznacza potwierdzenia tożsamości.**
- `kinect2` — jeden launcher do lokalnego build/run/test/enroll.
- `tests/` — testy bez sprzętu.
- `docs/ROADMAP.md` — kolejne etapy i warunki odbioru.

## Testy bez sprzętu

```bash
python3 -m unittest discover -s tests -v
bash -n kinect2
```

## Rejestracja w repozytorium i upstream

Załóż nowe repo `Kinect2-Linux`, zatwierdź pliki i opisz wersję jako MVP 0.1.
Nie wrzucaj zdjęć twarzy, plików `*.f32`, kluczy, modeli biometrycznych,
prywatnych logów ani lokalnych CSV.

Poprawkę w `libfreenect2-omp` trzymaj w osobnej gałęzi/forku i przygotuj PR
po testach poprawności filtrów, kompilacji bez OpenMP oraz na innych CPU.
Poprawki do Howdy (np. `cli/test.py`) zgłaszaj jako oddzielne PR-y.

Licencja: patrz `LICENSE` dla własnych plików oraz `THIRD_PARTY.md`.
