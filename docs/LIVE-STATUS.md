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

## Stan bieżący

Obsługa jest już w kodzie mostu, a odczyt w `tools/kinect2_status.py` i `tools/kinect2_inspect.py`. Nie nakładaj dawnych patchy `kinect2-live-status.patch` ani nie przywracaj plików `*.before-live-status` z dokumentów historycznych. Aktualizacje wykonuj przez Git, a następnie testy offline i sprzętowe. Zobacz [STATUS.md](STATUS.md).
