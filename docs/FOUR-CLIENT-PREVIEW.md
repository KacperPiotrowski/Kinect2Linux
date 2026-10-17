# Test czterech klientów Kinect v2: 2 RGB + 2 IR

To jest fizyczny test obrazu, a nie test samych liczników. Cztery osobne
procesy Pythona otwierają okna RGB A, RGB B, IR A oraz IR B. Wyłącznie
jeden natywny broker otwiera USB. Programy otrzymują klatki przez prywatne
gniazdo Unix, nie otwierają libfreenect2 ani sensora.

## Wymagania

- Arch Linux, fizyczny Kinect v2 i lokalny libfreenect2-omp.
- CMake, Ninja, GCC/C++23 i nlohmann-json.
- Python, numpy oraz OpenCV **z GUI (HighGUI, cv2.imshow)**;
  pakiet opencv-python-headless nie wyświetla okien.
- Działająca sesja KDE Wayland/XWayland.
- Zatrzymany poprzedni broker i mosty V4L2 używające USB.

## Instrukcja

    git fetch origin
    git switch --track origin/feat/preview-four-clients
    bash tools/build_broker.sh --with-hardware
    ./bin/test_frame_hub
    ./bin/test_sequence_gap_tracker

Terminal 1 — świadome zezwolenie na hardware i eksperymentalny frame IPC:

    ./bin/kinect2-broker-hw --allow-device-control --frame-preview \
      --worker "$PWD/bin/kinect2-worker"

Terminal 2 — kontroler otwierający jedną sesję USB i cztery osobne GUI:

    python3 tools/demo_four_clients.py

Oczekuj czterech różnych okien z ruchomymi obrazami.
ESC albo Q zamyka wyłącznie wybrane okno; pozostałe trzy nadal
pracują. Kontroler zamyka USB po zamknięciu wszystkich okien albo
po Ctrl+C w terminalu 2, kiedy kończy bezpiecznie całą sesję.

W trzecim terminalu możesz zbadać liczbę odbiorców:

    PYTHONPATH=sdk/python python3 - <<'PY'
    from kinect2_linux import BrokerClient
    s = BrokerClient().get_status()
    print("CLIENTS:", s["frame_preview"])
    print("FRAMES:", s["frame_counts"])
    print("GAPS:", s["sequence_gaps"])
    print("WORKER:", s["worker"])
    PY

Przy czterech oknach spodziewamy się frame_preview.subscribers = 4.

## Co jest zaimplementowane

Pojedyncze RGB (1920x1080 x 4 B) oraz IR i Depth (512x424 float32)
pochodzą z jednego natywnego urządzenia. Każda klatka jest kopiowana
raz do zapieczętowanego, niezmiennego memfd. Broker dostarcza deskryptor
do dowolnej liczby klientów (limit 8) przez Unix SOCK_SEQPACKET
i SCM_RIGHTS. Każdy odbiorca mapuje dane tylko do odczytu.
Piksele nigdy nie przechodzą przez kontrolny JSON.

Prywatne gniazdo to $XDG_RUNTIME_DIR/kinect2-frames.sock.
Klient inicjuje subskrypcję bajtem R, I lub D, potwierdzenie to K.
Następnie otrzymuje 32-bajtowy binarny nagłówek K2F1 oraz deskryptor
z niezmienną klatką. Klienci muszą mieć ten sam UID co broker.
Nie można otwierać Kinecta z innego procesu.

## Obecne granice funkcjonalności

- To transport **testowy**, nie docelowy zero-copy ring buffer.
- Wolne podglądy mogą pomijać klatki, aby nie blokować sensora.
- Kontroler demonstracji jednorazowo woła open_device/start_streams;
  nie zaimplementowano jeszcze per-client automatycznego zarządzania USB
  i dynamicznego wybierania uruchamianych strumieni.
- W trybie --frame-preview rośnie zużycie RAM i przepustowość pamięci.
  Dopiero lokalny test pokaże wpływ na wydajność.
- Nie zmieniamy mostów RGB/IR/Depth V4L2 i audio ALSA ani kontrolera
  ekspozycji.
- FPS okien (renderowanie) nie oznacza dokładnie FPS urządzenia.
  Rzeczywisty RGB osiągał ~15 FPS przy słabym świetle i 30 FPS
  przy mocnym oświetleniu. IR i Depth ~30 FPS w obu warunkach.

**Nie scalać wyłącznie po CI:** potrzebny test na rzeczywistym sprzęcie
i czterech otwartych oknach oraz ocena CPU i pamięci.
