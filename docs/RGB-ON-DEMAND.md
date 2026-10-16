# Kamera RGB 1080p on-demand

Stan po testach z 16 października 2026. Aktualna implementacja: `src/kinect_rgb_bridge.cpp`, `webcam/*.sh`.

- Producent (user service) otwiera `/dev/video11` (v4l2loopback), ale **fizyczny Kinect** otwiera dopiero przy aktywnym odbiorze.
- Wyjściowe RGB: 1920×1080, YUYV422. Zamykanie sensora po ok. 5 sekundach bez odbiorców, czarna klatka po zatrzymaniu.
- `v4l2loopback` musi obsługiwać `V4L2_EVENT_PRI_CLIENT_USAGE`; sprawdź `bin/kinect_rgb_bridge --probe /dev/video11` po zbudowaniu.
- RGB oraz `./kinect2 run`, `./kinect2 depth` i `./face3d` **nie mogą równocześnie przejąć fizycznego USB**. Most trzyma wspólną blokadę jedynie podczas aktywnego odczytu sensora. To ograniczenie rozwiąże planowany broker IPC.

## Instalacja (tylko po sprawdzeniu komend)

Upewnij się, że zależności są zainstalowane, a własna kopia `libfreenect2-omp` jest zbudowana obok repozytorium. Najpierw zatrzymaj inne programy używające sensora. Na Arch Linux potrzebujesz modułu `v4l2loopback` zgodnego z działającym kernelem, narzędzia `v4l2loopback-ctl` i kompilatora C++.

```bash
bash webcam/build.sh
sudo bash webcam/install-device.sh  # tworzy systemową usługę i /dev/video11
bash webcam/install-user.sh         # rejestruje usługę użytkownika
systemctl --user status kinect2-rgb-webcam.service --no-pager
```

Powyższe instalatory **modyfikują** `/etc/systemd/system` i `~/.config/systemd/user`, włączają usługi oraz tworzą `~/.local/bin/kinect2-rgb-run`. Zajrzyj do skryptów przed uruchomieniem. Usługa `kinect2-rgb-device.service` służy do tworzenia wirtualnej kamery.

## Diagnostyka bez otwierania fizycznego USB

```bash
./kinect2 status
./kinect2 clients
./kinect2 status --json
journalctl --user -u kinect2-rgb-webcam.service -n 30 --no-pager
```

`streaming_clients` i `sensor_streaming` są stanem mostu, nie niezależnym dowodem dekodowania obrazu u odbiorcy. `openers` wykrywa deskryptory, ale nie mówi, czy proces rzeczywiście czyta klatki. Diagnostyka rozróżnia świeży stan `bridge_runtime` i historyczny `journal_last_known`.

Jeśli Firefox pokazuje obraz, ale `ffplay` jest czarny, sprawdź osobno strumień przez FFmpeg (to obserwowany problem klienta, nie automatycznie awaria mostu):

```bash
ffmpeg -hide_banner -f v4l2 -input_format yuyv422 -video_size 1920x1080 -framerate 30 \
  -i /dev/video11 -vf 'select=gte(n\,60)' -frames:v 1 -update 1 -y /tmp/kinect-rgb-test.png
```

## Powrót i wyłączenie

Przed aktualizacją skopiuj **własną** działającą wersję plików i zanotuj stan usług. Aby tylko wyłączyć auto-start usługi użytkownika:

```bash
systemctl --user disable --now kinect2-rgb-webcam.service
```

Nie usuwaj automatycznie `/dev/video10`, nie wyładowuj globalnego `v4l2loopback` ani nie nadpisuj innych kamer. W przypadku błędu przywróć pliki przez Git i zrestartuj usługę użytkownika.
