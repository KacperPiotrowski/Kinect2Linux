# Kinect2-Linux — kontrolowane otwieranie Kinecta (eksperymentalne)

**PR #7: tylko zarządzanie uchwytem USB przez libfreenect2, bez startowania RGB, IR, Depth, V4L2, ALSA i systemd.** Żaden ze starych mostów nie został zmieniony. Samo wykrywanie sysfs i działanie zwykłego brokera nie otwiera USB.

## Dwa oddzielne buildy

Zwykła kompilacja i testy offline (bez libfreenect2 i bez Kinecta):

```bash
bash tools/build_broker.sh
./bin/test_sensor_backend
./bin/test_device_session
./bin/kinect2-broker
```

Ten broker **zawsze** odmawia `open_device` kodem `device_control_disabled`, nawet gdy Kinect jest podłączony.

Jawnie włączana kompilacja do ręcznych testów na Linuksie:

```bash
LIBFREENECT2_DIR="$PWD/../libfreenect2-omp" bash tools/build_broker.sh --with-hardware
```

Wymaga istniejącego `build-omp/lib/libfreenect2.so`, nagłówków tego samego drzewa i systemowego `nlohmann/json`. Powstaje **osobny** plik `bin/kinect2-broker-hw` z rpath do lokalnej biblioteki. Ten wariant **nadal nie otworzy USB**, jeśli nie zostanie uruchomiony z flagą `--allow-device-control`.

## Ręczny test sprzętowy — tylko za zgodą użytkownika

1. Zakończ dotychczasowego `./bin/kinect2-broker` (Ctrl+C). Sprawdź `./kinect2 clients`. Zatrzymaj przechwytywanie z `./kinect2 run` / `./kinect2 depth` oraz działającą usługę RGB, **jeśli jest aktywna**. Nie wyłączamy tych usług automatycznie. Nie włączaj `sudo`.
2. Upewnij się, że `XDG_RUNTIME_DIR` jest ustawione, a `$XDG_RUNTIME_DIR/kinect2-sensor.lock` to wspólna blokada używana przez stare mosty. `open_device` używa `flock(LOCK_EX|LOCK_NB)` i zwraca `device_busy`, jeśli blokada jest już zajęta.
3. W pierwszym terminalu uruchom jawnie tryb sprzętowy:

```bash
./bin/kinect2-broker-hw --allow-device-control
```

4. W drugim terminalu, z repo jako katalogu bieżącego:

```bash
PYTHONPATH=sdk/python python3 - <<'PY'
from kinect2_linux import BrokerClient

client = BrokerClient(timeout=20)
try:
    print("BEFORE:", client.get_status())
    print("OPEN:", client.open_device())
    print("DURING:", client.get_status())
finally:
    print("CLOSE:", client.close_device())
    print("AFTER:", client.get_status())
PY
```

`get_status().state` zmienia się między `idle` a `open`, `sensor_open` między `false` i `true`, a `streaming` **pozostaje false**. `open` oznacza posiadanie uchwytu, nie działający obraz ani potwierdzenie ciągłej dostępności urządzenia. Po zakończeniu możesz znów używać dotychczasowych mostów.

**Jeśli `open_device` zwróci `device_busy`, nie zatrzymuj losowych procesów i nie kasuj pliku blokady.** Sprawdź kto używa urządzenia. Jeśli `open_failed` lub `no_device`, przeanalizuj dostęp USB i logi bez eskalacji uprawnień.

## Semantyka i ograniczenia

- `open_device`: wyłącznie w procesie uruchomionym z `--allow-device-control`; nabywa wspólną blokadę, następnie otwiera domyślne urządzenie znalezione przez `libfreenect2`. Nie uruchamia strumieni; drugie otwarcie zwraca `already_open`.
- `close_device`: idempotentnie zamyka urządzenie **przed** zwolnieniem blokady; zasoby są zwalniane również przy poprawnym zamknięciu procesu (SIGINT/SIGTERM). Przy awarii procesu kernel zamknie jego deskryptory. Po brutalnym odłączeniu USB konieczne są dodatkowe testy sprzętowe.
- Obie operacje wymagają pustego obiektu `params`. Bez opt-in odpowiadają `device_control_disabled`. Błędy mają stabilne `error.code`: `device_busy`, `already_open`, `no_device`, `open_failed`, `lock_error` lub `unsafe_lock_path`.
- Broker na tym etapie działa **sekwencyjnie**, a otwieranie przez libfreenect2 może blokować obsługę kolejnych zapytań. To etap diagnostyczny, nie produkcyjny daemon z wieloma klientami. Użytkownicy tego samego UID mają te same uprawnienia IPC i mogą zamknąć wspólną sesję; per-client leases jeszcze nie istnieją.
- Sama blokada jest **advisory**. Chroni przed współpracującymi mostami, ale nie przed obcymi procesami, które ją ignorują. Urządzenie zawsze może odmówić otwarcia. Nie zmieniamy udev, PAM, uprawnień ani systemd.

## Testy bez sprzętu

W CI natywny `test_device_session` korzysta z fałszywego `HardwareDevice`. Weryfikuje: cykl otwórz/zamknij, ponowne otwarcie, wzajemne wykluczanie `flock`, błędne otwarcie, RAII w destruktorze, ścieżki z symlinkami, uprawnienia katalogu i brak backendu. Integracja Python↔C++ sprawdza, że zwykły broker nigdy nie przejmuje USB. **W CI nie kompilujemy wariantu libfreenect2 ani nie możemy potwierdzić działania sprzętowego.**
