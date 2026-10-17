# Python SDK — prototyp kontrolny

**To jeszcze nie jest API do pobierania klatek ani sterowania fizycznym Kinectem.** Implementacja zawiera kodek IPC i klienta lokalnego brokera C++ dla operacji `ping()`, `get_status()` oraz `list_devices()`.

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

`get_status()` świadomie zwraca `state: unavailable`: broker **nie** otwiera USB i nie raportuje stanu strumieni. Pole `usb_detection` i metoda `list_devices()` służą jedynie do wykrycia obecności USB Kinect v2 (`045e:02c4`) przez sysfs. `scan_ok: false` oznacza, że sysfs nie udało się odczytać, nie że Kinecta nie ma. Brak urządzenia jest normalny w CI.

Dostępna jest opcja `BrokerClient(socket_path="/private/path/kinect2-broker.sock", timeout=2.0)`. Domyślnie klient łączy się przez `$XDG_RUNTIME_DIR/kinect2-broker.sock`.

Protokół, uprawnienia i ograniczenia prototypu: [docs/IPC-PROTOCOL.md](../../docs/IPC-PROTOCOL.md). `libfreenect2`, NumPy ani fizyczny Kinect nie są potrzebne do testów komunikacji. API `with Kinect()` i przesyłanie klatek dopiero planujemy.
