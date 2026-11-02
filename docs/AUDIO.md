# Natywne mikrofony Kinect v2 — ALSA

Cztery niezależne kanały PCM: 16000 Hz, 32 bity (`S32_LE`). Zachowujemy **raw 4ch** bez automatycznego miksowania i resamplingu. Nie wymagamy EasyEffects ani wejścia stereo PipeWire. ALSA obsługuje audio jako osobny podsystem: z samych danych nie wynika synchronizacja ze strumieniem RGB/Depth.

## Nagranie diagnostyczne

Wykryj urządzenie (`arecord -l`), a następnie — gdy Kinect pojawia się pod nazwą `Sensor` — nagraj krótki plik lokalny:

```bash
arecord -D hw:Sensor,0 -f S32_LE -r 16000 -c 4 -d 8 -t wav /tmp/kinect-alsa-raw.wav
```

Analiza bez instalowania bibliotek Pythona:

```bash
python3 tools/audio_raw_analyze.py /tmp/kinect-alsa-raw.wav
```

Przykładowe wyniki z testu (nie wzorzec poprawnego poziomu): RMS −54,0 do −55,2 dBFS, peak 0,024–0,029, 0% dokładnych zer. To niskie poziomy; brak cyfr zero nie dowodzi, że to głos — trzeba odsłuchać próbkę.

Jeśli potrzebujesz odsłuchu, wykonaj **na kopii** opcjonalny downmix do mono i wzmocnienie. Nie zmienia to oryginalnego RAW:

```bash
ffmpeg -hide_banner -y -i /tmp/kinect-alsa-raw.wav \
  -af 'pan=mono|c0=c0,volume=30dB' -c:a pcm_s16le /tmp/kinect-test-louder.wav
ffplay -nodisp -autoexit /tmp/kinect-test-louder.wav
```

**Uwaga na słuch i przesterowanie:** zacznij odsłuch od niskiego poziomu głośności. Wzmocnienie 30 dB jest przykładem testowym, nie ustawieniem domyślnym SDK. Jeśli nic nie słychać, sprawdź wyciszenie *wyjścia audio*, zanim zmienisz konfigurację mikrofonów. Nigdy nie publikuj prywatnych nagrań.


## Opcjonalne mikrofony systemowe Kinect v2: 4ch + Stereo + Mono

**Status: eksperymentalna funkcja opt-in.** Na jednym Arch Linux/KDE
potwierdzono bardzo czysty odsłuch surowych kanałów 4ch, osobnego
wirtualnego Mono i dwóch kanałów Stereo. Bez podłączonego Kinecta
nie można uruchomić tych dwóch wirtualnych źródeł. To nie są nowe
sprzętowe mikrofony, lecz mapowania istniejącej matrycy.

Kinect v2 ma cztery niezależne mikrofony; PipeWire zwykle udostępnia je jako
"Xbox NUI Sensor Analogowe przestrzenne 4.0" (S32_LE, 4ch, 16 kHz).
**Oryginalne 4ch zawsze pozostaje nienaruszone**. Skrypt nie zmienia
domyślnego źródła systemowego, nie wyłącza EasyEffects i nie modyfikuje
brokera obrazu RGB/IR/Depth.

| Widoczna opcja | Co zawiera | Po co |
| --- | --- | --- |
| Xbox NUI Sensor / Surround 4.0 | Surowe 4 mikrofony | SDK, analiza, przyszły beamforming |
| Kinect2_Mono | Pierwszy fizyczny kanał matrycy | Rozmowy, prosty czysty głos |
| Kinect2_Stereo | Pierwsze dwa fizyczne kanały osobno, L/R | Eksperymenty z dwoma kanałami |

**Stereo nie oznacza śledzenia pozycji mówiącej osoby.** Matryca Kinecta
nie jest klasyczną parą mikrofonów stereo. W teście maintenera przejście
w lewą stronę nie spowodowało wyraźnej panoramy w lewo, co nie oznacza
usterki. Nie stosujemy ukrytego beamformingu, automatycznego miksowania
czterech kanałów, normalizacji ani filtrów EasyEffects.

### Uruchomienie tylko na obecną sesję

W zwykłym terminalu użytkownika (bez sudo), z działającym PipeWire
i podłączonym Kinectem:

```bash
python3 tools/kinect2_audio_profiles.py status
python3 tools/kinect2_audio_profiles.py start
python3 tools/kinect2_audio_profiles.py status
```

