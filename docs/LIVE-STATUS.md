# Kinect2-Linux: odczyt statusu RGB na żywo (eksperymentalny)

Zasada: **sensor nie jest otwierany przez polecenia diagnostyczne**.
Usługa RGB nadal udostępnia `/dev/video11` w 1920×1080 YUYV. Ten patch
nie zmienia mapowania obrazu, zarządzania energią ani istniejącej blokady USB.

## Jak działa

Uruchomiony `kinect_rgb_bridge` publikuje aktualny stan w pliku:

`$XDG_RUNTIME_DIR/kinect2-rgb-state.json`

Plik jest aktualizowany atomowo, tylko dla użytkownika (`0600`), średnio
raz na sekundę oraz po zmianie stanu. Nie jest umieszczany w repozytorium Git.
Zawiera PID procesu, znacznik monotoniczny, informację o strumieniowaniu,
liczbę aktywnych odbiorców oraz liczniki klatek i strat wyjściowych.

`./kinect2 status --json` akceptuje go tylko wtedy, gdy:

- usługa użytkownika jest aktywna;
- PID pliku odpowiada `MainPID` usługi;
- dane nie są starsze niż 3 sekundy ani nie pochodzą z przyszłości;
- plik jest regularny, niewielki i należy do bieżącego użytkownika.

Jeżeli odczyt jest niedostępny, pozostaje poprzedni odczyt z `journalctl`,
ale oznaczony `state_source: "journal_last_known"`, `state_fresh: false`.
Jeśli brak obu źródeł, stan strumienia to `null` (nieznany).

Nowe pola w `rgb`:

- `state_source`: `bridge_runtime`, `journal_last_known` lub `unknown`;
- `state_fresh`: `true`/`false`;
- `state_age_ms`, `state_updated_at` — świeżość zapisu mostka;
- `capture_stats`: `frames`, `seq_gaps`, `output_drops` (dla bieżącej sesji strumienia).

Nie zmieniono `schema_version=1`; stare pola pozostały dostępne.
`./kinect2 clients --json` przekazuje te pola dalej.

**Uwaga:** `streaming_clients` opisuje liczbę odbiorców zgłoszoną przez
`v4l2loopback`, a `openers` opisuje deskryptory wykryte w `/proc` — to
nie jest pewna identyfikacja aplikacji nagrywającej. Ani stan pliku,
ani kontrola kamerki nie zastępują systemowych zabezpieczeń prywatności.

## Wdrożenie

Patch jest przygotowany na:

- `src/kinect_rgb_bridge.cpp` z paczki **on-demand** i późniejszą poprawką
  `ENOENT`;
- `webcam/run.sh` z paczki **on-demand**;
- `tools/kinect2_status.py` z pierwszego Status API;
- `tools/kinect2_inspect.py` z integracji `status/devices/clients`.

Z katalogu projektu:

```bash
cp -a bin/kinect_rgb_bridge bin/kinect_rgb_bridge.before-live-status
git apply --check kinect2-live-status.patch
git apply kinect2-live-status.patch
python3 -m unittest discover -s tests -p test_live_status.py -q
bash webcam/build.sh
systemctl --user restart kinect2-rgb-webcam.service
./kinect2 status --json
./kinect2 clients --json
```

W razie konfliktu patcha **nie wymuszaj jego nałożenia**. Fizycznego
sensora nie testowano w środowisku budowania tej poprawki.

### Przywrócenie

Przy zatrzymanej usłudze:

```bash
systemctl --user stop kinect2-rgb-webcam.service
cp -a bin/kinect_rgb_bridge.before-live-status bin/kinect_rgb_bridge
git apply -R kinect2-live-status.patch
systemctl --user start kinect2-rgb-webcam.service
```

W przypadku konfliktów przy cofaniu patcha przywróć pliki źródłowe z
lokalnego Git/kopii, nie kasuj ich w ciemno.

## Przed publikacją GitHub

Nie wrzucaj nagrań twarzy IR/RGB, próbek biometrycznych, plików
`enrollments`, prywatnych WAV, logów zawierających identyfikatory USB,
folderów `.venv*`, lokalnych bibliotek i skompilowanych binariów.
`libfreenect2`, model dlib, Howdy oraz inne zależności mają własne licencje.
Projekt nie zawiera i nie powinien udawać kodu Microsoft Kinect SDK 2.0.
