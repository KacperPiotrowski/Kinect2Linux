# Odczyt statusu Kinect2-Linux (schema_version=1)

Wbudowane polecenia **tylko do odczytu**:

```bash
./kinect2 status [--json]
./kinect2 devices [--json]
./kinect2 clients [--json]
```

`tools/kinect2_status.py` i `tools/kinect2_inspect.py` działają bez otwierania Kinecta. Integracja w `./kinect2` **już istnieje**; nie instaluj historycznych patchy ani `tools/install_status_commands.py`.

Źródła: obecność USB w sysfs, `/dev/video11` i `/dev/video10`, `systemctl --user`, plik runtime `$XDG_RUNTIME_DIR/kinect2-rgb-state.json` (świeży do 3 s), zastępczo ostatnie zdarzenia w `journalctl`, informacja PipeWire/WirePlumber o domyślnym źródle audio, blokada `flock` oraz deskryptory `/proc`.

Znaczenie pól: `null`/`unknown` = brak pewnych danych; `rgb.openers` = procesy z otwartymi deskryptorami, nie dowód odbierania obrazu. Kamera wirtualna może istnieć bez aktywnego sensora. Domyślny mikrofon nie musi być Kinectem. Odczyt jest migawką wielu źródeł, a nie atomową transakcją. Szczegóły: [LIVE-STATUS.md](LIVE-STATUS.md).
