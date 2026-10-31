# Basic / Advanced — jedna instalacja, jeden broker

**Zasada:** Basic ukrywa złożoność, nie funkcje. Advanced udostępnia sterowanie,
nie jest innym produktem. W obu trybach ten sam Kinect v2 ma jednego właściciela
USB (broker); Python SDK, IR/Depth i przyszłe integracje nie są blokowane
wyborem Basic.

## Pierwszy etap — działający interfejs CLI, nie gotowe GUI/instalator 1.0

| Basic | Advanced |
| --- | --- |
| Kamerka V4L2 (obecnie etykieta `Kinect v2 RGB`) | Dostęp do statusu, IR/Depth, narzędzi SDK i diagnostyki |
| Mikrofon `Kinect2_Stereo` w zwykłych aplikacjach | Zachowane natywne 4ch ALSA; także opcjonalne Mono/Stereo |
| Czytelne etapy: check, prepare, camera, stereo, activate | Istniejące polecenia `./kinect2` bez żadnych ograniczeń |
| Przyszłe Howdy i inne integracje również dostępne | Dokładniejsza konfiguracja tych samych integracji |

Nie instalujemy drugiego brokera ani oddzielnych sterowników.
Nowe podpolecenia po prostu wywołują już testowane skrypty i **nie omijają**
ich kontroli uprawnień, właściciela urządzeń czy konfliktu starej usługi RGB.

## Basic — obecna ścieżka

```bash
./kinect2 basic check       # wyłącznie odczyt; audio + kamera
./kinect2 basic prepare     # kompiluje i przygotowuje usługę, bez jej uruchamiania
./kinect2 basic activate    # jawny wybór: uruchom kamerę, następnie profile audio
```

Przed `activate` nadal trzeba ręcznie przygotować wirtualne `/dev/video11`
i wyłączyć starą usługę RGB, zgodnie z [INSTALL.md](INSTALL.md). Instalator
**nie uruchamia sudo**, nie instaluje pakietów i nie nadpisuje obcej kamerki.
Dla niezależnego uruchomienia części użyj `./kinect2 basic camera` lub
`./kinect2 basic stereo`.

`basic stereo` korzysta dziś z istniejącego menedżera profili audio:
instaluje i uruchamia usługę `kinect2-audio-profiles.service` (tworzy Stereo
**oraz Mono**), pozostawiając surowe cztery kanały i domyślny mikrofon systemu
bez zmian. W aplikacjach wybierz `Kinect2_Stereo`. Nie jest to przestrzenna
rekonstrukcja stereo ani beamforming. Jeżeli Kinect/PipeWire nie są gotowe
podczas logowania, monitor audio poczeka na wykrycie źródła i spróbuje
odtworzyć remapy; samo `active (running)` nie potwierdza gotowości mikrofonów.
Mechanizm wymaga jeszcze długiego testu hotplug na fizycznym sprzęcie.
Szczegóły w [AUDIO.md](AUDIO.md).

**Częściowa aktywacja:** jeżeli kamera uruchomi się, a audio nie, polecenie
zwraca kod błędu i wyraźnie zgłasza ten stan; nie zatrzymuje działającej kamery.
Odzyskiwanie/rollback kamery opisuje [INSTALL.md](INSTALL.md); obsługę audio
[AUDIO.md](AUDIO.md). `check` nie aktywuje niczego.

## Advanced — te same funkcje, bez dodatkowego sensora

```bash
./kinect2 advanced check
./kinect2 advanced audio
./kinect2 advanced status
./kinect2 advanced devices
./kinect2 advanced depth 120
```

Pozostałe polecenia `./kinect2` i bezpośrednie API `FrameClient` nadal
działają niezależnie od profilu. Tryb Basic **nie jest ograniczeniem dostępu**.

## Następne małe etapy — jeszcze niezaimplementowane

1. Konfigurowalna nazwa wirtualnej kamery (np. `USB Camera`) przy zachowaniu
   weryfikacji `/dev/video11` i zgodności istniejących instalacji. Sama zmiana
   nazwy V4L2 nie podszywa fizycznego Kinecta pod inne urządzenie USB.
2. Prowadzona konfiguracja oraz wykrywanie awarii/hotplug mikrofonu stereo
   bez terminala, bez automatycznej zmiany mikrofonu innych aplikacji.
3. Przyjazny interfejs Basic (GUI/wizard) z możliwością przełączenia widoku
   Advanced; bez tworzenia osobnej implementacji brokera.
4. Opcjonalne integracje, w tym Howdy, dostępne również z Basic, ale tylko po
   jawnym włączeniu i weryfikacji bezpieczeństwa. Nie modyfikujemy PAM teraz.

Ten pierwszy PR nie zmienia `libfreenect2-omp`, fizycznego USB, V4L2,
PAM ani konfiguracji systemu podczas samej instalacji z Git.
