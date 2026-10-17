# Odtwarzalna biblioteka libfreenect2-omp dla Kinect2-Linux

## Dlaczego nie kopiujemy przesłanego ZIP 1:1?

ZIP pochodzi z lokalnych prac nad dekoderem CPU. Zawierał oryginalny
kod OpenKinect i modyfikację filtra bilateralnego, lecz **nie zawierał
katalogu include/**, dlatego nie nadawał się do czystej kompilacji.
Dodatkowo zawierał `build-omp/`, lokalne binaria, ścieżki w cache CMake
i flagę `-march=native` związaną z komputerem autora.

Porównanie SHA Git plików źródłowych z oficjalnym repo wskazało bazę
upstream master:
`fd64c5d9b214df6f6a55b4419357e51083f15d93`.

Zmodyfikowany `src/cpu_depth_packet_processor.cpp` ma znany hash Git
`14756995f96687336e6614d83f99028cc680c4d5`.
Oryginalny upstream: `85966b7dd39a1977b6f2f2b3a203f35a0d9f65e0`.
Mały patch z przesłanej wersji jest utrzymywany w repozytorium:
`third_party/patches/libfreenect2-omp-cpu-depth.patch`.
Dotyczy wyłącznie równoległego, rozdzielonego na wiersze filtra bilateralnego;
nie wprowadza nowych algorytmów estymacji Depth.

## Pobierz komplet źródeł, zbuduj bibliotekę (Arch Linux)

Program `git` i internet są potrzebne przy **pierwszym pobraniu**.
Skrypt nie instaluje pakietów systemowych, nie żąda `sudo`, nie
otwiera Kinecta i nie zmienia istniejącego `../libfreenect2-omp`.

Systemowe zależności instalujesz świadomie, np. na Arch:

    sudo pacman -S --needed git gcc cmake ninja pkgconf libusb libjpeg-turbo nlohmann-json

Z katalogu Kinect2Linux:

    bash tools/bootstrap_libfreenect2_omp.sh
    bash tools/build_broker.sh --with-hardware

Pierwsze polecenie:
1. pobiera oficjalne źródła `OpenKinect/libfreenect2` o **dokładnie**
   przypiętym SHA, w tym brakujące `include/`,
2. sprawdza oryginalny hash zmodyfikowanego pliku,
3. nakłada **tylko** nasz minimalny patch OpenMP i potwierdza hash wyniku,
4. buduje CPU-only `libfreenect2.so` z `-fopenmp`, bez `-march=native`,
5. zapisuje wynik w `third_party/libfreenect2-omp/build-omp/lib/`.

Drugi skrypt wybiera odbudowaną bibliotekę automatycznie i buduje
`bin/kinect2-broker-hw`. Pozostałe mosty C++ nadal mogą korzystać
ze starego `../libfreenect2-omp`; nie migrujemy ich bez odrębnych testów.

Weryfikacja bez kompilowania:

    bash tools/bootstrap_libfreenect2_omp.sh --source-only
    git -C third_party/libfreenect2-omp rev-parse HEAD
    git -C third_party/libfreenect2-omp hash-object src/cpu_depth_packet_processor.cpp
    test -f third_party/libfreenect2-omp/include/libfreenect2/libfreenect2.hpp

Ponowne uruchomienie sprawdza SHA zamiast nadpisywać checkout.
Obce zmiany w pliku CPU zostaną odrzucone. Katalog całego checkoutu
`third_party/libfreenect2-omp/` jest ignorowany przez Git;
w repo trafia tylko nasz niewielki patch oraz skrypt.

Jeśli chcesz używać dotychczasowej zewnętrznej wersji zamiast nowej,
można jawnie ustawić:

    LIBFREENECT2_DIR="$PWD/../libfreenect2-omp" bash tools/build_broker.sh --with-hardware

## Ograniczenia

- **Świeży build i test na fizycznym Kinekcie zaliczone na jednym Arch Linux**
  (szczegóły poniżej); nadal nie jest to dystrybuowany release ani test
  wielodystrybucyjny.
- CPU-only; nie włącza automatycznie OpenCL, OpenGL ani CUDA.
- Zależność wymaga dostępu do GitHub przy pierwszej instalacji,
  więc jeszcze nie jest samowystarczalną instalacją offline.
- Nie zmienia trybów ekspozycji ani nie obiecuje 30 FPS RGB
  w ciemności. Dotąd RGB osiągało ~15 FPS przy słabym świetle
  i ~30 FPS przy silnym świetle; IR i Depth ~30 FPS.
- Poprawkę filtra OpenMP trzeba dalej profilować; wcześniejsze testy
  wykazały duże zużycie CPU bez limitu wątków i różnice w odczuwalnej
  latencji przy wymuszonym `OMP_NUM_THREADS=4`.
- Nie zmienia `main` aż do ręcznego scalenia PR.

## Potwierdzenie sprzętowe maintenera — 17 października 2026

Na Arch Linux, GCC/G++ 16.2.1, libusb 1.0.30, libjpeg-turbo,
użytkownik wykonał **pełne pobranie źródeł z brakującymi wcześniej
nagłówkami, zastosowanie i weryfikację patcha OpenMP, kompilację
libfreenect2.so oraz kinect2-broker-hw**. Komenda `ldd` wskazała
`third_party/libfreenect2-omp/build-omp/lib/libfreenect2.so.0.2`,
a nie starą bibliotekę z katalogu obok repo.

Broker uruchomiony z `OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE`.
Benchmark `python3 tools/benchmark_capture.py --warmup 3 --duration 5`:

| Tryb | RGB FPS | IR FPS | Depth FPS | Luki RGB/IR/Depth | CPU brokera |
| --- | ---: | ---: | ---: | --- | ---: |
| RGB A | 30,2 | 0 | 0 | 0/0/0 | 19% |
| RGB+IR+Depth A | 30,0 | 30,0 | 30,0 | 0/0/0 | 223% |
| IR+Depth | 0 | 30,0 | 30,0 | 0/0/0 | 203% |
| RGB+IR+Depth B | 30,0 | 30,0 | 30,0 | 0/0/0 | 221% |
| RGB B | 30,0 | 0 | 0 | 0/0/0 | 20% |

RGB-only mediana 30,10 FPS; RGB combined 30,00 FPS
(99,7% wyniku solo). CPU 100% = jeden całkowicie zajęty
procesor logiczny. To **zliczanie odebranych ramek**, bez
weryfikacji pikseli, rzeczywistego opóźnienia USB→ekran,
utrat pakietów USB ani długotrwałej stabilności. Oświetlenie
mogło być wystarczająco silne dla RGB 30 FPS; wcześniej przy
słabszym świetle RGB miało 15 FPS. Test nie dotyczy czterech
klientów GUI, którzy pozostają w osobnym PR #11.

`-Waddress-of-packed-member` z oryginalnego kodu oraz
ostrzeżenie o minimalnej wersji CMake nie zablokowały buildu;
wymagają odrębnej oceny, nie są potwierdzeniem błędów wykonania.

## Prawa autorskie i licencje

Źródła `libfreenect2` i ich nagłówki pozostają kodem osób
wymienionych przez OpenKinect i podlegają licencjonowaniu upstream
(Apache-2.0 lub GPL-2.0 zgodnie z dokumentacją i notices upstream).
Ta zmiana nie nadaje im licencji MIT Kinect2-Linux.
Nie redystrybuujemy binariów ani archiwum lokalnych plików.
