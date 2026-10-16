import importlib.util
import json
from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sp = importlib.util.spec_from_file_location('kinect2_status', HERE / 'tools' / 'kinect2_status.py')
s = importlib.util.module_from_spec(sp)
sp.loader.exec_module(s)

ip = importlib.util.spec_from_file_location('kinect2_inspect', HERE / 'tools' / 'kinect2_inspect.py')
# Import via path, as normal CLI would do.
import sys
sys.path.insert(0, str(HERE / 'tools'))
import kinect2_inspect as inspect


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'kinect2-rgb-state.json'
        self.state = {'schema_version': 1, 'pid': 1001, 'sensor_streaming': True,
                      'streaming_clients': 1, 'timestamp_unix_ms': 1792160000000,
                      'monotonic_ns': 17_000_000_000, 'frames': 150, 'seq_gaps': 0,
                      'output_drops': 0}

    def write(self):
        self.path.write_text(json.dumps(self.state))

    def test_fresh_snapshot(self):
        self.write()
        live = s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000)
        self.assertTrue(live['state_fresh'])
        self.assertEqual(live['streaming_clients'], 1)
        self.assertEqual(live['state_age_ms'], 1000)
        self.assertEqual(live['capture_stats']['frames'], 150)

    def test_stale_snapshot(self):
        self.write()
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=21_000_000_000))

    def test_future_snapshot(self):
        self.write()
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=16_000_000_000))

    def test_wrong_pid(self):
        self.write()
        self.assertIsNone(s.read_live_rgb(self.path, 1002, now_ns=18_000_000_000))

    def test_malformed(self):
        self.path.write_text('{bad json')
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000))

    def test_invalid_types(self):
        self.state['streaming_clients'] = True
        self.write()
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000))

    def test_symlink_rejected(self):
        backing = self.path.with_suffix('.real')
        backing.write_text(json.dumps(self.state))
        self.path.symlink_to(backing)
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000))

    def test_oversized_rejected(self):
        self.path.write_text(' ' * 5000)
        self.assertIsNone(s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000))

    def test_zero_client_standby(self):
        self.state['streaming_clients'] = 0
        self.state['sensor_streaming'] = False
        self.write()
        live = s.read_live_rgb(self.path, 1001, now_ns=18_000_000_000)
        self.assertFalse(live['sensor_streaming'])

    def test_live_takes_precedence_without_journal(self):
        self.state['monotonic_ns'] = time.monotonic_ns()
        self.write()
        with patch.object(s, 'STATE_PATH', self.path), \
             patch.object(s, 'command') as command, \
             patch.object(s, 'physical_sensors', return_value=[]), \
             patch.object(s, 'device_present', return_value=False), \
             patch.object(s, 'camera_openers', return_value=[]), \
             patch.object(s, 'lock_status', return_value={'held': False}):
            def fake_command(*args, **kwargs):
                if args[0] == 'systemctl': return 'ActiveState=active\nMainPID=1001\n'
                if args[0] == 'journalctl': self.fail('Journal should not be read for live state')
                return None
            command.side_effect = fake_command
            value = s.get_status()
        self.assertEqual(value['rgb']['state_source'], 'bridge_runtime')
        self.assertTrue(value['rgb']['state_fresh'])

    def test_fallback_marked_not_fresh(self):
        self.write()
        with patch.object(s, 'STATE_PATH', self.path), \
             patch.object(s, 'command') as command, \
             patch.object(s, 'physical_sensors', return_value=[]), \
             patch.object(s, 'device_present', return_value=False), \
             patch.object(s, 'camera_openers', return_value=[]), \
             patch.object(s, 'lock_status', return_value={'held': False}):
            def fake_command(*args, **kwargs):
                if args[0] == 'systemctl': return 'ActiveState=active\nMainPID=1002\n'
                if args[0] == 'journalctl': return json.dumps({'_PID':'1002','MESSAGE':'Camera clients streaming: 1'})
                return None
            command.side_effect = fake_command
            value = s.get_status()
        self.assertEqual(value['rgb']['state_source'], 'journal_last_known')
        self.assertFalse(value['rgb']['state_fresh'])

    def test_cli_view_preserves_staleness(self):
        data = {'schema_version': 1, 'timestamp': 'now', 'usb_lock': {'held': False, 'owner_name': None, 'owner_pid': None},
                'rgb': {'service': 'active', 'bridge_pid': 1001, 'sensor_streaming': False,
                        'streaming_clients': 0, 'last_event_at': None, 'state_source': 'bridge_runtime',
                        'state_fresh': True, 'state_age_ms': 100, 'state_updated_at': 'now',
                        'capture_stats': {'frames': 0}, 'openers': []}}
        view = inspect.select_view(data, 'clients')
        self.assertTrue(view['rgb']['state_fresh'])
        self.assertEqual(view['rgb']['capture_stats']['frames'], 0)
        self.assertIn('na żywo', inspect.pretty_clients(view))


if __name__ == '__main__':
    unittest.main()
