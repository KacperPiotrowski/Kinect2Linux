# Kinect2-Linux — projekt lokalnego protokołu IPC v1

**Status: pierwszy kontrakt i testowany kodek Python. Brak serwera C++ i działającego klienta SDK.** Wprowadzenie tego dokumentu nie zmienia dotychczasowego dostępu RGB, IR, Depth ani audio.

## Kanał sterowania

Docelowy transport: lokalny Unix `SOCK_STREAM` (brak TCP ani zdalnego dostępu). Każda wiadomość to 4-bajtowa, **big-endian** długość `uint32`, a po niej dokładnie tyle bajtów UTF-8 JSON. Długość JSON od 1 do **65536 bajtów**; większe komunikaty i puste ramki są odrzucane przed alokacją payloadu. Każdy komunikat jest obiektem JSON z `"protocol_version": 1`. Błędna wersja, składnia, nie-UTF-8, niepełny odczyt, zduplikowane klucze i niedozwolone wartości `NaN` / `Infinity` oznaczają błąd protokołu.

Planowany wzór żądania (serwer **jeszcze nie istnieje**):

```json
{"protocol_version":1,"request_id":1,"op":"get_status","params":{}}
```

Planowany wzór odpowiedzi:

```json
{"protocol_version":1,"request_id":1,"ok":true,"result":{"state":"idle"}}
```

`request_id` wiąże odpowiedź z żądaniem. Nazwy operacji, struktury błędów i pola danych wymagają jeszcze zatwierdzenia oraz testów interoperacyjności C++/Python. JSON służy **wyłącznie** do sterowania i metadanych: nigdy nie wkładamy klatek obrazu ani surowego audio do JSON. Kanał danych/klatek (bezpieczna kopia, potem ewentualnie `memfd` i przekazywanie FD) zostanie określony osobno, przed implementacją brokera.

Docelowy serwer powinien sprawdzać uprawnienia lokalnego klienta (np. `SO_PEERCRED`), ograniczać liczbę klientów, timeouty, wielkości ramek i wykorzystanie pamięci. Sam kodek Pythona **nie** realizuje tych zabezpieczeń po stronie serwera.

## Format klatek w przyszłym API

| Strumień | Dane pierwotne sensora | Ważne rozróżnienie |
| --- | --- | --- |
| Color | 1920×1080, format z libfreenect2 (np. BGRX 8-bit) | obecna kamera V4L2 dostarcza przekonwertowane **YUYV422**, a nie pierwotny BGRX |
| IR | 512×424, `float32`, amplituda/intensywność IR | V4L2 `/dev/video10` pokazuje obraz po normalizacji do YUYV; nie traktować go jako surowego IR |
| Depth | 512×424, `float32`, oś Z w **milimetrach** | brak danych / wartości nieprawidłowe są możliwe, np. 0/NaN/Inf |
| Audio | 4 kanały, 16000 Hz, `S32_LE`, bez downmixu | ALSA jest odrębnym subsystemem; brak gwarancji synchronizacji z wideo |

Metadane klatki będą określać m.in. typ strumienia, rzeczywisty format pikseli, wymiary, stride, numer sekwencji, timestamp sensora wraz z jego jednostką (jeżeli znana) oraz czas monotoniczny hosta. Własność i czas życia bufora muszą być jawne. IR i Depth mogą tworzyć parę wyłącznie przy zgodnych znacznikach/numerach z tej samej sesji. Nie zakładamy współbieżnego poboru RGB+IR/Depth przed wdrożeniem jednego natywnego brokera.

## Zakres tego etapu

Moduł `sdk/python/kinect2_linux/ipc.py` implementuje tylko kodowanie i bezpieczne odbieranie komunikatów sterujących. Testy `tests/test_ipc_protocol.py` działają bez urządzenia, `libfreenect2`, NumPy, MediaPipe i .NET. Docelowe API `with Kinect() as sensor:` pozostaje planem, a nie dostępną funkcją.
