# Kinect2-Linux — plan przebudowy architektury

Status: **propozycja architektury**, nie wykonana migracja. Repo po czyszczeniu zachowuje stare runtime bez zmian; sam cleanup nie implementuje rdzenia. Platforma docelowa: Linux. Priorytet: niezawodność i bezpieczeństwo, następnie wydajność i wygoda API.

## Kontrakt projektu open source

- Cel: plug-and-play **docelowo**, bez obowiązkowego dostosowywania sygnału do programów osób trzecich.
- ALSA 4ch/16 kHz/S32_LE pozostaje natywnym wejściem; mono/stereo i resampling są **opcjonalnymi adapterami**.
- MediaPipe / body tracking: **wstrzymane**, nie są zależnością rdzenia. Eksperymenty Face3D/Howdy pozostają odizolowane.
- Punkt odniesienia bieżącego sprzętu opisuje [BASELINE-2026-10-16.md](BASELINE-2026-10-16.md).

## Zasady

1. **Zachować działający punkt odniesienia.** Nie zmieniać równocześnie sterownika USB, mostka V4L2, klientów IPC ani sposobu uruchamiania systemd. Każdy etap ma test powrotu do starego wariantu.
2. **Jeden właściciel fizycznego Kinecta.** Rdzeń C++ ma zarządzać otwarciem, strumieniami, buforami i dostępem do USB. V4L2, API i narzędzia stają się klientami rdzenia. Mikrofony ALSA są odrębnym podsystemem; nie zakładać ich automatycznej synchronizacji z wideo.
3. **Jeden wersjonowany protokół lokalny.** Gniazdo Unix dla poleceń i metadanych, osobna droga dla danych klatek (w pierwszej wersji bezpieczna kopia, docelowo współdzielona pamięć / fd passing po testach). Nie przekazywać surowych wskaźników między procesami.
4. **Zachować oryginalne dane i znaczniki czasu.** RGB 1920×1080, IR/Depth 512×424, surowa głębia float32, numery sekwencji, czas sensora jeśli dostępny; jasne rozróżnienie czasu sensora i czasu hosta. Bez cichego skalowania lub downmixu.
5. **Publiczny SDK ma być przenośny pomiędzy CPU, natomiast lokalny build może być zoptymalizowany pod gospodarza.** Brak twardego `-march=native` w standardowych binariach publikowanych na GitHubie.

## Komponenty po przebudowie (plan)

- `core/` — C++: jedna sesja Kinecta, stan, buforowanie, strumienie, synchronizacja i kontrola dostępu.
- `ipc/` — stabilny protokół IPC z `protocol_version`, limitami rozmiaru i kontrolą uprawnień klienta.
- `adapters/v4l2/` — kamera RGB `/dev/video11` i ewentualne wyjście IR; przejmuje klatki od rdzenia zamiast otwierać ponownie USB.
- `sdk/python/` — jedyne wysokopoziomowe API, jako klient wersjonowanego IPC; Python nie otwiera fizycznego USB. To planowany katalog, którego jeszcze nie ma.
- `ui/` — GUI Qt/Python jako klient IPC; Python nie może trzymać wyłączności na sensor.
- `tools/`, `tests/`, `docs/`, `packaging/` — diagnostyka, testy, dokumentacja, systemd, udev, DKMS.

## Strategia kompilacji

| Technologia | Build podstawowy | Build specjalistyczny |
|---|---|---|
| C++ | `Release` dla przenośnego x86-64, osobno Debug z ASan/UBSan | lokalny `-O3 -march=native`, profilowanie i opcjonalne LTO dopiero po testach |
| Python | źródła i zależności zarządzane jawnie; UI poza ścieżką krytyczną FPS | Nuitka tylko eksperymentalnie i po pomiarach; `.pyc` nie jest AOT kodu maszynowego |

Dla C++ utrzymać dwa profile: **portable** do wydania i **native-local** do testów konkretnego procesora. Python pozostaje opcjonalną warstwą kliencką, bez udziału w krytycznej ścieżce pobierania klatek; dopiero po pomiarach rozważyć optymalizację jego narzutów.

