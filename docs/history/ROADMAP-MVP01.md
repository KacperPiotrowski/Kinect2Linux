> **Archiwum historyczne.** Instrukcje instalacji/patchowania w tym pliku są przestarzałe i nie należy ich stosować do aktualnej wersji projektu. Zobacz główne `README.md`.

# Roadmap i warunki odbioru

## MVP 0.1 — publikujemy jako eksperyment

- [x] Zweryfikowany most IR→V4L2 i podgląd przez OpenCV na Archu (wynik z wcześniejszej sesji).
- [x] CPU/OpenMP: 900 IR+Depth bez luk w sekwencji przy 4 wątkach (wynik użytkownika).
- [x] Zestaw uruchomieniowy: `doctor/build/run/preview/enroll`.
- [x] Podgląd z odłączonym wątkiem analizy (testy logiki bez sprzętu).
- [ ] Test nowego podglądu na rzeczywistym komputerze z KDE Wayland.
- [ ] Test 5 prób rejestracji i trafności rozpoznawania.

## MVP 0.2 — sensor runtime

- Jedno otwarcie Kinecta, równoczesny strumień RGB/IR/Depth.
- Dla klientów: kontrolowany, prywatny IPC (pełne IR float32 / Depth float32, znaczniki czasu), plus wyjścia V4L2.
- Rozdzielenie odbioru i obliczeń tak, żeby opóźniona analiza nie blokowała wątku sensora.
- Stabilne nazwy urządzeń i uruchamianie jako usługa systemd.
- Test >=30 minut oraz walidacja rzeczywistego błędu Depth (nie tylko FPS).

## MVP 0.3 — eksperymentalna biometria 3D

- Automatyczne prowadzenie i zatwierdzanie pozycji głowy podczas rejestracji.
- Dopasowane przestrzennie IR/Depth; kontrola jednostek i kalibracji.
- Weryfikacja zgodności tożsamości i geometrii; test zdjęcie/ekran/maska.
- Własne modele przechowywane w bezpiecznym katalogu z uprawnieniami 0700/0600.
- Benchmark fałszywych akceptacji/odrzuceń przed jakąkolwiek integracją z PAM.

## Integracja z PAM — dopiero po audycie

Nie bazować na dostępności `/dev/video10` jako dowodzie zaufanej kamery.
Usługa weryfikująca musi kontrolować pochodzenie IR/Depth i posiadać niezależny
fallback hasła. Zmiany PAM wymagają kopii konfiguracji i testów w osobnej
sesji awaryjnej. Wynik testu rozpoznania nie jest samodzielnym audytem.
