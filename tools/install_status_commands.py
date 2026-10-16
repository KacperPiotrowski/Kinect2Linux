#!/usr/bin/env python3
"""Safely add read-only commands to existing Kinect2-Linux bash launcher.

Preserves all current functionality; backs up original launcher and validates
new bash syntax before atomically installing it. Idempotent.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'kinect2'
MARKER = '  # KINECT2_STATUS_API_READONLY_V1'
CASE_MARKER = 'case "${1:-help}" in'
COMMANDS = '''  # KINECT2_STATUS_API_READONLY_V1
  status)
    shift
    exec python3 "$ROOT/tools/kinect2_status.py" "$@"
    ;;
  devices|clients)
    action="$1"
    shift
    exec python3 "$ROOT/tools/kinect2_inspect.py" "$action" "$@"
    ;;
'''
USAGE_ANCHOR = '  ./kinect2 doctor  -'
USAGE_LINES = '''  ./kinect2 status [--json] - odczyt stanu (bez otwierania Kinecta)
  ./kinect2 devices [--json] - fizyczne i wirtualne urzadzenia
  ./kinect2 clients [--json] - odbiorcy i wlasciciel USB (best effort)
'''


def patched(text: str) -> str:
    if MARKER in text:
        return text
    if text.count(CASE_MARKER) != 1:
        raise ValueError(f'Nie odnaleziono jednoznacznego bloku: {CASE_MARKER}')
    text = text.replace(CASE_MARKER, CASE_MARKER + '\n' + COMMANDS, 1)
    if USAGE_LINES.strip() not in text and USAGE_ANCHOR in text:
        text = text.replace(USAGE_ANCHOR, USAGE_LINES + USAGE_ANCHOR, 1)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description='Integrate Kinect2-Linux read-only status commands')
    parser.add_argument('--check', action='store_true', help='validate but do not modify launcher')
    args = parser.parse_args()
    for script in ('tools/kinect2_status.py', 'tools/kinect2_inspect.py'):
        if not (ROOT / script).is_file():
            raise SystemExit(f'Brak {script}: rozpakuj pakiet Status API przed instalacja')
    if LAUNCHER.is_symlink():
        raise SystemExit('Odmowa: ./kinect2 jest dowiazaniem symbolicznym')
    old = LAUNCHER.read_text(encoding='utf-8')
    new = patched(old)
    if new == old:
        print('Integracja juz obecna — bez zmian.')
        return
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                     dir=ROOT, prefix='.kinect2-status-', delete=False) as tmp:
        tmp.write(new)
        temp_path = Path(tmp.name)
    try:
        subprocess.run(['bash', '-n', str(temp_path)], check=True)
        if args.check:
            print('OK: mozna bezpiecznie zintegrowac status/devices/clients (bez zmian).')
            return
        backup = ROOT / 'kinect2.before-status-api'
        seq = 1
        while backup.exists():
            backup = ROOT / f'kinect2.before-status-api.{seq}'
            seq += 1
        shutil.copy2(LAUNCHER, backup)
        os.chmod(temp_path, stat.S_IMODE(LAUNCHER.stat().st_mode))
        os.replace(temp_path, LAUNCHER)
        print(f'Gotowe. Kopia launchera: {backup.name}')
        print('Przetestuj: ./kinect2 status --json; ./kinect2 devices; ./kinect2 clients')
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == '__main__':
    main()
