"""Hardware-free verification of native 4ch WAV analyzer."""
from pathlib import Path
import importlib.util
import math
import struct
import tempfile
import unittest
import wave

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'audio_raw_analyze.py'
spec = importlib.util.spec_from_file_location('audio_raw_analyze', SCRIPT)
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


class AudioRawTests(unittest.TestCase):
    def test_four_independent_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capture.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(4)
                wav.setsampwidth(4)
                wav.setframerate(16000)
                wav.writeframes(struct.pack('<4i', 1073741824, 0, -1073741824, 2147483647) * 20)
            rate, stats = audio.analyze(path)
        self.assertEqual(rate, 16000)
        self.assertAlmostEqual(stats[0]['rms_dbfs'], 20 * math.log10(.5), places=4)
        self.assertEqual(stats[1]['zeros_pct'], 100.0)
        self.assertEqual(stats[0]['zeros_pct'], 0.0)
        self.assertAlmostEqual(stats[2]['peak'], .5)
        self.assertGreater(stats[3]['peak'], .999)

    def test_reject_wrong_channel_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'stereo.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(4)
                wav.setframerate(16000)
                wav.writeframes(b'\0' * 800)
            with self.assertRaisesRegex(ValueError, '4 kanały'):
                audio.analyze(path)

    def test_reject_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'empty.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(4)
                wav.setsampwidth(4)
                wav.setframerate(16000)
            with self.assertRaisesRegex(ValueError, 'puste'):
                audio.analyze(path)
