# Automatyczne strumienie brokera — etap eksperymentalny

**Cel:** każdy zwykły proces Pythona sam wybiera `rgb`, `ir` albo `depth`.
Nie używa `open_device/start_streams/stop_streams/close_device`, a
broker **jako jedyny** otwiera USB, gdy jest co najmniej jeden aktywny
odbiorca. Gdy ostatni się rozłączy, broker zwalnia urządzenie i blokadę.

Przykłady mają charakter eksperymentalny. Nie wymieniamy nimi
funkcjonujących mostów V4L2 i usług systemd.

## Uruchomienie na Arch

Przed testem świadomie zatrzymaj dotychczasowy broker, IR V4L2 i
inne programy korzystające z fizycznego sensora. Usługa RGB
`kinect2-rgb-webcam.service` może pozostać zarejestrowana w systemd,
ale jej aktywni odbiorcy nie mogą jednocześnie trzymać USB.
**Nie usuwaj pliku `kinect2-sensor.lock` ani gniazd na siłę.**

    bash tools/bootstrap_libfreenect2_omp.sh
    bash tools/build_broker.sh --with-hardware
    ./bin/test_auto_capture
    ./bin/test_frame_hub

Terminal 1, jawnie włączone sprzęt, IPC klatek i automatyka:

    OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE \
      ./bin/kinect2-broker-hw \
        --allow-device-control --frame-preview --auto-streams \
        --worker "$PWD/bin/kinect2-worker"

Terminal 2, cztery podglądy Python — kontroler **nie**
przejmuje ani nie zamyka USB w tym trybie:

    python3 tools/demo_four_clients.py

Możesz też uruchomić wiele **samodzielnych** procesów Pythona;
każdy z nich z osobna otrzymuje wybrany strumień, bez centralnego
uruchamiania demo:

    PYTHONPATH=sdk/python python3 - <<'PY'
    from kinect2_linux.frame_client import FrameClient
    with FrameClient("depth", timeout=20) as camera:
        for _ in range(30):
            with camera.receive() as frame:
                print(frame.kind, frame.width, frame.height, frame.sequence)
    PY

Kinect zostaje otwarty po przyłączeniu odbiorcy (do kilkuset ms
opóźnienia + czas startu sensora), a po zamknięciu ostatniego gniazda
urządzenie i blokada są zwalniane. `FrameClient` może pomijać zaległe
klatki dzięki `receive_latest()`; `receive()` oddaje FIFO.

## Status i zarządzanie życiem

    PYTHONPATH=sdk/python python3 - <<'PY'
    from kinect2_linux import BrokerClient
    s = BrokerClient().get_status()
    print("USB:", s["sensor_open"], "STREAMS:", s["selected"])
    print("CLIENTS:", s["frame_preview"])
    PY

`frame_preview.mode=automatic` oznacza, że broker sam zarządza
strumieniami. `frame_preview.rgb`, `ir`, `depth` zliczają
**logicznych** odbiorców każdego typu (IR i Depth fizycznie tworzą
jeden wspólny tor); `subscribers` zawiera ich sumę.

Zestaw strumieni jest sumą aktywnych subskrypcji. Przykładowo:
jedno RGB i jeden IR => sprzętowo RGB + IR/Depth. Zamknięcie RGB
nie zatrzymuje IR. Gdy wszyscy wyjdą, USB przestaje być zajęte.
Martwe połączenia są zbierane nawet bez kolejnych klatek sensora.

W trybie `--auto-streams` stare polecenia globalne
`open_device`, `start_streams`, `stop_streams`, `close_device`
odpowiadają błędem `managed_by_subscribers`, żeby przypadkowy klient
nie mógł zatrzymać obrazu innych. Stary tryb ręczny, bez
`--auto-streams`, pozostał niezmieniony do diagnostyki i benchmarków.
W przypadku błędu przejęcia sensora `frame_preview.last_error`
wskazuje kod (np. `device_busy`); broker ponawia próbę co 2 sekundy,
dopóki ktoś jest połączony.

## Ograniczenia pierwszego wdrożenia

- Broker nadal działa sekwencyjnie i może na chwilę zablokować
  polecenia podczas otwierania / przełączania sprzętu.
- Zmiana sumy strumieni wymaga zatrzymania i restartu sprzętowego
  `startStreams`. Istniejący odbiorcy mogą wtedy na krótko
  przestać dostawać klatki; gniazda pozostają otwarte.
  **Kinect v2 może przy tym na chwilę mrugnąć kontrolką** — to efekt
  `device->stop()` + `device->startStreams(...)`, nie celowe odłączenie
  i ponowne otwarcie uchwytu USB. Przykład: po odłączeniu obydwu IR, gdy
  pozostają 2 RGB, broker przechodzi z RGB+IR/Depth do samego RGB.
  `sensor_open` nadal powinno być `True`, a RGB wznowić klatki.
  Liczniki `frame_counts` zerują się podczas restartu strumieni,
  więc mierz FPS dopiero po ustabilizowaniu nowego zestawu.
- Limit ośmiu jednoczesnych subskrybentów, prywatne gniazda Unix
  tego samego UID, memfd z pełną kopią danych na ramkę.
- Brak automatycznej migracji starej kamery V4L2 na brokera.
  Mosty V4L2 są alternatywną ścieżką dostępu do USB.
- `FrameClient` nie daje jeszcze obsługi kilku strumieni jednym
  obiektem, automatycznej rekonfiguracji przy restarcie brokera,
  pełnych statystyk per-viewer ani publicznego wersjonowanego wydania SDK.
- Nie jest to test fizycznego Kinecta z tymi konkretnymi zmianami:
  offline CI sprawdza fikcyjne urządzenie i 4 subskrybentów IPC.
  Do zmiany PR z Draft potrzeba testu sprzętowego USB i 4 klientów,
  po czym pomiarów CPU i stabilności na jednej maszynie.

**Nie scalać wyłącznie na podstawie zielonego CI.**
