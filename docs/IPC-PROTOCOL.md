# Kinect2-Linux — lokalny protokół IPC v1

**Stan:** implementacja pierwszego brokera C++ **bez dostępu do urządzenia** oraz klienta Pythona obsługującego wyłącznie `ping` i `get_status`. Nie ma jeszcze wspólnego otwarcia USB, strumieniowania klatek ani integracji z działającymi mostami. Żaden z nich nie jest zmieniany.

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
{"protocol_version":1,"request_id":2,"ok":true,"result":{"state":"unavailable","sensor_open":false,"reason":"sensor_backend_not_implemented"}}
```

**To status prototypu brokera, nie fizycznego Kinecta.** Nieznana operacja daje `ok: false` i `error.code: "unknown_operation"`. Uszkodzona ramka, niepoprawne UTF-8/JSON, duplikaty kluczy, `NaN`/`Infinity`, zła wersja lub błędne typy są odrzucane przez zamknięcie połączenia bez odpowiedzi. Jedno żądanie przypada na jedno połączenie.

## Bezpieczeństwo i ograniczenia

- Socket powstaje wyłącznie w prywatnym katalogu `0700` należącym do bieżącego użytkownika; sam socket ma `0600`. Domyślna ścieżka: `$XDG_RUNTIME_DIR/kinect2-broker.sock`. Parametr `--socket` umożliwia własną ścieżkę.
- Weryfikacja tożsamości klienta: Linux `SO_PEERCRED`; na tym etapie dopuszczany jest tylko ten sam UID co proces brokera.
- Maksymalny payload 65536 bajtów, zagnieżdżenie JSON do 32 poziomów, timeout I/O 2 s.
- Proces nie nadpisuje istniejącej ścieżki socketu. Przy SIGINT/SIGTERM sprząta własny socket; po SIGKILL może pozostać nieczynny plik socketu, który wymaga ręcznego sprawdzenia.
- Ta wersja **obsługuje klientów sekwencyjnie**. Nie ma jeszcze równoczesnej transmisji klatek, zaawansowanego backpressure, kontroli sesji ani gotowego serwera produkcyjnego.
- Broker nie potrzebuje roota. Nie uruchamiaj go z `sudo` i nie traktuj jako komponentu uwierzytelniania biometrycznego.

## Dane sensora — odrębny kanał (plan)

JSON służy **tylko** do sterowania i metadanych, nie do transportu obrazu lub PCM. Przyszły kanał danych będzie binarny, z jawnie określoną własnością buforów (najpierw bezpieczna kopia, potencjalnie `memfd`/`mmap` i przekazywanie FD po pomiarach).

| Strumień | Surowy format w docelowym SDK | Różnica względem obecnego prototypu |
| --- | --- | --- |
| RGB | 1920×1080, format libfreenect2, np. BGRX | V4L2 `/dev/video11` ma skonwertowane YUYV |
| IR | 512×424, `float32` | V4L2 `/dev/video10` prezentuje obraz przeskalowany do YUYV |
| Depth | 512×424, `float32`, Z w milimetrach | wartości 0/NaN/Inf mogą być nieprawidłowe |
| Audio | 4 kanały, 16 kHz, `S32_LE` | osobny podsystem ALSA, bez gwarancji synchronizacji z wideo |

Docelowe metadane będą zawierać format, stride, numer sekwencji, znacznik czasu sensora (jednostka i źródło) i czas hosta. Równoczesne RGB/IR/Depth wymaga dopiero rzeczywistego brokera USB.

## Kompilacja i uruchomienie bez Kinecta

Wymagany jest kompilator obsługujący **C++23** oraz systemowy pakiet nagłówkowy **nlohmann/json** (nie kopiujemy kodu zależności do repozytorium). Przykładowa instalacja na Arch Linux: `sudo pacman -S --needed gcc nlohmann-json`; na Ubuntu: `sudo apt-get install g++ nlohmann-json3-dev`. GitHub Actions instaluje zależność przed kompilacją.

C++ korzysta z `nlohmann/json` do parsowania i tworzenia komunikatów. Callback waliduje duplikaty kluczy w każdym obiekcie i ogranicza zagnieżdżenie do 32 poziomów. Limit rozmiaru i sprawdzanie schematu nie zależą od konfiguracji parsera.

```bash
bash tools/build_broker.sh
./bin/kinect2-broker
# W drugim terminalu:
PYTHONPATH=sdk/python python3 -c 'from kinect2_linux import BrokerClient; c=BrokerClient(); print(c.ping(), c.get_status())'
```

`XDG_RUNTIME_DIR` powinien wskazywać prywatny katalog; w przeciwnym razie ustaw własną ścieżkę w `--socket` i `BrokerClient(socket_path=...)`. `Ctrl+C` kończy serwer. Testy integracyjne uruchamiają się offline poprzez `KINECT2_BROKER_BIN="$PWD/bin/kinect2-broker" python3 -m unittest discover -s tests -v`.
