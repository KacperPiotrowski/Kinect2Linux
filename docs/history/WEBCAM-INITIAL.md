> **Archiwum historyczne.** Instrukcje instalacji/patchowania w tym pliku są przestarzałe i nie należy ich stosować do aktualnej wersji projektu. Zobacz główne `README.md`.

# Kinect2-Linux — kolorowa kamera systemowa (RGB)

**Wersja eksperymentalna, do testu na Twoim Arch Linux / KDE Wayland.**
Dodatek nie modyfikuje `kinect2`, `face3d`, `/dev/video10`, Howdy ani PAM.
Wykorzystuje `libfreenect2-omp` do pobrania RGB 1920×1080 i wysyła
YUYV 1280×720 / do 30 FPS do wirtualnej kamery **`/dev/video11`**.

## Instalacja (raz)

1. Rozpakuj pliki ZIP **w katalogu istniejącego `Kinect2-Linux`**.
2. Zakończ ręczne `./kinect2 run`, `./face3d` i procesy przejmujące sensor.
3. W terminalu w katalogu projektu wykonaj:

```bash
sudo pacman -S --needed v4l2loopback-utils
bash webcam/build.sh
sudo bash webcam/install-device.sh
bash webcam/install-user.sh
```

Skrypt uruchomiony jako root instaluje wyłącznie **własną** usługę
`kinect2-rgb-device.service` i nie zmienia konfiguracji istniejącego
`/dev/video10`. Jej jedynym zadaniem jest utworzenie
`/dev/video11` poprzez `v4l2loopback-ctl`. Jeśli moduł nie jest jeszcze
załadowany, uruchamia go z dotychczasową konwencją IR `/dev/video10`.
W razie konfliktu nazwy lub
numeru urządzenia kończy się błędem, nie nadpisując obcej kamery.

Drugi instalator działa jako zwykły użytkownik. Tworzy usługę
`kinect2-rgb-webcam.service` i włącza ją w sesji KDE.
Kamera zaczyna nadawać **przy logowaniu**, nie dopiero przy otwarciu
aplikacji. Uruchamianie na żądanie wymaga osobnego etapu integracji.

## Sprawdzenie

```bash
systemctl --user status kinect2-rgb-webcam.service --no-pager
journalctl --user -u kinect2-rgb-webcam.service -n 30 --no-pager
cat /sys/class/video4linux/video11/name
```

Oczekiwana nazwa urządzenia: `Kinect v2 RGB`.
Klatki można sprawdzić przez OpenCV (jeśli `python-opencv` już jest zainstalowany):

```bash
python3 -c 'import cv2; c=cv2.VideoCapture("/dev/video11",cv2.CAP_V4L2); print("RGB frame:", c.read()[0]); c.release()'
```

Sprawdź kamerę w ustawieniach przeglądarki/OBS. W WirePlumber:

```bash
wpctl status
```

Gdy masz kilka kamer i trzeba wybrać domyślną, znajdź identyfikator
`Kinect v2 RGB` w sekcji *Video* i wykonaj `wpctl set-default ID`.
WirePlumber pamięta wybór. Przeglądarki i aplikacje mogą mieć własny wybór kamery.

## Praca z Face3D i Howdy

Sensor USB może należeć tylko do jednego odbiorcy. Aby pracować z IR/Depth:

```bash
systemctl --user stop kinect2-rgb-webcam.service
./face3d --pose
systemctl --user start kinect2-rgb-webcam.service
```

Podobnie przed `./kinect2 run` dla Howdy. Oba launchery używają
tego samego `kinect2-sensor.lock`, więc drugi odbiorca nie otworzy
sensora jednocześnie. **RGB `/dev/video11` nie służy do logowania:**
Howdy nadal korzysta z IR `/dev/video10`, bez zmian w PAM.

## Zatrzymanie i usunięcie

Tymczasowo: `systemctl --user stop kinect2-rgb-webcam.service`.
Wyłącz automatyczny start:

```bash
systemctl --user disable --now kinect2-rgb-webcam.service
sudo systemctl disable --now kinect2-rgb-device.service
```

Zainstalowane pliki są w:
`~/.config/systemd/user/kinect2-rgb-webcam.service`,
`~/.local/bin/kinect2-rgb-run`,
`/etc/systemd/system/kinect2-rgb-device.service`,
`/usr/local/libexec/kinect2-rgb-device`.
Dezaktywacja usługi systemowej nie usuwa istniejącego urządzenia
`/dev/video11` w trakcie bieżącej sesji; znika ono po restarcie
(o ile inna konfiguracja nie tworzy go ponownie).

## Uwagi techniczne

- `v4l2loopback` z `exclusive_caps=1` udostępnia kamerę aplikacjom po
  podłączeniu producenta obrazu; dlatego usługę uruchamiamy przy logowaniu.
- Prędkości 30 FPS i zgodności OBS/Firefox **nie zweryfikowano na
  docelowym sprzęcie**. Kod C++ przeszedł testy składni i konwersji YUYV
  z atrapami API, co nie zastępuje prawdziwego testu na sensorze.
- Program generuje 720p z natywnego 1080p, aby zmniejszyć koszt transmisji
  YUYV przez wirtualną kamerę. Nie wykorzystuje mapy Depth.
- W przypadku restartów zobacz logi: `journalctl --user -u kinect2-rgb-webcam.service -f`.
