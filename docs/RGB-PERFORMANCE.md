# Diagnostyka wydajności RGB + IR/Depth (PR #9)

**Cel:** ustalić, czy spadek RGB z ~79 do ~60 klatek w trzysekundowych
pomiarach PR #8 był efektem rozruchu/przełączania, czy rzeczywistym
ograniczeniem przy jednoczesnym przechwytywaniu.

Wyniki historyczne PR #8 (około 3 sekundy, **obejmują start**):
- IR+Depth: IR 88, Depth 88.
- RGB: 79.
- RGB + IR + Depth: RGB 60, IR 81, Depth 81.

Nie są to ustabilizowane FPS; nie dowodzą przeciążenia CPU ani USB.

## Co mierzymy

`tools/benchmark_capture.py` wykonuje **pięć prób**, celowo w kolejności
RGB → RGB+IR+Depth → IR+Depth → RGB+IR+Depth → RGB.
Każda próba ma 3 sekundy rozgrzewki i 10 sekund właściwego pomiaru
(łącznie około 65 s plus narzut przełączania).

Skrypt porównuje różnice `frame_counts` po rozgrzewce i podaje:
- Delivered RGB/IR/Depth FPS (klatki odebrane przez callback, nie gwarancję FPS sensora).
- Luki `sequence_gaps`: brakujące numery sekwencji **pomiędzy dostarczonymi klatkami**
  libfreenect2. Zero nie wyklucza strat na wcześniejszym etapie USB/dekodowania.
- CPU % całego procesu brokera odczytany z `/proc/PID/stat`: 100% ≈ jeden w pełni
  wykorzystany rdzeń logiczny, 200% ≈ dwa rdzenie itd. To nie jest CPU % całego komputera.
- Medianę RGB-only i RGB combined; drugi pomiar każdego trybu pomaga wykryć dryf.

NIE przesyłamy danych obrazu, nie zapisujemy plików kamer ani nie zmieniamy
uprawnień urządzenia.

## Test sprzętowy na Arch Linux

PR #8 został już scalony, ale ta diagnostyka jest na oddzielnej gałęzi:

```bash
git fetch origin
git switch --track origin/perf/rgb-throughput-diagnostics
bash tools/build_broker.sh --with-hardware
./bin/test_sequence_gap_tracker
```

Przed próbą zatrzymaj inny broker i mosty RGB/IR/Depth korzystające z USB.
Nie kasuj pliku `kinect2-sensor.lock` ani nie uruchamiaj brokera przez sudo.

W pierwszym terminalu:

```bash
./bin/kinect2-broker-hw --allow-device-control
```

W **drugim terminalu**, w katalogu repo:

```bash
python3 tools/benchmark_capture.py --warmup 3 --duration 10
```

Skrypt sam otworzy Kinecta, wykona pięć pomiarów, po każdej próbie
zatrzyma strumienie i na końcu zamknie USB. W razie błędu spróbuje
zwolnić zasoby w `finally`. Prześlij całą tabelę z terminala, łącznie
z CPU % i lukami sekwencji.

## Jak interpretować wynik — bez przedwczesnego wniosku

1. **RGB combined blisko RGB-only po rozgrzaniu:** krótkie testy zawyżyły
   ocenę spadku; żadna optymalizacja może nie być potrzebna.
2. **RGB combined niższe, CPU procesu mocno zajęte:** prawdopodobna
   konkurencja o CPU przy `CpuPacketPipeline` (dekodowanie JPEG RGB oraz
   przetwarzanie Depth). Najpierw eksperyment z ograniczeniem liczby
   wątków OpenMP, potem ewentualnie opcjonalny pipeline GPU.
3. **Wyraźne `rgb_seq_gaps`:** docierają ramki z lukami numeracji;
   trzeba sprawdzić log libfreenect2, USB 3.0 (`lsusb -t`), obciążenie
   i bufory, nie zakładając automatycznie winy konkretnego podsystemu.
4. **CPU niskie, luki zero, lecz RGB combined nadal wyraźnie niższe:**
   zbadać tempo produkcji ramek w samej bibliotece, kolejki listenerów,
   firmware i transfery USB — same liczniki brokerowe nie wystarczą.

Jeśli różnica jest powtarzalna, można powtórzyć **dokładnie ten sam test**
po ponownym uruchomieniu brokera z różnymi ustawieniami:
`OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE ./bin/kinect2-broker-hw --allow-device-control`.
To eksperyment, **nie** nowa domyślna konfiguracja. Nie zmieniaj jednocześnie
pipeline'u, kontrolera USB i ustawień wątków — wtedy nie będzie wiadomo,
co dało poprawę.

Libfreenect2 udostępnia różne pipeline'y CPU/OpenCL/OpenGL
([dokumentacja projektu](https://openkinect.github.io/libfreenect2/group__pipeline.html));
włączenie GPU wymaga odrębnej kompilacji i sprawdzenia na rzeczywistym sprzęcie.

**Kryterium zamknięcia diagnostyki:** dwie powtarzalne serie pomiarowe i
wyjaśnienie przyczyny na podstawie liczb, nie przypuszczeń. Dopiero wtedy
wybieramy poprawkę i porównujemy z baseline w identycznych warunkach.