Powinny być widoczne trzy wybory: oryginalny Xbox NUI Sensor Surround 4.0,
`Kinect2_Mono` i `Kinect2_Stereo`. Skrypt identyfikuje źródło Kinecta
po prefiksie urządzenia oraz profilu `.analog-surround-40` i wymaga
dokładnie jednego aktywnego sensora w formacie 4ch/16kHz. Nie ma w nim
identyfikatora seryjnego Twojego Kinecta.

Używa `pactl load-module module-remap-source` z `remix=no` i jawną
mapą kanałów. Gdy środowisko różni się od przetestowanego, skrypt
**odmówi działania**, zamiast zgadywać mapowanie. Wymaga aktywnego serwera
zgodnego z PulseAudio i `pactl` (na Arch zwykle pakiety
`pipewire-pulse` i `libpulse`).

Aby wyłączyć tylko profile stworzone przez skrypt:

```bash
python3 tools/kinect2_audio_profiles.py stop
```

Polecenie sprawdza własne identyfikatory modułów w prywatnym pliku sesji
`$XDG_RUNTIME_DIR/kinect2-linux-audio-profiles.json` oraz nazwy źródeł;
**nie usuwa obcych modułów**. Jeśli testowałeś wcześniej ręczne
`kinect2_mono_test` / `kinect2_stereo_test`, ich moduły pozostają.
Uruchomione klienty audio mogą wymagać ponownego wybrania źródła.

### Opcjonalny autostart po zalogowaniu

Jeśli użytkownik świadomie chce zachować Mono i Stereo po restarcie,
uruchamia poniższe polecenia **z trwałej kopii repozytorium**
(np. `~/Projekty/kinect/Kinect2Linux`), a nie z pliku testowego w `/tmp`:

```bash
python3 tools/kinect2_audio_profiles.py install-service
# Instalacja usługi NIE włącza jej.
python3 tools/kinect2_audio_profiles.py enable-service
```

Tworzona jest wyłącznie lokalna, nazwana usługa
`systemd --user` `kinect2-audio-profiles.service`. Nie używa sudo,
nie modyfikuje `/etc`, nie dotyka innych jednostek ani starego bridge
RGB. Usługa startuje **po zalogowaniu** i działa jako lekki monitor:
co około 3 sekundy sprawdza PipeWire i obecność źródła Kinecta 4ch,
a potem tworzy lub odtwarza wyłącznie dwa zarządzane remapy. Jeżeli
Kinect zostanie wykryty z opóźnieniem, podłączony ponownie albo
PipeWire/Pulse zrestartuje się i usunie moduły, monitor podejmie
ponowną próbę bez ręcznego `systemctl start`.

`active (running)` oznacza działanie monitora, **nie** gwarantuje
obecności `Kinect2_Mono` ani `Kinect2_Stereo` (np. przy odłączonym
sensorze). Sprawdź faktyczne źródła:

```bash
systemctl --user status kinect2-audio-profiles.service --no-pager
python3 tools/kinect2_audio_profiles.py status
pactl list short sources
journalctl --user -b -u kinect2-audio-profiles.service --no-pager -n 40
```

Monitor nie otwiera USB i nie zmienia źródła domyślnego. Przy odłączeniu
sensora usuwa wyłącznie własne, zapisane remapy; obce moduły pozostają.
To mechanizm okresowej kontroli, **nie** zdarzeniowy monitor udev.
Scenariusze opóźnionego wykrycia i utraty modułów są testowane na
mockach, ale trwałość po restarcie / hotplug nadal wymaga testu na
fizycznym Kinect v2 i innych wersjach PipeWire.

### Aktualizacja ze starszej jednostki oneshot

Po aktualizacji kodu w trwałym katalogu projektu wykonaj:

```bash
python3 tools/kinect2_audio_profiles.py install-service
systemctl --user restart kinect2-audio-profiles.service
```

Instalator rozpoznaje **tylko dokładną treść starej jednostki**
wygenerowanej przez Kinect2Linux; obcej lub ręcznie modyfikowanej
jednostki nie nadpisuje. `daemon-reload` odbywa się podczas instalacji,
ale uruchomioną starszą usługę trzeba **jawnie zrestartować**.

Rollback (bez usuwania natywnego 4ch):

```bash
python3 tools/kinect2_audio_profiles.py disable-service
```

Komenda wyłącza jednostkę user service i usuwa wyłącznie zarządzane
przez skrypt moduły. Nie modyfikuje domyślnego źródła systemowego.
Jednostka pozostaje zainstalowana, lecz wyłączona. Dodatkowo można
ponownie sprawdzić urządzenia komendą `pactl list short sources`.

### Trwałe przypięcie remapów do Kinecta — WirePlumber 0.5 (opt-in)

