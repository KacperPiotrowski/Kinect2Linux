#!/usr/bin/env python3
"""Basic and Advanced entry points for one Kinect2Linux engine.

This is a conservative, incremental CLI facade over existing installers.
It never runs sudo, changes PAM, replaces devices or bypasses safety checks.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools" / "install_kinect2.sh"
AUDIO = ROOT / "tools" / "kinect2_audio_profiles.py"
CLI = ROOT / "kinect2"

ADVANCED_COMMANDS = frozenset((
    "status", "devices", "clients", "doctor", "build", "run",
    "preview", "depth", "enroll", "models", "test",
))


def help_text() -> str:
    return """Kinect2Linux: jeden silnik, dwa sposoby obsługi

  ./kinect2 basic check       Sprawdź kamerę i mikrofon (bez zmian).
  ./kinect2 basic prepare     Zbuduj i przygotuj broker (nie uruchamia).
  ./kinect2 basic camera      Włącz przygotowaną kamerkę (jawna zgoda).
  ./kinect2 basic stereo      Włącz profile audio, w tym stereo (jawna zgoda).
  ./kinect2 basic activate    Kamera, a następnie stereo; zgłasza częściowy sukces.

  ./kinect2 advanced check    Kontrola wymagań brokera.
  ./kinect2 advanced audio    Szczegóły dostępnych profili audio.
  ./kinect2 advanced <cmd>    Istniejące polecenia: status, devices, clients,
                              doctor, build, run, preview, depth,
                              enroll, models, test.

Ważne:
  - Oba tryby używają tego samego brokera, sensora i SDK.
  - Basic nie blokuje dostępu do IR/Depth ani przyszłych integracji.
  - Nadal potrzebna jest ręczna konfiguracja /dev/video11, USB i zależności.
  - Obecna kamera nazywa się Kinect v2 RGB; alias USB Camera to kolejny etap.
  - Stereo to na razie remap dwóch mikrofonów, bez ustawiania domyślnego wejścia.
  - Żadne polecenie nie włącza Howdy/PAM automatycznie.
Dokumentacja: docs/BASIC-ADVANCED.md
"""


def run(*argv: object) -> int:
    try:
        return subprocess.run([str(arg) for arg in argv], check=False).returncode
    except OSError as exc:
        print(f"[kinect2] Nie można uruchomić polecenia: {exc}", file=sys.stderr)
        return 2


def basic(action: str, extra: list[str]) -> int:
    if extra:
        print("[kinect2] Basic: to polecenie nie przyjmuje dodatkowych argumentów.", file=sys.stderr)
        return 2
    if action == "check":
        print("[kinect2] Basic: kontrola kamery", flush=True)
        camera = run("bash", INSTALLER, "--check")
        print("[kinect2] Basic: kontrola mikrofonu stereo", flush=True)
        audio = run(sys.executable, AUDIO, "status")
        return 0 if camera == 0 and audio == 0 else 2
    if action == "prepare":
        return run("bash", INSTALLER, "--prepare")
    if action == "camera":
        return run("bash", INSTALLER, "--activate")
    if action == "stereo":
        print("[kinect2] Utworzy źródła Stereo i Mono; natywne 4ch pozostanie bez zmian.", flush=True)
        print("[kinect2] Nie zmieniam domyślnego mikrofonu systemowego.", flush=True)
        return run(sys.executable, AUDIO, "enable-service")
    if action == "activate":
        print("[kinect2] Basic: aktywacja kamery", flush=True)
        if (code := run("bash", INSTALLER, "--activate")) != 0:
            print("[kinect2] Kamera nie została aktywowana. Audio pozostawiono bez zmian.", file=sys.stderr)
            return code
        print("[kinect2] Basic: aktywacja źródła stereo", flush=True)
        if (code := run(sys.executable, AUDIO, "enable-service")) != 0:
            print(
                "[kinect2] CZĘŚCIOWY SUKCES: kamera jest aktywowana, "
                "profil audio wymaga uwagi. Nie cofnięto działającej kamery. "
                "Zobacz docs/BASIC-ADVANCED.md.",
                file=sys.stderr,
            )
            return code
        print("[kinect2] Kamera oraz źródło stereo aktywowane.", flush=True)
        print("[kinect2] Wybierz Kinect2_Stereo jako mikrofon w aplikacji.", flush=True)
        return 0
    print(f"[kinect2] Nieznane polecenie Basic: {action}", file=sys.stderr)
    return 2


def advanced(action: str, extra: list[str]) -> int:
    if action == "check" and not extra:
        return run("bash", INSTALLER, "--check")
    if action == "audio" and not extra:
        print("[kinect2] Oryginalne cztery kanały ALSA są zachowane.", flush=True)
        return run(sys.executable, AUDIO, "status")
    if action in ADVANCED_COMMANDS:
        return run("bash", CLI, action, *extra)
    print(f"[kinect2] Nieznane polecenie Advanced: {action}", file=sys.stderr)
    return 2


def main(args: list[str] | None = None) -> int:
    argv = sys.argv[1:] if args is None else args
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(help_text())
        return 0
    mode = argv[0].lower()
    if mode not in ("basic", "advanced"):
        print(f"[kinect2] Nieznany tryb: {argv[0]}", file=sys.stderr)
        print(help_text(), file=sys.stderr)
        return 2
    if len(argv) == 1 or argv[1] in ("-h", "--help", "help"):
        print(help_text())
        return 0
    return (basic if mode == "basic" else advanced)(argv[1], argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
