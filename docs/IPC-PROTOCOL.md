# Kinect2-Linux — lokalny protokół IPC v1

**Stan:** broker C++23 obsługuje `ping`, `get_status` i odczyt obecności Kinecta przez `list_devices`. Domyślny broker używa wyłącznie sysfs i **nie otwiera USB**. Opcjonalny broker sprzętowy obsługuje `open_device`/`close_device` z `libfreenect2` po wyraźnej zgodzie użytkownika. Nie ma jeszcze strumieniowania ani integracji z działającymi mostami. Żaden z nich nie jest zmieniany.

## Kanał sterowania (zaimplementowany)

Transport: lokalny Unix `AF_UNIX` / `SOCK_STREAM`. Wiadomość: cztery bajty długości `uint32` big-endian, następnie UTF-8 JSON (1–65536 bajtów). Każda wiadomość musi być obiektem z polem `"protocol_version": 1`. Żądanie wymaga pól `request_id` (nieujemna liczba całkowita, maksymalnie 16 cyfr), `op` (string) i `params` (obiekt).

Przykład żądania:

```json
{"protocol_version":1,"request_id":1,"op":"ping","params":{}}
```

Odpowiedź:

```json
{"protocol_version":1,"request_id":1,"ok":true,"result":{"pong":true}}
```

`get_status` zwraca obecnie:

```json
{"protocol_version":1,"request_id":2,"ok":true,"result":{"state":"unavailable","sensor_open":false,"reason":"sensor_backend_not_implemented","usb_detection":{"source":"sysfs","scan_ok":true,"device_count":0}}}
```

Dla `get_status` odpowiedź zawiera też pole `usb_detection` z wartościami `source: "sysfs"`, `scan_ok: bool` i `device_count: int`. Pole `state: "unavailable"` pozostaje dla domyślnego brokera. W jawnie uruchomionym wariancie sprzętowym stan może wynosić `idle` lub `open` (uchwyt USB), lecz `streaming` nadal jest `false`.

Operacja `list_devices` zwraca wyłącznie wynik wykrywania obecności urządzenia:

```json
{"protocol_version":1,"request_id":3,"ok":true,"result":{"source":"sysfs","scan_ok":true,"devices":[{"sysfs_name":"1-2","vendor_id":"045e","product_id":"02c4"}]}}
```

Dane przykładowe powyżej **nie oznaczają**, że CI wykrył fizycznego Kinecta. `devices: []` jest prawidłową odpowiedzią, jeżeli sprzęt nie jest podłączony; `scan_ok: false` sygnalizuje niemożność przeglądania katalogu sysfs i **nie może** być interpretowane jako brak urządzeń. Lista odświeża się przy każdym zapytaniu (najprostsza obsługa hotplug). Nazwa sysfs to lokalizacja urządzenia w USB, **bez numeru seryjnego**, adresu pamięci ani danych biometrycznych.

**To status prototypu brokera, nie fizycznego Kinecta.** Nieznana operacja daje `ok: false` i `error.code: "unknown_operation"`. Uszkodzona ramka, niepoprawne UTF-8/JSON, duplikaty kluczy, `NaN`/`Infinity`, zła wersja lub błędne typy są odrzucane przez zamknięcie połączenia bez odpowiedzi. Jedno żądanie przypada na jedno połączenie.

## Bezpieczeństwo i ograniczenia

- Socket powstaje wyłącznie w prywatnym katalogu `0700` należącym do bieżącego użytkownika; sam socket ma `0600`. Domyślna ścieżka: `$XDG_RUNTIME_DIR/kinect2-broker.sock`. Parametr `--socket` umożliwia własną ścieżkę.
- Weryfikacja tożsamości klienta: Linux `SO_PEERCRED`; na tym etapie dopuszczany jest tylko ten sam UID co proces brokera.
- Maksymalny payload 65536 bajtów, zagnieżdżenie JSON do 32 poziomów, timeout I/O 2 s.
- Proces nie nadpisuje istniejącej ścieżki socketu. Przy SIGINT/SIGTERM sprząta własny socket; po SIGKILL może pozostać nieczynny plik socketu, który wymaga ręcznego sprawdzenia.
- Ta wersja **obsługuje klientów sekwencyjnie**. Nie ma jeszcze równoczesnej transmisji klatek, zaawansowanego backpressure, kontroli sesji ani gotowego serwera produkcyjnego.
- Broker nie potrzebuje roota. Nie uruchamiaj go z `sudo` i nie traktuj jako komponentu uwierzytelniania biometrycznego.

