# Współtworzenie Kinect2-Linux

Cel: SDK do Kinect v2 na Linuksa, docelowo plug-and-play, z natywnym dostępem do sygnałów. Obecny kod nadal ma etap prototypowy; patrz [plan](docs/REBUILD-PLAN.md).

## Jak możesz pomóc / How to help

Nie musisz mieć Kinecta ani zaawansowanego GPU, żeby pomóc. Potrzebujemy
przede wszystkim **testów na innych dystrybucjach**, czytelnej instalacji,
dokumentacji i poprawek testów bez sprzętu. Jeśli dopiero zaczynasz, zobacz
[otwarte zadania](https://github.com/KacperPiotrowski/Kinect2Linux/issues)
i poszukaj etykiety `good first issue` lub `help wanted`.
Przed większą zmianą napisz w odpowiednim issue, żebyśmy nie dublowali pracy.

**English:** Hardware owners can test USB detection, native RGB/IR/Depth
capture, the broker and the V4L2 webcam on different Linux distributions.
No Kinect? Offline unit tests, documentation, CI, packaging research and
reproducible build reports are also welcome. Please start with a scoped GitHub
issue before large architectural changes. Do not open another physical USB
capture path: the architecture targets one exclusive broker owning Kinect USB.

When opening an issue, include your Linux distribution, kernel, architecture,
relevant setup steps, expected versus actual behavior and *sanitized* errors.
Keep sensor serial numbers, usernames, home paths, face/audio recordings,
screenshots containing people and private configuration out of public reports.

See: [Community / Dołącz do nas](docs/COMMUNITY.md) and
[release-readiness tracking](https://github.com/KacperPiotrowski/Kinect2Linux/issues/12).

## Przed pull requestem

1. Pracuj na gałęzi Git. Nie wprowadzaj jednocześnie zmian do libfreenect2, mostu RGB, skryptów systemd i interfejsu Pythona; ogranicz zakres i opisz plan wycofania.
2. Uruchom testy offline: `python3 -m unittest discover -s tests -v`, `bash -n kinect2 face3d webcam/*.sh`, oraz kontrolę publicznego drzewa: `python3 tools/check_public_tree.py`.
3. Jeśli zmieniasz kod urządzenia: opisz rzeczywisty test Kinecta (RGB frame/klienci/idle; IR płynność i FPS; Depth pary, luki i wartości; ALSA 4ch) i benchmark przed/po; sprawdź brak regresji na innych CPU.
4. Nie zmieniaj domyślnie liczby kanałów audio, częstotliwości, rozdzielczości ani formatu bez udokumentowanej konwersji na żądanie.
5. Dokumentuj wymagane zależności, format komunikatów, kontrakt API i ograniczenia, bez obietnic niezweryfikowanych funkcji.

## Czego nigdy nie wysyłać do publicznego repozytorium

Surowych obrazów ludzi, WAV/PCM, modeli biometrycznych, chmur punktów PLY, prywatnych plików kalibracji zawierających identyfikatory sensorów, logów, lokalnych konfiguracji systemd z informacjami o użytkowniku, kluczy oraz binariów/licencjonowanych modeli innych projektów bez praw redystrybucji. `.gitignore` pomaga, ale **nie zastępuje** ręcznej kontroli `git status` i `git diff --cached`.

## Przed publikacją

Sprawdź pochodzenie i licencje każdego pliku ([THIRD_PARTY.md](THIRD_PARTY.md)). Nie utożsamiaj eksperymentów rozpoznawania twarzy z bezpiecznym uwierzytelnianiem: obecne narzędzia nie zapewniają ochrony przed spoofingiem i **nie należy** używać ich do PAM/SDDM/sudo. Do sprzętowych testów staraj się nie dołączać danych pozwalających zidentyfikować konkretnego użytkownika/sensor.
