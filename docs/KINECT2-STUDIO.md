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
włącza/wyłącza analizę bez restartowania żadnej subskrypcji ani
brokera. Wątek RGB przekazuje dostępne klatki do jednoelementowego
bufora osobnego wątku TrackingSession("body", mode="basic").
Nadchodzące klatki zastępują oczekujące, jeżeli inferencja trwa dłużej.
**Nie ma już sztucznego limitu 5 analiz/s**, ale rzeczywisty FPS
zależy od czasu YOLOX+RTMPose i dostępnych zasobów CPU.
ONNX nie blokuje już odbioru nowych klatek RGB. Po włączeniu opcji
górny panel dzieli się na **bieżący obraz RGB** i **osobny podgląd
szkieletu**. Zielone 17 punktów COCO rysowane jest na dokładnie
**tej samej kopii RGB**, którą przeanalizował model. Dzięki temu
nie ma fałszywego dopasowania starej pozy do nowego obrazu. Nie jest to
jednak płynny realtime motion capture — panel szkieletu aktualizuje
się tak szybko, jak CPU potrafi przetwarzać RTMPose. Gdy człowiek szybko
się porusza, panel ze szkieletem będzie pozostawał za żywym RGB,
ale jego linie powinny pasować do obrazu **w tym panelu**.
IR i Depth pozostają niezależne. Bez kalibracji i 3D.
Start/Stop nadal dotyczą tylko naszych subskrypcji brokera.

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
RGB po zaznaczeniu opcji. Podczas pierwszego załadowania ONNX obraz RGB, IR i Depth powinien
nadal odświeżać się niezależnie od analizy. Sam szkielet może pojawić
się później. Nie ma potrzeby ręcznego restartowania podglądu. Wyłączenie
opcji zwalnia sesję modelu po zakończeniu aktualnie wykonywanej
inferencji; brak modeli nie blokuje podglądu RGB.

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
- checkbox jest dostępny podczas podglądu i włącza osobny wątek AI,
  bez restartu RGB, IR, Depth ani brokera;
- bufor Qt przechowuje tylko najnowszy obraz, zamiast kolejki sygnałów;
- ograniczenie prezentacji podniesiono do maksymalnie 30 FPS i uproszczono
  skalowanie obrazu. Dla IR używana jest mniejsza próbka do wyznaczania
  percentyli jasności, przy zachowaniu pełnego podglądu;
- metryki FPS mówią o wyświetlanych klatkach, nie o sprzęcie.

**Wymaga ponownego testu sprzętowego**: rzeczywisty FPS podczas ruchu,
wrażenie opóźnienia, włączenie/wyłączenie modelu w locie, zamknięcie
okna przy ładowaniu ONNX oraz obciążenie CPU. To nie jest gwarancja 30 FPS.

### Drugi etap optymalizacji: 2D bez blokowania podglądu

Pierwszy test po podniesieniu limitu GUI: RGB bez modelu ~15.2 FPS,
po włączeniu szkieletu ~7.6 FPS, a wiek prezentowanej klatki wzrósł
z około 13 ms do 86–102 ms (trzy krótkie nagrania ekranu).
W kodzie źródłem ryzyka był `tracker.process()` uruchamiany
synchronicznie w **tym samym wątku**, który pobiera i pokazuje RGB.

Teraz:
- kamera RGB działa niezależnie od inferencji i pozostaje źródłem
  15+ FPS jeżeli pozwoli na to broker i CPU;
- model otrzymuje najnowszą dostępną klatkę z
  **jednoelementowego bufora**, bez sztucznego limitu 5 FPS — stare
  klatki wypadają, a wątek podglądu nie czeka na analizę;
- po zgłoszeniu niedopasowania szkieletu rysujemy go teraz w
  **oddzielnym panelu ze skopiowaną klatką RGB użytą przez ONNX**.
  Prawy panel może działać wolniej, ale nie rozjeżdża już sylwetki
  względem obrazu, na którym została wyznaczona;
- inferencja ONNX nadal zużywa zasoby CPU i pamięć. Nawet osobny wątek
  nie gwarantuje zachowania identycznego FPS dla wszystkich urządzeń.

Wymaga ponownego testu na fizycznym Kinect v2: FPS RGB/IR/Depth przy
wyłączonym i włączonym szkielecie, CPU, czytelność linii podczas ruchu,
Start/Stop i zamknięcie okna podczas inicjalizacji modeli.

### Naprawa kolejnego błędu: 15 FPS przy brokerze dostarczającym 30