## Opcjonalne sterowanie fizycznym uchwytem USB

Operacje `open_device` i `close_device` wymagają pustego obiektu `params` i jawnej kompilacji `--with-hardware` oraz uruchomienia `--allow-device-control`. Domyślny broker zwraca błąd `device_control_disabled`; wariant sprzętowy współdzieli blokadę `kinect2-sensor.lock` z istniejącymi mostami. Nie startuje streamów. Szczegółowe ograniczenia i instrukcja testu na Arch Linux: [DEVICE-CONTROL.md](DEVICE-CONTROL.md).

## Dane sensora — odrębny kanał (plan)

JSON służy **tylko** do sterowania i metadanych, nie do transportu obrazu lub PCM. Przyszły kanał danych będzie binarny, z jawnie określoną własnością buforów (najpierw bezpieczna kopia, potencjalnie `memfd`/`mmap` i przekazywanie FD po pomiarach).

| Strumień | Surowy format w docelowym SDK | Różnica względem obecnego prototypu |
| --- | --- | --- |
| RGB | 1920×1080, format libfreenect2, np. BGRX | V4L2 `/dev/video11` ma skonwertowane YUYV |
| IR | 512×424, `float32` | V4L2 `/dev/video10` prezentuje obraz przeskalowany do YUYV |
| Depth | 512×424, `float32`, Z w milimetrach | wartości 0/NaN/Inf mogą być nieprawidłowe |
| Audio | 4 kanały, 16 kHz, `S32_LE` | osobny podsystem ALSA, bez gwarancji synchronizacji z wideo |

Docelowe metadane będą zawierać format, stride, numer sekwencji, znacznik czasu sensora (jednostka i źródło) i czas hosta. Równoczesne RGB/IR/Depth wymaga dopiero rzeczywistego brokera USB.

## Testowanie wykrywania bez sprzętu

Warstwa `core/sensor_backend.hpp` definiuje testowalny interfejs `SensorBackend::discover()`, a `SysfsSensorBackend` czyta tylko `/sys/bus/usb/devices/*/{idVendor,idProduct}` (dokładne dopasowanie `045e:02c4`). Nie korzysta z `libfreenect2`, nie otwiera urządzeń ani nie przejmuje już działających usług. Atrapy odczytu i scenariusze odłączania USB są testowane natywnie z tymczasowym katalogiem sysfs.

```bash
bash tools/build_broker.sh
./bin/test_sensor_backend
```

Te testy i testy Python ↔ C++ uruchamiają się w GitHub Actions bez Kinecta. **Potwierdzenie poprawności wykrywania na fizycznym sprzęcie nadal wymaga testu na Arch Linux**.

## Kompilacja i uruchomienie bez Kinecta

Wymagany jest kompilator obsługujący **C++23** oraz systemowy pakiet nagłówkowy **nlohmann/json** (nie kopiujemy kodu zależności do repozytorium). Przykładowa instalacja na Arch Linux: `sudo pacman -S --needed gcc nlohmann-json`; na Ubuntu: `sudo apt-get install g++ nlohmann-json3-dev`. GitHub Actions instaluje zależność przed kompilacją.

C++ korzysta z `nlohmann/json` do parsowania i tworzenia komunikatów. Callback waliduje duplikaty kluczy w każdym obiekcie i ogranicza zagnieżdżenie do 32 poziomów. Limit rozmiaru i sprawdzanie schematu nie zależą od konfiguracji parsera.

```bash
bash tools/build_broker.sh
./bin/kinect2-broker
# W drugim terminalu:
PYTHONPATH=sdk/python python3 -c 'from kinect2_linux import BrokerClient; c=BrokerClient(); print(c.ping(), c.get_status(), c.list_devices())'
```

`XDG_RUNTIME_DIR` powinien wskazywać prywatny katalog; w przeciwnym razie ustaw własną ścieżkę w `--socket` i `BrokerClient(socket_path=...)`. `Ctrl+C` kończy serwer. Testy integracyjne uruchamiają się offline poprzez `KINECT2_BROKER_BIN="$PWD/bin/kinect2-broker" python3 -m unittest discover -s tests -v`.
