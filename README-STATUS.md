# Kinect2-Linux — Read-only status API (MVP 0.1)

To jest **eksperymentalny, samodzielny odczyt stanu** istniejącej instalacji
Kinect2-Linux. Nie uruchamia sensora, nie zmienia PAM, kamer, USB, PipeWire,
modułów jądra ani usług systemd. Działa bez dodatkowych bibliotek Python.

## Instalacja

Rozpakuj ZIP w katalogu `~/Projekty/kinect/Kinect2-Linux` (nie nadpisuje
istniejących plików projektu), następnie:

```bash
python3 tools/kinect2_status.py
python3 tools/kinect2_status.py --json
python3 -m unittest discover -s tests -p 'test_kinect2_status.py' -q
```

Docelowo można podpiąć odczyt pod `./kinect2 status [--json]`, ale ten
prototyp celowo **nie modyfikuje aktualnego launchera**.

## Co zwraca

- `device.connected` i `device.sensors`: rozpoznanie fizycznego Kinecta v2
  (USB VID:PID `045e:02c4`) w sysfs, bez otwierania urządzenia.
- `rgb`: urządzenie `/dev/video11`, stan usługi, PID procesu mostka oraz
  ostatnia zaobserwowana liczba odbiorców i stan strumienia z **logów
  aktualnego procesu usługi**. `null` oznacza brak wiarygodnego odczytu.
- `rgb.openers`: widoczne w `/proc` procesy **z otwartym deskryptorem**
  `/dev/video11`. To NIE musi oznaczać, że oglądają klatki. Dostęp do
  cudzych procesów może być ograniczony; przy PipeWire/portalach można
  zobaczyć pośrednika zamiast docelowej aplikacji.
- `ir`: obecność wirtualnego `/dev/video10`, nie stan IR sensora.
- `audio.default_source`: domyślny mikrofon, liczba jego kanałów według
  WirePlumber; **nie** dowód na aktywne nagrywanie dźwięku.
- `usb_lock`: stan wspólnego `flock`, ewentualny PID procesu trzymającego
  blokadę (jeśli kernel udostępnia go w `/proc/locks`). Brak blokady nie
  dowodzi, że jakiś niepowiązany program nie otworzył fizycznego USB.

## Czego jeszcze NIE dostarcza

- Pełnej identyfikacji „która aplikacja używa kamery” (PipeWire/portal).
- Wspólnego brokera RGB+IR+Depth i śledzenia klientów na poziomie SDK.
- Gwarantowanej spójności w czasie — to chwilowy odczyt wielu źródeł.

Przy docelowym SDK sensowne jest oddzielne, read-only API IPC Unix socket
lub D-Bus, aktualizowane bezpośrednio przez proces zarządzający sensorem.
Dopiero taki manager będzie mógł wiarygodnie znać wszystkich swoich klientów.
