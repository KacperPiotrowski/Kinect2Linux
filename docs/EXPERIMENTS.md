# Opcjonalne eksperymenty Face3D / Howdy / MediaPipe

Te moduły są **oddzielone od głównych RGB/IR/Depth/audio**. Są niestabilne i nie zapewniają uwierzytelniania ani sprawdzenia żywotności. W szczególności historyczny eksperyment MediaPipe na IR pozostaje **wstrzymany** z uwagi na zgłaszany problem kompatybilności. Nowy, odizolowany klient RGB Face Landmarker 1.1.1 jest dostępny wyłącznie do prób (patrz [MEDIAPIPE.md](MEDIAPIPE.md)), bez potwierdzenia na fizycznym sprzęcie. MediaPipe nie jest potrzebny do uruchomienia SDK.

- `./face3d --help` — eksperymentalny podgląd IR+Depth, wykrywanie twarzy i geometria pozy (kod `face/live3d.py`, `src/kinect_face3d_stream.cpp`). Użycie wymaga zatrzymania innych procesów posiadających USB.
- `./kinect2 preview` — podgląd IR z opcjonalnym detektorem twarzy. Nie oznacza identyfikacji osoby.
- `./kinect2 enroll`, `./kinect2 models`, `./kinect2 test` — stare integracje z Howdy. Nie są wymagane dla głównego SDK. **Nie podłączaj ich do PAM/SDDM/sudo bez osobnego audytu.**
- `tools/mediapipe_ir_probe.py` — wyłącznie historyczny eksperyment na zapisanym obrazie IR, bez połączenia z Kinectem. Modelu Google nie ma w repozytorium; zobacz `models/README.md`.
- `tools/mediapipe_face_live.py` — opcjonalny konsument RGB z brokera, MediaPipe Face Landmarker, bez rozpoznawania tożsamości, uwierzytelniania lub dostępu USB; test sprzętowy wciąż oczekuje. Szczegóły: [MEDIAPIPE.md](MEDIAPIPE.md).

Historia eksperymentów (etapy 1–4) zachowana w `docs/history/`; **nie** traktuj jej instrukcji patchowania jako bieżącej procedury instalacji.
