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

## Opcjonalny Motion Capture 2D (RTMPose-s, CPU)

W menu obok Basic/Advanced znajduje się **Szkielet 2D · CPU**, domyślnie
wyłączony. Można go zaznaczyć **także podczas działającego podglądu**. Studio
bezpiecznie odtwarza wtedy wyłącznie subskrypcję RGB, pozostawiając
IR/Depth i innych klientów brokera bez zmian. Wtedy wątek RGB
przekazuje własną klatkę obrazu do istniejącego TrackingSession("body",
mode="basic") i nakłada zielony szkielet 17 punktów COCO na **dokładnie
tę samą** klatkę RGB. IR i Depth pozostają bez zmian. Start/Stop nadal
dotyczą wyłącznie naszych trzech subskrypcji brokera.

Model potrzebuje **dwóch lokalnych plików ONNX** w katalogu models.
Żadne wagi nie są dołączone do Git ani pobierane przy uruchamianiu aplikacji.
Jeśli nie były jeszcze przygotowane, wykonaj osobno, świadomie:

~~~bash
. .venv-studio/bin/activate
python -m pip install 'rtmlib==0.0.16' 'onnxruntime==1.31.0'
# Wymaga przeglądu licencji/modeli i wyraźnej zgody na pobranie:
python3 tools/prepare_rtmpose_body.py --download
python tools/kinect2_studio.py
~~~

Szczegóły źródeł modeli, wymagań i licencji: [BODY-BASIC-CPU.md](BODY-BASIC-CPU.md).
Nie wykonuj pobierania, jeśli modele już leżą w models. Brak bibliotek/wag
nie wyłącza RGB: Studio wyświetla powód niedostępności śledzenia i
pokazuje sam obraz. Modele są ładowane dopiero przy pierwszej klatce
RGB po zaznaczeniu opcji. Podczas pierwszego startu może być krótka pauza
w odświeżaniu RGB, ale interfejs Qt działa w osobnym wątku. Po
przełączeniu śledzenia poczekaj na informację o stanie Body Tracking;
nie ma potrzeby ręcznego restartowania całego podglądu.

**To jest 2D, a nie Kinect SDK 2.0 Body Tracking 3D:** punkty
pochodzą wyłącznie z obrazu RGB. Nie są metrycznie rejestrowane z Depth,
nie podajemy odległości ani ID osoby, nie tworzymy danych biometrycznych
do uwierzytelniania. FPS wyświetlony na podglądzie dotyczy prezentowanych
klatek, nie częstotliwości sprzętowego Kinecta. Czas inferencji znajduje
się w polu diagnostyki Body Tracking.

Bez modeli/bez Qt test geometrii:

~~~bash
python3 -m unittest discover -s tests -p 'test_kinect2_studio_pose.py' -v
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

## Świeższy obraz i kontrolki po starcie

Zgłoszenie sprzętowe (listopad 2026): przed zmianą użytkownik widział
około 8 FPS przy mocnym oświetleniu i nie mógł zaznaczyć śledzenia po
kliknięciu Start. Wynikało to przede wszystkim z limitu 10 FPS w GUI
oraz blokowania checkboxa, a nie z wykazanej awarii sensora.

Po tej poprawce:
- checkbox jest dostępny podczas podglądu i restartuje tylko klienta RGB,
  nie całe Studio i nie proces brokera;
- bufor Qt przechowuje tylko najnowszy obraz, zamiast kolejki sygnałów;
- ograniczenie prezentacji podniesiono do maksymalnie 30 FPS i uproszczono
  skalowanie obrazu. Dla IR używana jest mniejsza próbka do wyznaczania
  percentyli jasności, przy zachowaniu pełnego podglądu;
- metryki FPS mówią o wyświetlanych klatkach, nie o sprzęcie.

**Wymaga ponownego testu sprzętowego**: rzeczywisty FPS podczas ruchu,
wrażenie opóźnienia, włączenie/wyłączenie modelu w locie, zamknięcie
okna przy ładowaniu ONNX oraz obciążenie CPU. To nie jest gwarancja 30 FPS.

## Ograniczenia

- IR jest skalowane dla podglądu; nie modyfikujemy natywnych klatek.
- Depth pokazuje kolor od 500 do 4500 mm, nie tworzy chmury XYZ i
  nie dokłada danych RGB (brak kalibracji/rejestracji).
- Pierwszy prototyp ma opcjonalny **overlay body 2D** z już istniejącego
  RTMPose-s, ale **nie ma śledzenia 3D**, nagrywania sesji, eksportu danych,
  podglądu czterech mikrofonów ani automatycznego instalatora.
- Każdy strumień ma własny wątek z ograniczonym timeoutem i odbiera
  najnowsze klatki zamiast zapychać GUI kolejką. Jednoelementowy bufor
  najnowszej klatki zapobiega gromadzeniu starych obrazów w kolejce Qt.
  Przygotowanie obrazu jest ograniczone do **maksymalnie 30 FPS** na panel,
  a GUI odświeża się zegarem 33 ms; na słabszym sprzęcie FPS może być
  niższy. **FPS w GUI mierzy faktycznie wyświetlone klatki, nie natywny
  FPS sensora**. Opóźnienie w metrykach liczy się od publikacji klatki
  przez brokera do prezentacji w Qt i nie obejmuje ekspozycji/sensora.
  Nie zakłada synchronizacji trzech strumieni.
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
2. Dopracowanie opcjonalnego RTMPose-s 2D: testy CPU i zamykania
   pierwszego ładowania ONNX bez wpływu na inne strumienie.
3. Zakładka Audio Lab: RØDE / Kinect 4ch / Mono / Stereo, odsłuch,
   porównanie A/B oraz diagnostyka poprawności routingu.
4. Rejestracja i odtwarzanie sesji z jawnym przyciskiem nagrywania;
   dopiero później przetwarzanie map Depth w 3D.
