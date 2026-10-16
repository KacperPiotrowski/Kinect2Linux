# Zależności, prawa autorskie i pochodzenie

Kod własny Kinect2-Linux jest publikowany na [licencji MIT](LICENSE). Nie oznacza to, że zależności lub zewnętrzne modele otrzymują licencję MIT.

- [OpenKinect/libfreenect2](https://github.com/OpenKinect/libfreenect2) — osobna biblioteka, dual Apache-2.0 / GPL-2.0 (patrz nagłówki i pliki `APACHE20`, `GPL2`, `CONTRIB` w upstream). Ten projekt korzysta z **lokalnie zbudowanej** biblioteki i nie zamieszcza jej binariów ani forka `-omp`.
- [v4l2loopback](https://github.com/v4l2loopback/v4l2loopback) — osobny moduł kernela na GPL-2.0-or-later; nie jest kopiowany do repozytorium.
- OpenCV, dlib, FFmpeg, NumPy, Python, Howdy, MediaPipe — niezależne zależności, każdy projekt ma własne warunki licencyjne. Aktualna dystrybucja źródłowa ich nie vendoryzuje.
- Zewnętrzne wagi, modele `.task` / `.dat` i dane biometryczne **nie są dołączane**. Ich legalność i możliwość redystrybucji wymagają osobnej weryfikacji. Modelu MediaPipe nie uznajemy za automatycznie zdatny do dalszej dystrybucji.
- Nie zawieramy kodu ani plików Microsoft Kinect SDK 2.0. Nazwa Kinect odnosi się do obsługi posiadanego urządzenia.

**Przed opublikowaniem binariów:** przegląd nagłówków licencyjnych własnych źródeł, pochodzenia wkładów, powiązanych bibliotek i ewentualnych modeli oraz notices wymaganych przez licencje. Ten spis nie stanowi porady prawnej ani audytu zakończonego wynikiem pozytywnym.
