> **Historyczna iteracja Face3D.** Poniższe instrukcje patchowania mogą być nieaktualne. Obecny punkt wejścia opisuje [EXPERIMENTS.md](../EXPERIMENTS.md).

# Kinect2 Face3D Stage 3 — eksperymentalne zbieranie 5 póz

Ten etap **nie jest bezpiecznym systemem uwierzytelniania**. Nie ingeruje w Howdy, PAM, `/dev/video10`, `libfreenect2` ani działający most Kinecta.

## Wymagania

- Istniejący Kinect2-Linux z działającym `./face3d --pose` i natywnym Qt6.
- `./face3d` ma już ustawienie `PYTHONNOUSERSITE=1` (wcześniejsza poprawka).
- Zatrzymany `./kinect2 run` — jeden proces może być właścicielem Kinecta.

## Instalacja

Pobierz archiwum i umieść je w katalogu `~/Projekty/kinect/Kinect2-Linux/`.

```bash
cd ~/Projekty/kinect/Kinect2-Linux
cp face/live3d.py face/live3d.py.stage2-backup
unzip -o Kinect2-Face3D-stage3.zip
python3 -m py_compile face/live3d.py
python3 -m unittest discover -s tests -p test_enrollment.py -v
./face3d --enroll
```

`--pose` wciąż działa. Nowy tryb nie wymaga modyfikacji ani rekompilacji kodu C++.

## Jak przebiega sesja

1. W oknie naciśnij **Rozpocznij rejestrację (C)**. Patrz prosto w sensor i trzymaj głowę nieruchomo.
2. Po zapisaniu `FRONT` program prosi o **YAW−**, potem **YAW+**, **PITCH−** i **PITCH+**. Ze względu na niedokalibrowane znaki obrotu, polecenia odnoszą się do kierunku zmian liczb Yaw/Pitch, **nie do zaufanych etykiet lewo/prawo**.
3. Każdy etap wymaga co najmniej 7 *różnych* analizowanych klatek, minimum 0,4 s stabilnej pozycji, pojedynczej twarzy i poprawnej głębi (minimum 85% poprawnych próbek, odległość 0,55–2,2 m, rozsądny rozrzut pomiaru).
4. Gdy wszystkie pięć etapów zostaną zaakceptowane, dane zostaną zapisane automatycznie do prywatnego folderu. Przed ukończeniem całej sesji nic nie jest utrwalane.
5. W razie potrzeby kliknij **Zacznij od nowa (C)**.

## Wynik

Domyślny katalog: `~/.local/share/kinect2-linux/enrollments/face3d-YYYYmmdd-HHMMSS/`.

- Pięć plików `.npz`, każdy zawiera **wycinek twarzy** z surowego IR `float32` oraz zsynchronizowanej głębi `float32`.
- `manifest.json` opisuje przybliżoną pozę, sekwencję klatki, zakres ROI, kalibrację i jakość pomiaru.
- Podkatalog sesji ma uprawnienia 0700, pliki 0600 (przy standardowym lokalnym systemie plików).

Są to **wrażliwe dane biometryczne**, nie udostępniaj ich publicznie i nie dodawaj do Git. Gdy przestaną być potrzebne, możesz usunąć katalog sesji.

## Ograniczenia

- `rotation_proxy()` oblicza tylko **proxy** Yaw/Pitch ze zmian głębi w czterech obszarach twarzy, a nie prawdziwą 6-DoF pozę. Translacja, mimika, ruch tła, utrata profilu i różne materiały mogą zafałszować wyniki. Algorytm nie jest jeszcze podstawą do uwierzytelniania.
- Wykrywacz frontalny może zgubić twarz przy mocnym skręcie. Jeśli etap nie jest zaliczany, zmniejsz obrót i spróbuj spokojniej. Nie zmieniaj progu dla bezpieczeństwa; to tylko eksperyment.
- Ten etap **nie zapisuje modeli Howdy** i nie pozwala na automatyczne logowanie, nie implementuje anty-spoofingu, ani nie oznacza zgodności z Apple Face ID.
- Dla finalnego rozpoznawania potrzebne będą wiarygodne punkty twarzy 2D/3D, kalibracja orientacji, testy akceptacji fałszywej osoby oraz bezpieczna integracja z PAM.
