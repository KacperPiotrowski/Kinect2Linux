# Kinect v2 RGB — tryb na żądanie (eksperymentalny)

Dla działającej instalacji Kinect2-Linux /dev/video11 Full HD, po poprawce 1080p.
Nie rusza `/dev/video10`, Howdy, PAM ani urządzeń systemowych.

## Zachowanie

- Stały, lekki proces usługi ma otwarte **wyłącznie wirtualne** `/dev/video11`.
- Sensor Kinect v2 pozostaje zamknięty do czasu, kiedy odbiorca zaczyna faktyczne przechwytywanie obrazu.
- `v4l2loopback` emituje prywatne zdarzenia `V4L2_EVENT_PRI_CLIENT_USAGE`. To wymaga obsługi ze strony zainstalowanego modułu jądra; do testu służy `--probe`.
- Po pięciu sekundach od zakończenia ostatniego przechwytywania Kinect przestaje streamować, jest zamykany, a blokada USB jest zwalniana. Na wyjście zapisujemy czarną klatkę (żeby nie zostawić obrazu ostatniego użytkownika).
- Fizyczny Kinect pozostaje włączony, jeśli jakiś program *utrzymuje otwarty strumień* kamery, nawet bez widocznego podglądu. Testy przeglądarki, OBS i aplikacje działające w tle mogą tak robić.
- Nie jest gwarantowane, że każde oprogramowanie natychmiast aktywuje taki wirtualny strumień. Nie przetestowano tego pakietu na fizycznym Kinekcie użytkownika.

## Instalacja bezpieczna, krok po kroku

Umieść ZIP w katalogu projektu. Możesz przygotować nowe pliki i sprawdzić obsługę zdarzeń *bez zatrzymywania starej usługi*, dzięki atomowemu podmienianiu pliku wykonywalnego przez `webcam/build.sh`.

```bash
cd ~/Projekty/kinect/Kinect2-Linux
cp -a src/kinect_rgb_bridge.cpp src/kinect_rgb_bridge.cpp.before-ondemand
cp -a webcam/build.sh webcam/build.sh.before-ondemand
cp -a webcam/run.sh webcam/run.sh.before-ondemand
cp -a bin/kinect_rgb_bridge bin/kinect_rgb_bridge.before-ondemand
unzip -o kinect2-rgb-on-demand.zip
bash webcam/build.sh
bin/kinect_rgb_bridge --probe /dev/video11
```

Jeśli test zwróci **OK** — dopiero teraz uruchom nową wersję usługi:

```bash
systemctl --user restart kinect2-rgb-webcam.service
journalctl --user -u kinect2-rgb-webcam.service -n 25 --no-pager -l
```

W spoczynku szukaj wpisu `Kinect RGB webcam ready ... (on-demand, Kinect OFF)` i sprawdź, czy sensor się wyłączył. Następnie otwórz test kamerki internetowej: powinny pojawić się `Camera clients streaming: 1` oraz `Kinect ON...`. Po zamknięciu testu i około pięciu sekundach powinno pojawić się `STANDBY: Kinect OFF`.

## Powrót do poprzedniej działającej wersji

```bash
cd ~/Projekty/kinect/Kinect2-Linux
systemctl --user stop kinect2-rgb-webcam.service
cp -a src/kinect_rgb_bridge.cpp.before-ondemand src/kinect_rgb_bridge.cpp
cp -a webcam/build.sh.before-ondemand webcam/build.sh
cp -a webcam/run.sh.before-ondemand webcam/run.sh
cp -a bin/kinect_rgb_bridge.before-ondemand bin/kinect_rgb_bridge
systemctl --user start kinect2-rgb-webcam.service
```

## Uwaga

Nowy mostek oczekuje zmiennej `KINECT_RGB_LOCK` ustawianej przez dołączony `webcam/run.sh`. Trzymamy ten sam plik blokady (`$XDG_RUNTIME_DIR/kinect2-sensor.lock`) co Face3D, ale tylko podczas fizycznego odczytu z Kinecta, a nie podczas bezczynności.

Uwaga: `--probe` **testuje możliwość subskrypcji zdarzeń, nie testuje jeszcze ich prawidłowego działania w konkretnej przeglądarce**. W razie problemu należy wycofać poprawkę powyższymi poleceniami.
