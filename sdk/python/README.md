# Python SDK — prototyp kontrolny

**Kontrolny broker i odbiór klatek są osobnymi API.** W `main` istnieje eksperymentalny `FrameClient("rgb" | "ir" | "depth")` do odbierania prawdziwych klatek przez gniazdo Unix i sealed memfd. PR #15 dodaje automatyczne uruchamianie strumieni po podłączeniu klienta; nie jest to jeszcze stabilne, instalowalne `pip` SDK. Domyślny broker bez `--allow-device-control` obsługuje jedynie `ping()`, `get_status()` i `list_devices()` oraz nie otwiera USB. Eksperymentalne `open_device()` / `close_device()` oraz `start_streams(rgb=..., ir_depth=...)` / `stop_streams()` działają wyłącznie z osobno skompilowanym i jawnie uruchomionym wariantem sprzętowym.

Z głównego katalogu repozytorium:

```bash
bash tools/build_broker.sh
./bin/kinect2-broker
```

W drugim terminalu:

```bash
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient

client = BrokerClient()
print(client.ping())
print(client.get_status())
print(client.list_devices())
PY
```

Dla zwykłego brokera `get_status()` świadomie zwraca `state: unavailable`: bez jawnego trybu sprzętowego **nie** otwiera USB ani nie raportuje stanu strumieni. Pole `usb_detection` i metoda `list_devices()` służą jedynie do wykrycia obecności USB Kinect v2 (`045e:02c4`) przez sysfs. `scan_ok: false` oznacza, że sysfs nie udało się odczytać, nie że Kinecta nie ma. Brak urządzenia jest normalny w CI.

Dostępna jest opcja `BrokerClient(socket_path="/private/path/kinect2-broker.sock", timeout=2.0)`. Domyślnie klient łączy się przez `$XDG_RUNTIME_DIR/kinect2-broker.sock`.

Protokół, uprawnienia i ograniczenia prototypu: [docs/IPC-PROTOCOL.md](../../docs/IPC-PROTOCOL.md). `libfreenect2`, NumPy ani fizyczny Kinect nie są potrzebne do testów komunikacji. Przyszłe wysokopoziomowe `with Kinect()` i wersjonowane pakiety `pip` dopiero planujemy; surowe klatki przez `FrameClient` są już obsługiwane.

**Ręczny test sprzętowy i procedura wycofania:** [DEVICE-CONTROL.md](../../docs/DEVICE-CONTROL.md). Przy poprawnym otwarciu Kinecta stan `open` oznacza wyłącznie uchwyt urządzenia, nie działające strumienie.

**Selektywny capture i liczniki brokera:** [STREAM-CAPTURE.md](../../docs/STREAM-CAPTURE.md). `get_status().frame_counts` wskazuje liczby odebranych ramek RGB, IR i Depth. Audio pozostaje niezależne przez ALSA/PipeWire.

**Diagnoza przepustowości RGB i współpracy RGB+IR+Depth:** [RGB-PERFORMANCE.md](../../docs/RGB-PERFORMANCE.md), benchmark `python3 tools/benchmark_capture.py`. Najpierw pomiary po rozgrzewce, dopiero potem optymalizacje pipeline'u.

## Pierwszy samodzielny odbiorca (PR #15, gałąź eksperymentalna)

W pierwszym terminalu uruchom brokera na fizycznym sensorze:

```bash
bash tools/bootstrap_libfreenect2_omp.sh
bash tools/build_broker.sh --with-hardware
OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE \
  ./bin/kinect2-broker-hw --allow-device-control --frame-preview --auto-streams
```

W drugim terminalu ten program sam uruchomi przechwytywanie IR i Depth
(tylko IR jest logicznie subskrybowany). Po wyjściu z kontekstu
broker automatycznie zamknie sprzęt, jeśli nie ma innych subskrybentów.

```bash
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux.frame_client import FrameClient

with FrameClient("ir", timeout=20) as camera:
    for _ in range(30):
        with camera.receive() as frame:
            print("IR:", frame.width, frame.height, frame.sequence)
PY
```

Jeśli uruchomisz w innym terminalu identyczny kod ze strumieniem `"rgb"`,
oba procesy dzielą jeden fizyczny sensor; nie potrzebują wzajemnie się znać.
Więcej: [AUTO-SUBSCRIPTIONS.md](../../docs/AUTO-SUBSCRIPTIONS.md).
