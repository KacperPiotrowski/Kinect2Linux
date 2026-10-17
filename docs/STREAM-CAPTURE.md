# Kinect2-Linux — selektywne przechwytywanie natywne (PR #8, eksperymentalne)

**Status:** oddzielny, opt-in proces sprzętowy C++23 potrafi uruchomić RGB, IR+Depth lub obie grupy.
To **tylko liczniki odebranych klatek**. Obrazy NIE opuszczają brokera, nie ma API ramek
dla Pythona, V4L2 ani kolejki subskrypcji; nie ma też gwarancji FPS lub synchronizacji.

## Architektura i zakres

- Jeden `DeviceSession` otwiera Kinecta i utrzymuje ten sam `flock` co stare mosty.
- `start_streams(rgb=..., ir_depth=...)` wywołuje natywne `startStreams(rgb, ir_depth)`
  na jednym urządzeniu. Osobne obiekty nasłuchujące liczą RGB i sparowane IR/Depth;
  do IPC trafiają tylko liczniki, bez danych i bez dodatkowych konwersji.
- `stop_streams()` kończy pracę wątków i natywne strumienie, **zostawiając otwarty uchwyt USB**;
  można wybrać inny tryb po zatrzymaniu, bez zamykania Kinecta.
- `close_device()` zawsze zatrzymuje przechwytywanie przed zwolnieniem USB i blokady.
- `get_status()` zwraca `state: idle/open/streaming`, `selected`, `frame_counts` i
  `streaming`. **`streaming: true` oznacza przyjętą konfigurację, a nie dowód żywych
  klatek**. Zatrzymanie/odłączenie sprzętu w trakcie pracy wymaga dalszej obsługi.
- Mikrofon to osobne urządzenie ALSA/PipeWire — PR #8 nie zmienia audio.

IR i Depth są w tej wersji **jednym trybem sprzętowym `ir_depth`**, choć późniejsze
subskrypcje klientów będą mogły wskazywać pojedynczy typ ramki. Nie zakładamy,
że jednoczesny RGB + IR/Depth ma już potwierdzone FPS na fizycznym Kinekcie.

## Bezpieczny build i testy bez sprzętu

```bash
bash tools/build_broker.sh
./bin/test_sensor_backend
./bin/test_device_session
KINECT2_BROKER_BIN="$PWD/bin/kinect2-broker" python3 -m unittest discover -s tests -v
```

Zwykły broker **nie ma** dostępu do libfreenect2 i odpowiada
`device_control_disabled` na `open_device`, `start_streams`, `stop_streams` i `close_device`.

## Test ręczny na Kinect v2, po zielonym CI

1. Zatrzymaj poprzedni broker i działające mosty, jeżeli używają USB
   (`./kinect2 run`, `./kinect2 depth`, producent RGB). Nie wyłączamy ich
   automatycznie i nie usuwamy pliku blokady.
2. W repozytorium z gałęzi PR #8 zbuduj wariant sprzętowy:

```bash
LIBFREENECT2_DIR="$PWD/../libfreenect2-omp" bash tools/build_broker.sh --with-hardware
./bin/kinect2-broker-hw --allow-device-control
```

3. W drugim terminalu przeprowadź test najpierw **IR+Depth** (bez RGB):

```bash
PYTHONPATH=sdk/python python3 - <<'PY'
import time
from kinect2_linux import BrokerClient

client = BrokerClient(timeout=20)
try:
    print('OPEN:', client.open_device())
    print('START:', client.start_streams(ir_depth=True))
    time.sleep(3)
    print('STATUS:', client.get_status())
finally:
    try:
        print('STOP:', client.stop_streams())
    finally:
        print('CLOSE:', client.close_device())
PY
```

Oczekujemy `frame_counts.ir > 0` i `frame_counts.depth > 0`, ale **nie uznajemy
ich ani zadeklarowanego `streaming=true` za wystarczający pomiar FPS**.
Po zaliczeniu IR+Depth można przetestować oddzielnie `rgb=True`, a następnie
`rgb=True, ir_depth=True`; dopiero taki test pokaże, czy kombinacja działa
na tej konfiguracji Kinect v2 i CPU.

**Jeśli otwarcie/przechwytywanie się nie powiedzie:** zatrzymaj eksperymentalny
broker (Ctrl+C), potwierdź zwolnienie blokady, wróć do istniejących mostów.
Nie używaj `sudo` ani nie restartuj automatycznie usług. Komendy
`start_streams`/`stop_streams` są dostępne tylko w sprzętowym brokerze z flagą
`--allow-device-control` i **nie** dają klientowi wyłączności na tryb sesji.

## Plan kolejnego etapu

Osobne, ograniczone kolejki danych/bufory dla RGB, IR i Depth; wielu odbiorców,
każdy z własnym wyborem strumieni i odpowiednim backpressure. Brak tych
właściwości jest celowy w PR #8. Nie scalać jako „działający SDK klatek”.
