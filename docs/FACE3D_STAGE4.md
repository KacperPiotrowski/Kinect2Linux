# Kinect2 Face3D Stage 4 — 5 punktów twarzy + Depth (eksperyment)

Wykorzystuje **lokalny** model `shape_predictor_5_face_landmarks.dat` z dlib
(często dostępny razem z Howdy). Waga modelu nie jest dołączona; zapoznaj się z
licencją źródłowego modelu przed redystrybucją.

Zmiana względem Stage 3: Yaw i Pitch nie są już liczone z narożników
prostokąta detekcji. Osobny wątek lokalizuje cztery punkty wokół oczu i nos,
próbkuje mapę głębi wokół tych punktów, przelicza na współrzędne XYZ i
wyznacza **przybliżoną orientację względem FRONT**.

Wymagania: działająca wersja Stage 3 + poprawka bezpiecznego zamykania, dlib,
lokalny **czytelny** plik modelu. Nie instaluje pakietów ani nie dotyka PAM.

## Uruchomienie

Zatrzymaj inne programy korzystające z Kinecta. Po nałożeniu patcha:

```bash
PYTHONNOUSERSITE=1 ./face3d --pose
```

Jeśli model nie jest czytelny, dostaniesz informację przed uruchomieniem
sensora. Sprawdź położenie:

```bash
sudo find /usr/lib/howdy /usr/lib/security/howdy /usr/etc/howdy \
  -name shape_predictor_5_face_landmarks.dat 2>/dev/null
```

Jeśli plik jest niedostępny do odczytu dla zwykłego użytkownika, możesz
samodzielnie pozyskać zgodną kopię modelu z dozwolonego źródła do
`~/.local/share/kinect2-linux/models/` albo podać parametr
`--landmark-model /sciezka/do/modelu.dat`. **Nie zmieniaj uprawnień katalogów Howdy**.

## Co testujemy

1. `./face3d --pose`, C do ustawienia FRONT.
2. Na IR pojawia się 5 pomarańczowych punktów; obracaj głowę powoli.
3. Gdy nie można odczytać XYZ któregokolwiek punktu, odczyt pozy zostaje
   odrzucony — nie ma cichego powrotu do starej metody.
4. `./face3d --enroll` dopiero po weryfikacji kierunków i stabilności.

**To nie jest skalibrowany kąt głowy ani system zabezpieczenia biometrycznego.**
Model 5-punktowy jest trenowany głównie dla obrazów widzialnych, więc skuteczność
w podczerwieni wymaga sprawdzenia. Silny obrót może wyłączyć detektor frontalny.
Nie obniżaj progów bez pomiarów; nie modyfikuj PAM.