Test urządzenia bez Qt i ONNX pokazał **RGB 30.0 / IR 30.0 / Depth 30.0
dostarczonych FPS**, brak pominięć kolejki i brak timeoutów. Podgląd GUI
nadal pokazywał około **15.1 FPS**; osobny panel 2D około **4.4 FPS**.

W kodzie `StreamWorker._run_capture()` istniał drugi warunek:
`moment - last_processed < 1/30`. `last_processed` był aktualizowany
**po konwersji** obrazu, więc opóźnienie konwersji i jitter zegara
przy dostarczaniu co ~33.3 ms odrzucały często co drugą klatkę. Usunęliśmy
ten sztuczny filtr. Nadal działa **jednoelementowy bufor** najnowszej
klatki i zegar GUI 33 ms; przy rzeczywistym przeciążeniu klatki mogą
być pomijane, ale nie są odrzucane tylko ze względu na kolejny
konkurujący interwał. Nie gwarantuje to stałych 30 FPS na KDE —
potrzebny test sprzętowy po poprawce.

**Dlaczego licznik `ms` stale rośnie i spada?** To wiek aktualnie
pokazywanej klatki od czasu publikacji przez brokera, **nie**
czas renderowania ani pomiar ekspozycji Kinecta. W odświeżaniu 30 Hz
czas między klatkami wynosi średnio 33.3 ms, więc wiek będzie rosnąć
do momentu prezentacji nowszej klatki, po czym spadnie. W raporcie
`fps_probe` median `0 ms` to liczba zaokrąglona do pełnego ms,
a nie zerowy czas transmisji. FPS panelu RGB to ilość **wyświetlonych**
klatek na sekundę, a panelu pozy — ilość ukończonych analiz.

### Pomiar problemu ~15 FPS bez zgadywania

Samo podniesienie limitu GUI z 10 do 30 FPS nie udowadnia, że broker
dostarcza więcej niż ~15 FPS. Aby odróżnić problem dostarczania klatek
od wąskiego gardła Qt, najpierw zamknij Studio (tak, by jego okno nie
konkurowało o CPU), pozostaw działający broker i uruchom:

~~~bash
python tools/kinect2_studio_fps_probe.py --seconds 10
~~~

Narzędzie przez 10 sekund mierzy jednoczesnych trzech odbiorców
RGB/IR/Depth bez NumPy, Qt, renderowania czy ONNX. Zwraca **odebrane
klatki na sekundę** i liczbę pominiętych starych klatek. To **nie** jest
FPS fizycznego sensora: wynik uwzględnia dostarczanie przez brokera i
system operacyjny. Jeśli bez GUI jest ~15, źródła ograniczenia trzeba
szukać wcześniej niż w prezentacji Qt (broker, transport, obciążenie
USB/CPU). Jeśli bez GUI jest dużo więcej niż ~15, obciążeniem staje się
konwersja/skalowanie/rysowanie aplikacji.

W tej wersji podglądu czytamy surowe bufory przez
`frame.as_numpy(copy=False)` tylko wewnątrz czasu życia mmap,
po czym **kopiujemy wyłącznie dane do mniejszych, własnych QImage**
zamiast kopiować całe RGB 1920×1080. Ogranicza to transfer pamięci,
ale **nie stanowi gwarancji** FPS czy braku zacięć na sprzęcie.

### Rzetelny pomiar Body CPU (przed wyborem modelu lub akceleracji)

Kolejny test na Ryzenie 9 7900 pokazał **RGB 30.3 FPS** i
**szkielet 4.7 FPS**. Nie jest to dowód ograniczeń procesora,
ponieważ wcześniejsza ścieżka Studio miała twardy limit jednej
klatki analizy co 200 ms, a ONNX Runtime domyślnie działa w tym
adapterze z **jednym wątkiem**. Limit 5 FPS usunęliśmy.

Narzędzie `tools/kinect2_body_bench.py` bierze **jedną klatkę
RGB przez brokera do pamięci RAM** i wykonuje serię analiz na tej
samej klatce bez Qt, skalowania QPixmap czy zewnętrznego dostępu
do USB. Nie zapisuje obrazu ani danych na dysku i nie pobiera wag
modelu. Przygotuj lokalne modele ONNX, stanąć przed kamerą i
uruchom test przy **zamkniętym Studio**:

~~~bash
. .venv-studio/bin/activate
python tools/kinect2_body_bench.py --warmup 3 --runs 20
~~~

Następnie porównaj *oddzielne procesy* z różną liczbą wątków CPU,
żeby nie współdzieliły stanu/puli ONNX Runtime:

~~~bash
for t in 1 2 4 6; do
  echo "=== ORT threads=$t ==="
  KINECT2_BODY_ORT_THREADS="$t" \
    python tools/kinect2_body_bench.py --warmup 3 --runs 20
done
~~~

Narzędzie raportuje **medianę, 95. percentyl (p95), najlepszy czas**
i przybliżony teoretyczny FPS przy sekwencyjnej inferencji, a
także osobno koszt **YOLOX detector** oraz **RTMPose pose estimator**.
To jest benchmark **na tej samej zapamiętanej klatce**, więc nie
weryfikuje jakości śledzenia przy ruchu, obciążenia pozostałych
usług ani pełnego FPS GUI. Bez wykrytej osoby wynik części
`pose estimator` może być niewiarygodny — skrypt to sygnalizuje.

Interpretacja: jeśli łączny czas analizy wynosi ~200 ms, sam
pipeline wymaga dalszej optymalizacji/modelu lub backendu. Jeśli
wynosi np. 30–40 ms, ogranicznik Studio był głównym winowajcą.
Wyniki warto badać dla kilku scen, z jedną i więcej osobami,
bez dopisywania danych z czujnika głębi, których model RGB nie
wykorzystuje.

Docelowy ekwiwalent Kinect SDK v2 **nie jest samym 2D z RGB**.
Oryginalny SDK wykorzystywał dane głębi do śledzenia 25 stawów
3D. Poprawa RTMPose 2D to jeden z etapów, ale wymaga osobnego
projektu śledzenia z Depth, kalibracji oraz walidacji dokładności
i latencji, zanim będziemy mówić o profesjonalnym Body Tracking 3D.

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

## Zamykanie aplikacji i obsługa sygnałów terminala

Po zgłoszeniu z 2026-11-04 dodaliśmy kontrolowaną obsługę SIGINT
(Ctrl+C) i SIGTERM oraz skrót **Ctrl+Q**. Nieobsłużony wcześniej
KeyboardInterrupt mógł przerwać wywołanie `_render_latest` w
głównym wątku Qt, zostawiając aplikację w nieczytelnym stanie.
Sygnał zamknięcia jest teraz przekazywany na **następny obrót pętli
Qt**, a wątki podglądu i ONNX mają zakończyć się bez brutalnego
`QThread.terminate()`. Do weryfikacji na fizycznym sprzęcie.

**Ctrl+Z nie jest poleceniem kończącym!** Zatrzymuje cały proces
(SIGTSTP), przez co okno przestaje obsługiwać zdarzenia i KDE może
zgłosić „Nie odpowiada”. W terminalu ze stanem `[1]+ Zatrzymano`
wykonaj `jobs -l`, następnie `kill -CONT %1` i `kill -TERM %1`
(dla zadania numer 1). Gdy aplikacja jest responsywna, zalecamy
przycisk Stop, Ctrl+Q lub zamknięcie X. Nie kończ brutalnie procesu
bez potrzeby — inne klienty brokera powinny pozostać nietknięte.

W razie kolejnej awarii przed próbą Ctrl+Z zapisz informacje o tym,
czy Kinect2 Studio reaguje na kliknięcia (Basic/Advanced, Stop) i czy
zawieszenie nastąpiło **przed** czy **po** użyciu Ctrl+C. To rozróżnia
przeciążenie GUI od celowego zatrzymania procesu przez powłokę.

## Vulkan i OpenGL — możliwy następny etap, NIE część obecnego GUI

Obecny interfejs to PySide6 **QWidget + QLabel/QPixmap**; nie używa
Qt Quick Scene Graph. Samo ustawienie `QSG_RHI_BACKEND=vulkan` nie
przyspieszy tej ścieżki. Możliwe kierunki eksperymentów:

- migracja wyłącznie powierzchni podglądu do Qt Quick (RHI): backend
  Vulkan, OpenGL oraz fallback zgodnie z dostępnymi sterownikami GPU;
- najpierw profile wydajności: transfer klatek, skalowanie tekstur,
  rysowanie szkieletu, graf CPU i render FPS;
- później Depth 3D, po skalibrowaniu geometrii i sprawdzeniu modelu
  kamery. GPU przyspiesza wyświetlanie, ale nie obiecuje automatycznie
  większego FPS CPU RTMPose/YOLOX.
- eksperymentalny backend musi być opcjonalny i mieć działający
  fallback; UI, diagnostyka mikrofonów i pojedynczy właściciel USB
  pozostają bez zmian.

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
