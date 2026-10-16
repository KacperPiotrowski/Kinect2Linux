#!/usr/bin/env python3
"""Check public source list for known private/generated Kinect artifacts.

Uses `git ls-files` when available, so ignored local files do not break CI.
Does not inspect previous Git commits, file contents or licenses.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EXT = {'.pyc', '.ply', '.wav', '.flac', '.pcm', '.f32', '.npz', '.pgm', '.ppm', '.task', '.tflite', '.onnx', '.dat'}
FORBIDDEN_SUFFIXES = ('.backup', '.stage1', '.before-status-api', '.before-enoent-fix', '.calibration.json')

result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, check=False)
if result.returncode == 0:
    candidates = [Path(s.decode('utf-8', 'surrogateescape')) for s in result.stdout.split(b'\0') if s]
else:
    candidates = [p.relative_to(ROOT) for p in ROOT.rglob('*')
                  if p.is_file() and '.git' not in p.relative_to(ROOT).parts
                  and '__pycache__' not in p.parts]
problems = []
for rel in candidates:
    parts = rel.parts
    if 'research-data' in parts or '__pycache__' in parts or 'obj' in parts:
        problems.append(str(rel))
    elif (rel.suffix.lower() in FORBIDDEN_EXT or rel.name.endswith(FORBIDDEN_SUFFIXES)):
        problems.append(str(rel))
    elif 'bin' in parts and rel.name != '.gitkeep':
        problems.append(str(rel))
if problems:
    print('Niedozwolone pliki w publicznym drzewie:', *sorted(problems), sep='\n - ', file=sys.stderr)
    sys.exit(1)
print('OK: sprawdzenie nazw plików w publicznym drzewie.')