**Zaobserwowany problem (Arch/KDE, 2026-11-02):** przy uruchomionym
EasyEffects wewnętrzne strumienie `input.kinect2_linux_mono` oraz
`input.kinect2_linux_stereo` mogły być podłączone do
`easyeffects_source`, mimo że oba remapy zostały stworzone z parametrem
`master=<fizyczne źródło Kinecta>`. Efekt: pusty WAV (100% próbek zero),
choć `status` mówił `active (managed)`. Ręczne podłączenie portu
`capture_FL` Kinecta do wejścia remapu Mono przywróciło głos **przy
działającym EasyEffects**. Nie jest to dowód, że każdy użytkownik
WirePlumber/EasyEffects doświadcza tego błędu.

**Przyczyna techniczna:** `module-remap-source` w pipewire-pulse tworzy
wewnętrzny strumień capture `input.<source_name>` z `target.object`
ustawionym z parametru `master`. WirePlumber może zapamiętać inny cel
lub przenieść strumień na domyślne źródło. Opcjonalna reguła
`stream.rules` w **WirePlumber 0.5** chroni tylko dwa wewnętrzne
strumienie Kinecta:

- `state.restore-target = false` — nie odtwarzaj starego celu,
- `node.dont-move = true` — nie przenoś strumienia przez metadane,
- `node.dont-fallback = true` + `node.linger = true` — czekaj na
  wybrany fizyczny Kinect, zamiast podpinać inne źródło.

Nie konfigurujemy `target.object` na sztywno: robi to PipeWire przy
tworzeniu każdego remapu na podstawie bieżącego `master`. Reguła nie
dotyka mikrofonu RØDE, domyślnego źródła, EasyEffects Source, innych
programów ani ich normalnej możliwości przełączania wejścia.

#### Instalacja i aktywacja

Z **głównego katalogu aktualnej gałęzi Kinect2Linux**, bez `sudo`:

```bash
wireplumber --version
python3 tools/kinect2_audio_profiles.py install-routing
python3 tools/kinect2_audio_profiles.py routing-status
```

Instalator obsługuje świadomie **WirePlumber 0.5.x**, zapisuje wyłącznie
`~/.config/wireplumber/wireplumber.conf.d/90-kinect2linux-remap-streams.conf`
i odmawia nadpisania obcego, zmienionego lub symlinkowanego pliku.
Nie wymaga rebootu, nie wyłącza EasyEffects i **nie restartuje
samodzielnie żadnej usługi**. Sama instalacja *nie zmienia jeszcze*
istniejących połączeń — reguły działają przy tworzeniu nowych strumieni.

Aby zastosować od razu, zapisz pracę w aplikacjach korzystających z
audio i **świadomie** wykonaj (nastąpi krótka przerwa dźwięku):

```bash
systemctl --user restart wireplumber.service
systemctl --user restart kinect2-audio-profiles.service
sleep 4
python3 tools/kinect2_audio_profiles.py routing-status
```

Oczekiwane trzy połączenia z **fizycznego** Kinecta:
`Mono input_FL: OK`, `Stereo input_FL: OK`, `Stereo input_FR: OK`.
`routing-status` jest wyłącznie diagnostyczny; `active (managed)`
nadal oznacza *istnienie modułu*, **nie** poprawny dźwięk. Po
uruchomieniu EasyEffects wykonaj test nagrania i **odsłuchaj WAV**.
Test fizyczny po restarcie KDE, przełączeniu urządzeń audio i
hotplug pozostaje konieczny przed uznaniem tej reguły za stabilną.

#### Bezpieczne wycofanie

```bash
python3 tools/kinect2_audio_profiles.py remove-routing
```

Usuwany jest **tylko dokładny, niezmodyfikowany fragment**
Kinect2Linux. Aby zastosować usunięcie natychmiast, po zapisaniu
pracy możesz świadomie zrestartować `wireplumber.service` oraz
`kinect2-audio-profiles.service` jak wyżej. Usunięcie reguły nie
usuwa usług audio, źródeł 4ch ani plików stanu innych programów.
Żadnego `rm -rf ~/.local/state/wireplumber`.

### Co zrobić, gdy zwykła aplikacja brzmi robotycznie?

Bezpośrednie ALSA 4ch oraz ręczny remap pojedynczego mikrofonu brzmiały
świetnie, a automatyczna konwersja oryginalnego PipeWire 4ch → 2ch też
została zaakceptowana. Nie udowodniliśmy błędu PipeWire ani EasyEffects.
Aby go zgłosić upstream, trzeba najpierw zidentyfikować **konkretną**
aplikację i etap zniekształcający głos. Wyniki diagnostyczne:
[issue #22](https://github.com/KacperPiotrowski/Kinect2Linux/issues/22).
