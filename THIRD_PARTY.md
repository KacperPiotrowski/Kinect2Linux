# Zależności, prawa autorskie i pochodzenie

Kod własny Kinect2-Linux jest publikowany na [licencji MIT](LICENSE). Nie oznacza to, że zależności lub zewnętrzne modele otrzymują licencję MIT.

- [OpenKinect/libfreenect2](https://github.com/OpenKinect/libfreenect2) — osobna biblioteka, dual Apache-2.0 / GPL-2.0 (patrz nagłówki i pliki `APACHE20`, `GPL2`, `CONTRIB` w upstream). Ten projekt korzysta z **lokalnie zbudowanej** biblioteki i nie zamieszcza jej binariów ani forka `-omp`.
- [v4l2loopback](https://github.com/v4l2loopback/v4l2loopback) — osobny moduł kernela na GPL-2.0-or-later; nie jest kopiowany do repozytorium.
- OpenCV, dlib, FFmpeg, NumPy, Python, Howdy, MediaPipe — niezależne zależności, każdy projekt ma własne warunki licencyjne. Aktualna dystrybucja źródłowa ich nie vendoryzuje.
- Zewnętrzne wagi, modele `.task` / `.dat` i dane biometryczne **nie są dołączane**. Ich legalność i możliwość redystrybucji wymagają osobnej weryfikacji. Modelu MediaPipe nie uznajemy za automatycznie zdatny do dalszej dystrybucji.
- Nie zawieramy kodu ani plików Microsoft Kinect SDK 2.0. Nazwa Kinect odnosi się do obsługi posiadanego urządzenia.


## Archiwalny plik modelu MediaPipe

W [pierwszym publicznym commicie (`a34f4b2`)](https://github.com/KacperPiotrowski/Kinect2Linux/commit/a34f4b2ae3bd1485ef5858ba660c50dffea90c22) znajdował się `models/face_landmarker.task` (3 758 596 bajtów). Plik **usunięto z bieżącego drzewa `main`**, ale nadal można go odzyskać z historii Git. Nie jest to składnik wymaganego stosu RGB/IR/Depth/audio.

Nie mamy niezależnie potwierdzonego źródła pobrania, manifestu komponentów ani warunków licencyjnych **tego konkretnego archiwalnego artefaktu**. W [odpowiedzi maintanera MediaPipe](https://github.com/google-ai-edge/mediapipe/issues/6355) podano ogólną informację, że kod i modele są zazwyczaj objęte Apache-2.0, o ile nie stwierdzono inaczej. Nie przesądza to automatycznie licencji ani obowiązków redystrybucji dla historycznego pliku.

Nie należy oznaczać archiwalnego modelu licencją MIT tego projektu ani ponownie dołączać go do wydań bez sprawdzenia jego pochodzenia i warunków. Ewentualne usuwanie go z historii Git wymaga osobnej decyzji i planu migracji dla istniejących klonów.

**Przed opublikowaniem binariów:** przegląd nagłówków licencyjnych własnych źródeł, pochodzenia wkładów, powiązanych bibliotek i ewentualnych modeli oraz notices wymaganych przez licencje. Ten spis nie stanowi porady prawnej ani audytu zakończonego wynikiem pozytywnym.
