#!/usr/bin/env python3
"""Analyze four-channel signed 32-bit PCM WAV from Kinect/ALSA, stdlib only.

Read-only: never normalizes, downmixes, alters or uploads the recording.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import struct
import wave


def analyze(path: Path) -> tuple[int, list[dict[str, float]]]:
    counts = [0, 0, 0, 0]
    totals = [0.0, 0.0, 0.0, 0.0]
    peaks = [0.0, 0.0, 0.0, 0.0]
    zeros = [0, 0, 0, 0]
    with wave.open(str(path), 'rb') as inp:
        channels = inp.getnchannels()
        width = inp.getsampwidth()
        rate = inp.getframerate()
        if channels != 4 or width != 4 or inp.getcomptype() != 'NONE':
            raise ValueError('Wymagany WAV PCM: 4 kanały, 32-bit signed LE (S32_LE).')
        # No hidden sample rate conversion. Report actual header rate to caller.
        while True:
            block = inp.readframes(4096)
            if not block:
                break
            if len(block) % 16 != 0:
                raise ValueError('WAV zawiera niekompletną próbkę 4ch S32_LE.')
            for vals in struct.iter_unpack('<4i', block):
                for i, sample in enumerate(vals):
                    val = sample / 2147483648.0
                    totals[i] += val * val
                    peaks[i] = max(peaks[i], abs(val))
                    counts[i] += 1
                    zeros[i] += sample == 0
    if not all(counts):
        raise ValueError('Nagranie jest puste.')
    stats = []
    for i in range(4):
        rms = math.sqrt(totals[i] / counts[i])
        stats.append({
            'rms_dbfs': 20 * math.log10(max(rms, 1e-12)),
            'peak': peaks[i],
            'zeros_pct': 100.0 * zeros[i] / counts[i],
        })
    return rate, stats


def main() -> int:
    parser = argparse.ArgumentParser(description='Pomiar WAV Kinect 4ch 16kHz S32_LE bez NumPy i konwersji sygnału')
    parser.add_argument('wav', type=Path)
    args = parser.parse_args()
    try:
        rate, stats = analyze(args.wav)
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        parser.exit(1, f'Błąd odczytu WAV: {exc}\n')
    print(f'Kanały: 4, Hz: {rate}, bajtów/próbkę: 4')
    if rate != 16000:
        print('Uwaga: częstotliwość nie jest typowym 16000 Hz dla Kinect v2.')
    for i, channel in enumerate(stats, start=1):
        print(f'Kanał {i}: RMS={channel["rms_dbfs"]:.1f} dBFS | '
              f'Peak={channel["peak"]:.6f} | Zero={channel["zeros_pct"]:.1f}%')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
