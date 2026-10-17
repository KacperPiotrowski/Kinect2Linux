# Bezpieczne wycofanie starego `../libfreenect2-omp`

Dla oryginalnych użytkowników Kinect2-Linux, którzy wcześniej budowali
bibliotekę w **katalogu obok** projektu, a teraz używają przypiętego
`third_party/libfreenect2-omp` z PR #13.

**Nie usuwaj jeszcze** `../libfreenect2-omp`, dopóki nie wykonasz wszystkich
poniższych kroków. Nowy broker sprzętowy może już używać nowej
biblioteki, ale wcześniejsze programy RGB/IR/Depth/Face3D mogły być
zlinkowane z bezwzględnym RUNPATH/RPATH do dawnej lokalizacji.
Dodatkowo stare skrypty `kinect2`, `face3d`, `webcam/build.sh`
domyślnie kompilowały przeciwko starym źródłom; tę zależność
naprawiono dopiero w PR #14.

## Procedura

1. Zatrzymaj stary broker, demo, mosty i **aktywną** usługę
   `kinect2-rgb-webcam.service` przed przebudową; nie zmieniaj
   systemu samoczynnie i nie uruchamiaj narzędzi kompilacyjnych przez sudo.
2. Przejdź na wersję repo z poprawką migracji launcherów (PR #14 po
   zatwierdzeniu i scaleniu do main). Upewnij się, że w repo istnieje
   kompletna nowa biblioteka:

   ```bash
   cd ~/Projekty/kinect/Kinect2Linux
   bash tools/bootstrap_libfreenect2_omp.sh
   ./kinect2 doctor
   ```

3. Przebuduj stare mosty ze źródeł; komendy nie otwierają sensora:

   ```bash
   ./kinect2 build
   bash webcam/build.sh
   ./face3d build
   ```

   Diagnostyczny `bin/kinect_depth_probe` również trzeba ponownie
   skompilować, jeśli był wcześniej zlinkowany z dawną lokalizacją.
   `./kinect2 depth` normalnie buduje go tylko, gdy nie istnieje albo
   jego źródła się zmieniły, a następnie **otwiera urządzenie**.
   Nie używaj tego polecenia wyłącznie po to, aby przepiąć biblioteki.
   Możesz tymczasowo odłożyć stary `bin/kinect_depth_probe`
   (to wynik kompilacji, nie źródła), a następnie przy kolejnym
   świadomym teście `./kinect2 depth` zbuduje go od nowa.
   Jeśli używasz dodatkowych ręcznie skompilowanych programów,
   także przebuduj je z nowymi nagłówkami i biblioteką.

4. Sprawdź rzeczywistą ścieżkę linkowania **każdego istniejącego**
   programu z listy:

   ```bash
   for b in bin/kinect2-broker-hw bin/kinect_ir_bridge \
            bin/kinect_rgb_bridge bin/kinect_face3d_stream \
            bin/kinect_depth_probe; do
     if [[ -x "$b" ]]; then
       echo "== $b =="
       ldd "$b" | grep -E 'libfreenect2|not found'
     fi
   done
   ```

   Wszystkie występujące wpisy `libfreenect2` muszą wskazywać katalog
   `Kinect2Linux/third_party/libfreenect2-omp/build-omp/lib/`,
   **nie** `../libfreenect2-omp/build-omp/lib/` i nie
   `not found`.

5. Dopiero wtedy **przenieś** starą kopię poza jej dotychczasową
   lokalizację (np. zmień jej nazwę), zamiast natychmiast ją usuwać.
   Uruchom świadomie te funkcje, których używasz, sprawdź działanie
   RGB/IR/Depth/Face3D oraz ewentualnej usługi systemd-user.
   Jeśli cokolwiek się zepsuje, odtwórz dawną nazwę katalogu.
   Po udanym teście możesz sam zdecydować o trwałym usunięciu
   starej kopii.

**Uwaga:** `LIBFREENECT2_DIR` jawnie ustawione w shellu,
konfiguracji systemd, IDE lub skryptach nadal ma pierwszeństwo i
może wymuszać starą bibliotekę. `env | grep LIBFREENECT2_DIR`
pozwala to sprawdzić dla bieżącej powłoki.
Katalog `third_party/libfreenect2-omp` jest lokalnie pobierany i
ignorowany przez Git; nie usuwaj go zamiast starego katalogu.

## Testy migracji na fizycznym sprzęcie (17 października 2026)

Na Arch Linux użytkownik zmienił nazwę dawnego katalogu
`../libfreenect2-omp` na `../libfreenect2-omp.old` (odwracalnie),
pozostawiając `LIBFREENECT2_DIR` nieustawione. Przed próbą kompilacji
sprawdzono `ldd` dla brokera, mostu IR, mostu RGB i Face3D: wszystkie
wskazały nową bibliotekę w
`Kinect2Linux/third_party/libfreenect2-omp/build-omp/lib/`.

Potwierdzone testy użytkownika:

- **Native IR + Depth:** `./kinect2 depth 60`: 60/60 par zgodnych
  sekwencji i znaczników czasu, 0 luk sekwencji, 0 niepoprawnych
  formatów i brakujących par; urządzenie prawidłowo zamknięte.
  `ldd bin/kinect_depth_probe` wskazał nową bibliotekę.
- **IR V4L2:** `./kinect2 run` wraz z `./kinect2 preview`: żywy
  obraz na `/dev/video10`, potwierdzony wizualnie.
- **RGB V4L2:** `/dev/video11` ma etykietę `Kinect v2 RGB`, usługa
  `kinect2-rgb-webcam.service` ma stan `active`,
  `bin/kinect_rgb_bridge --probe /dev/video11` potwierdza
  `V4L2_EVENT_PRI_CLIENT_USAGE`, a `ffmpeg` odebrał 90 ramek
  YUYV422 1920×1080; użytkownik potwierdził żywy obraz w Firefoxie.
  Wartość `fps=23` w końcowej linii FFmpeg nie jest pomiarem
  szybkości próbkowania sensora.

**Zakres potwierdzenia:** migracja ścieżek, kompilacja i realne
działanie RGB/IR/Depth na jednym komputerze. Samodzielne uruchomienie
Face3D nie było przedmiotem testu (jego binarium kompiluje się i
prawidłowo linkuje). Nie gwarantuje to, że żaden własny skrypt,
zewnętrzna usługa lub program spoza repo nie korzysta z dawnego
katalogu. Przed definitywnym skasowaniem `.old` sprawdź takie
lokalne zależności i utrzymaj możliwość cofnięcia migracji.

Zmiana nie przenosi audio ALSA ani sprzętowych uprawnień USB. Nie daje
jeszcze gotowego instalatora ani pewności działania na każdej dystrybucji.
