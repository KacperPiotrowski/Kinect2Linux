# Modułowy build i procesy potomne brokera — etap 1

## Model procesu

Broker pozostaje zarządcą i **jedynym właścicielem USB**. Osobny program
kinect2-worker jest faktycznym podprocesem, uruchamianym przez brokera za
pomocą posix_spawn(). Worker nie otwiera Kinecta i nie uruchamia klatek.

    kinect2-broker (rodzic, USB owner)
        └── kinect2-worker (dziecko, bez dostępu do sensora)

Komunikacja w pierwszym etapie to prywatny socketpair Unix SOCK_SEQPACKET:
HELLO/1 → READY/1, PING/1 → PONG/1, STOP/1 → BYE/1.
Broker weryfikuje ścieżkę binarium (absolutna, własny plik bez symlinków,
niezapisowalny przez inne osoby), uruchamia dziecko przed otwarciem USB,
odpytuje stan i sprząta jego proces po zamknięciu. Worker weryfikuje
PPID i UID oraz używa PR_SET_PDEATHSIG, aby nie pozostać bez rodzica.

Nie ma jeszcze auto-restartu, hot-reload, inotify ani nowych modułów
obliczeniowych. Worker działa z tym samym UID co broker; to izolacja
awarii, **nie granica bezpieczeństwa dla niezaufanych pluginów**.

## Przyrostowa kompilacja

Potrzebne Arch: cmake, ninja, gcc (C++23), nlohmann-json.

    bash tools/build_broker.sh
    bash tools/build_broker.sh

Drugie wywołanie nie kompiluje ponownie niezmienionych plików.
CMake/Ninja ma odrębne biblioteki discovery, session, hardware stub
i worker supervisor. Ponownie linkuje tylko zależne programy.

Sprzętowa wersja w osobnym katalogu build, z lokalnym libfreenect2-omp:

    bash tools/build_broker.sh --with-hardware

Domyślny bin/kinect2-broker nadal NIGDY nie otwiera Kinecta; tryb
sprzętowy nadal wymaga --allow-device-control.

## Test bez Kinecta

    bash tools/build_broker.sh
    ./bin/test_worker_process "$PWD/bin/kinect2-worker"

Zatrzymaj wcześniejszy broker; w terminalu nr 1:

    ./bin/kinect2-broker --worker "$PWD/bin/kinect2-worker"

W terminalu nr 2:

    PYTHONPATH=sdk/python python3 - <<'PY'
    from kinect2_linux import BrokerClient
    c = BrokerClient()
    print("PING:", c.ping())
    print("WORKER:", c.get_status()["worker"])
    print("USB:", c.get_status()["sensor_open"])
    PY

Worker powinien mieć enabled=true, healthy=true i niezerowy PID,
a sensor_open=false. Komenda:

    ps -o pid,ppid,cmd -p PID_WORKERA

powinna pokazać broker jako PPID. Ctrl+C w terminalu nr 1 zatrzymuje
podproces, po czym broker kończy pracę.

## Co dalej

W osobnych zmianach: binarny protokół danych i ograniczone kolejki
RGB/IR/Depth, wielu klientów, później kontrolowany restart workerów
po bezpiecznej wymianie ich plików i rollback w przypadku błędów.
Nie ma jeszcze żadnego ładowania nowych plików podczas pracy.
Fizyczny sensor nadal otwiera wyłącznie jeden proces.

**Warunek sprzętowy:** 30 FPS RGB uzyskano tylko w jaśniejszym
pomieszczeniu; przy słabszym oświetleniu RGB miało 15 FPS.
IR/Depth utrzymywały 30 FPS w obu warunkach.
