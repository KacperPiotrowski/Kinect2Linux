# Kinect2 Studio — pierwsza aplikacja okienkowa (eksperymentalna)

**Status:** pierwszy prototyp do testowania na Arch Linux / KDE Plasma.
Nie jest to pełny odpowiednik Microsoft Kinect Studio ani instalator 1.0.

Kinect2 Studio to osobny klient **obecnego** brokera Kinect2Linux.
NIE otwiera USB, nie startuje drugiego procesu libfreenect2, nie
uruchamia zdalnych usług, nie zmienia PipeWire, WirePlumber ani domyślnego
mikrofonu. Wymaga świadomego kliknięcia **Start podglądu**.

## Uruchomienie

Potrzebne są Python 3, NumPy i PySide6. Na systemie z ograniczeniem
instalacji pakietów Pythona do systemowego środowiska użyj własnego venv:

~~~bash
python3 -m venv .venv-studio
. .venv-studio/bin/activate
python -m pip install PySide6 numpy
python tools/kinect2_studio.py
~~~

Aplikacja pobiera klatki przez istniejące **FrameClient** ze
**sdk/python/kinect2_linux**. Przy aktywnym i prawidłowo
skonfigurowanym **kinect2-broker.service** (opcje
--auto-streams --frame-preview) podglądy uruchamiają capture na
żądanie, bez zatrzymywania Firefoksa i innych klientów. Aplikacja nie
uruchamia/usypia usługi systemd. Jeśli broker jest niedostępny,
GUI pozostaje otwarte i pokazuje błąd. Nie włączaj równocześnie
starszego mostu przejmującego fizyczne USB.

Do sprawdzenia brokera bez zmian systemu:

~~~bash
systemctl --user is-active kinect2-broker.service
./kinect2 status
~~~

## Widok Basic / Advanced

- **Basic:** niezależny podgląd RGB (BGRX), IR oraz false-colour Depth.
- **Advanced:** wskazówki o znacznikach FPS, sekwencji klatek i wieku
  od publikacji przez brokera; pomiar nie jest opóźnieniem ekspozycji.
- Panel diagnostyki: stan brokera i **obecność** natywnego Kinect 4ch,
  Kinect2_Mono i Kinect2_Stereo z pactl list short sources.
  Sama obecność profilu nie dowodzi, że poprawnie nagrywa.
- Przycisk Stop zamyka tylko nasze subskrypcje. Pozostali klienci i
  usługi pozostają bez zmian.

## Ograniczenia

- IR jest skalowane dla podglądu; nie modyfikujemy natywnych klatek.
- Depth pokazuje kolor od 500 do 4500 mm, nie tworzy chmury XYZ i
  nie dokłada danych RGB (brak kalibracji/rejestracji).
- Pierwszy prototyp **nie ma** motion capture, nagrywania sesji, eksportu
  danych, podglądu z czterech mikrofonów ani automatycznego installer GUI.
  Aktualny eksperyment 2D body: tools/demo_basic_body_cpu.py.
- Każdy strumień ma własny wątek z ograniczonym timeoutem i odbiera
  najnowsze klatki zamiast zapychać GUI kolejką. Nie zakłada
  synchronizacji trzech niezależnych strumieni.
- Testy GUI na prawdziwym Kinect v2 + KDE, Wayland/X11 i wydajność
  RGB+IR+Depth są **do wykonania**. CI bez wyświetlacza uruchamia
  tylko testy komponentów niezależnych od Qt.

Test bez sprzętu:

~~~bash
python3 -m unittest discover -s tests -p 'test_kinect2_studio_core.py' -v
~~~

## Prywatność i wycofanie

Aplikacja **nie zapisuje ani nie wysyła** żadnych obrazów i audio.
Nie tworzy własnej usługi. Aby zakończyć pracę, kliknij Stop i zamknij
okno. Nie ma żadnej konfiguracji systemowej do usuwania; wystarczy
usunąć opcjonalne środowisko .venv-studio, jeśli już go nie chcesz.

## Następne etapy

1. Testy prawdziwych klatek RGB/IR/Depth, FPS, rozłączania i restartu
   brokera bez utraty innych odbiorców.
2. Integracja opcjonalnego RTMPose-s (17 punktów 2D) w GUI, bez
   automatycznego pobierania modeli.
3. Zakładka Audio Lab: RØDE / Kinect 4ch / Mono / Stereo, odsłuch,
   porównanie A/B oraz diagnostyka poprawności routingu.
4. Rejestracja i odtwarzanie sesji z jawnym przyciskiem nagrywania;
   dopiero później przetwarzanie map Depth w 3D.
