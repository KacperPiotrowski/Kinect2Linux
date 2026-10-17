# Python SDK — prototyp kontrolny

**To jeszcze nie jest API do pobierania klatek.** Domyślny broker obsługuje jedynie `ping()`, `get_status()` i `list_devices()` oraz nie otwiera USB. Eksperymentalne `open_device()` / `close_device()` oraz `start_streams(rgb=..., ir_depth=...)` / `stop_streams()` działają wyłącznie z osobno skompilowanym i jawnie uruchomionym wariantem sprzętowym.

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

Protokół, uprawnienia i ograniczenia prototypu: [docs/IPC-PROTOCOL.md](../../docs/IPC-PROTOCOL.md). `libfreenect2`, NumPy ani fizyczny Kinect nie są potrzebne do testów komunikacji. API `with Kinect()` i przesyłanie klatek dopiero planujemy.

**Ręczny test sprzętowy i procedura wycofania:** [DEVICE-CONTROL.md](../../docs/DEVICE-CONTROL.md). Przy poprawnym otwarciu Kinecta stan `open` oznacza wyłącznie uchwyt urządzenia, nie działające strumienie.

**Selektywny capture (bez obrazów w Pythonie):** [STREAM-CAPTURE.md](../../docs/STREAM-CAPTURE.md). `get_status().frame_counts` wskazuje liczby odebranych ramek RGB, IR i Depth. Audio pozostaje niezależne przez ALSA/PipeWire.