## Bezpieczeństwo i niezawodność — warunki ukończenia

- Proces sensora działa z minimalnymi uprawnieniami, bez `sudo` do codziennego przechwytywania. Uprawnienia USB i gniazda IPC są jawnie opisane.
- IPC uwierzytelnia klientów lokalnych (`SO_PEERCRED` lub równoważny mechanizm), limituje rozmiar komunikatów i maksymalną liczbę klientów. Nie traktować samego PID ani ścieżki procesu jako dowodu uprawnień.
- Czytelne stany: `disconnected`, `idle`, `starting`, `streaming`, `stopping`, `error`; status świeży albo jawnie `unknown`.
- Jeden wolny klient nie blokuje pozostałych: ograniczone kolejki, polityka odrzucania starych klatek, liczniki błędów per klient.
- Bezpieczne kończenie: SIGTERM/wyjście klienta/odłączenie USB/restart usługi/awaria odbiorcy nie zostawiają urządzenia trwale zablokowanego.
- Testy: wielokrotne hotplug, kilka klientów jednocześnie, zmiana rozdzielczości, nagły zanik USB, odtwarzanie po restarcie, brak wycieku buforów, testy fuzz protokołu, ASan/UBSan.
- Prywatność: stan i status bez zbędnych danych osobowych. Biometryczne obrazy i nagrania nie mogą trafiać do logów ani repozytorium. Wirtualna kamera **nie** jest zaufanym źródłem danych do uwierzytelniania PAM.

## Kolejność pracy i kryteria akceptacji

### 0. Zamrożenie punktu odniesienia

- [ ] Wydzielić tag/gałąź z działającym RGB on-demand i Live Status API.
- [ ] Zebrać bazowe pomiary: RGB 1080p30, IR+Depth 30 fps, sekwencje, opóźnienie rozruchu, zużycie RAM/CPU, 4 kanały audio ALSA.
- [ ] Przegląd licencji, `.gitignore` i zależności. Usunąć prywatne próbki, `.venv`, pliki binarne i logi z publicznego drzewa.

### 1. Przygotowanie kontraktów i testów Python

- [ ] Opisać kontrakty klatek RGB, IR, Depth i surowego audio 4ch: format, wymiary, jednostki, znaczniki czasu i własność buforów.
- [ ] Zaprojektować wersjonowany protokół IPC oraz obsługę błędów i anulowania klienta przed implementacją rdzenia.
- [ ] Zaprojektować małe, idiomatyczne API Python z kontekstem `with Kinect()`; do czasu wdrożenia rdzenia używać atrap/mocków w testach.
- [ ] Zachować istniejące polecenia CLI i V4L2 jako działający punkt odniesienia; Python nie może przejmować fizycznego USB.

### 2. Natywny broker sensora

- [ ] Rdzeń C++ przejmuje jedyne otwarcie USB, istniejące mostki korzystają z IPC.
- [ ] RGB wideo i `status` zachowują bieżącą funkcjonalność (on-demand, wygaszenie po 5 sekundach).
- [ ] Dwóch niezależnych klientów może odbierać RGB bez `Device or resource busy`.
- [ ] Bufory i klatki zachowują rozdzielczość, format, liczniki i jawny backpressure.

### 3. Rozszerzenia SDK 2.0

- [ ] Udostępnić równocześnie IR+Depth i RGB przez rdzeń; wykonać mapowanie i kalibrację RGB↔Depth.
- [ ] Dopracować 4-kanałowe audio i osobne API kierunku głosu; nie downmixować surowych danych.
- [ ] Śledzenie ciała, dłoni i twarzy jako **oddzielne moduły obliczeniowe**, nie część sterownika USB.
- [ ] Dopiero po testach bezpieczeństwa rozważyć integrację z mechanizmem uwierzytelniania (PAM).

## Zasada przyjmowania zmian

Każdy etap musi dać: powtarzalny build, testy automatyczne, próbę na fizycznym Kinekcie, pomiar wydajności przed/po, możliwość wycofania oraz dokumentację. **Sama kompilacja nie jest kryterium jakości.**
