# Kinect2-Linux Face3D — Stage 2: eksperymentalny pomiar ruchu głowy

## Wymagania

To **dodatek do działającego Face3D Stage 1**. Archiwum nadpisuje jedynie:

- `src/kinect_face3d_stream.cpp` (dodaje parametry kalibracji optycznej IR do przesyłanych danych)
- `face/live3d.py` (wyświetla względną asymetrię głębi twarzy)
- `tests/test_live3d.py` (testy jednostkowe)

Nie dotyka `./kinect2`, `./kinect2 run`, Howdy, PAM, kernela ani biblioteki `libfreenect2-omp`.

## Aktualizacja istniejącego projektu

1. Zatrzymaj wcześniejszy `./face3d` lub `./kinect2 run`.
2. W katalogu `~/Projekty/kinect/Kinect2-Linux` zachowaj kopię obu plików przed nadpisaniem (np. `cp face/live3d.py face/live3d.py.stage1` i `cp src/kinect_face3d_stream.cpp src/kinect_face3d_stream.cpp.stage1`).
3. Rozpakuj archiwum do **istniejącego** `Kinect2-Linux`, zachowując strukturę podkatalogów.
4. Wykonaj:

```bash
./face3d build
./face3d --pose
```

Sprawdź skrypt przed uruchomieniem: `python3 tests/test_live3d.py`.

## Sterowanie

- Popatrz prosto w sensor z odległości ok. 0,7–1,2 m.
- Kliknij okno podglądu, aby przejęło fokus, i naciśnij **C** — zapisze chwilową pozycję jako **FRONT**.
- Powoli obróć głowę w obie strony, a potem lekko pochyl i unieś.
- Overlay pokazuje przybliżone zmiany `yaw` i `pitch` względem pozycji początkowej. `YAW+` i `YAW-` oznaczają **dwa kierunki zmiany asymetrii głębi**, a nie jeszcze skalibrowane prawo/lewo.
- Każda zmiana musi być wykryta w co najmniej 3 *kolejnych wynikach detektora*.
- **Q/Esc** zamyka okno. Nie zapisuje biometria/modeli.
- Jeśli wartości nie osiągają progu, przetestuj `./face3d --pose --turn-threshold 8`. Nie używaj tego progu jako zabezpieczenia logowania.

## Ograniczenia

- Jest to **eksperymentalny wskaźnik ruchu 3D**, oparty na medianach głębi z czterech małych regionów prostokąta twarzy. To nie jest dokładna poza głowy (6DoF), kalibrowane śledzenie punktów twarzy ani dowód żywotności.
- Opiera się na detektorze *frontalnym*, który może gubić twarz przy silnym obrocie.
- Czarny na mapie głębi oznacza **brak ważnego pomiaru** w danym pikselu. Nie można utożsamiać czerni ze skrajną bliskością.
- Face3D nadal nie wykonuje uwierzytelniania, nie zapisuje skanów, nie zmienia PAM i nie uruchamia się automatycznie jako usługa.
- Kolejny krok: prawdziwe punkty orientacyjne twarzy + wygładzanie czasowe + testy precyzji, dopiero potem rejestracja z kontrolą kątów i weryfikacja 3D.

## Pliki testowe

`python3 tests/test_live3d.py` — syntetyczne testy parsowania protokołu, normalizacji i wskaźnika wychylenia.

Testy wykonane na sucho nie zastępują testu z Kinectem.
