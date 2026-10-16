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
