> **Archiwum historyczne.** Instrukcje instalacji/patchowania w tym pliku są przestarzałe i nie należy ich stosować do aktualnej wersji projektu. Zobacz główne `README.md`.

# Kinect2-Linux — integracja Status API

Rozszerza istniejacy `./kinect2` o trzy polecenia tylko do odczytu:

- `./kinect2 status [--json]` — pelny raport, ten sam co `tools/kinect2_status.py`.
- `./kinect2 devices [--json]` — sensor USB, kamery wirtualne, domyslny mikrofon.
- `./kinect2 clients [--json]` — odbiorcy strumienia RGB, procesy z otwarta kamera, wlasciciel USB.

Pakiet **nie** podmienia launchera, nie zmienia kodu mostka i nie otwiera
sensora. Skrypt instalacyjny doklada tylko trzy podpolecenia, zachowujac
wszystkie pozostale komendy.

## Instalacja

W katalogu `~/Projekty/kinect/Kinect2-Linux`, majac juz zainstalowany
poprzedni pakiet `kinect2-status-api-mvp.zip`:

```bash
unzip -n kinect2-status-integration.zip
python3 tools/install_status_commands.py --check
python3 tools/install_status_commands.py
./kinect2 status
./kinect2 status --json
./kinect2 devices
./kinect2 clients
```

Skrypt tworzy kopie `kinect2.before-status-api` (lub kolejny numer, jesli
kopia juz istnieje). Przy ponownej instalacji nie duplikuje polecen.
Jesli `--check` zglosi blad, nie uruchamiaj instalatora.

## Zasady poprawnosci

`streaming_clients` pochodzi z ostatniego zarejestrowanego zdarzenia
mostka RGB (PID biezacej uslugi), a `last_event_at` to data ostatniej
**zmiany stanu**, nie odswiezany co sekunde pomiar. `openers` to tylko
procesy z otwartym deskryptorem urzadzenia. `clients` nie przypisuje
odbioru obrazu do konkretnych procesow bez dowodow.

## Przywrocenie poprzedniego launchera

```bash
cd ~/Projekty/kinect/Kinect2-Linux
cp -a kinect2.before-status-api kinect2
```

Jesli instalator wybral kopie z numerem, uzyj podanej przez niego nazwy.
