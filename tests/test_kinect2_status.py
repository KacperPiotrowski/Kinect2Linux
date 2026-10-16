import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import json

FILE = Path(__file__).resolve().parents[1] / 'tools/kinect2_status.py'
spec = importlib.util.spec_from_file_location('kinect2_status', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StatusTest(unittest.TestCase):
    def test_service_props(self):
        self.assertEqual(m.service_props('ActiveState=active\nMainPID=123\n'), {'state': 'active', 'pid': 123})
        self.assertEqual(m.service_props(None), {'state': 'unknown', 'pid': None})

    def test_journal_ignores_old_pid(self):
        logs = '\n'.join(json.dumps(x) for x in [
            {'_PID':'1','MESSAGE':'Kinect ON: RGB 1920x1080 @ up to 30 FPS'},
            {'_PID':'2','MESSAGE':'Kinect RGB webcam ready on /dev/video11 (on-demand, Kinect OFF)'},
            {'_PID':'2','MESSAGE':'Camera clients streaming: 1'},
            {'_PID':'2','MESSAGE':'Kinect ON: RGB 1920x1080 @ up to 30 FPS'},
            {'_PID':'2','MESSAGE':'Camera clients streaming: 0'},
            {'_PID':'2','MESSAGE':'STANDBY: Kinect OFF; virtual camera remains available.'}])
        state = m.parse_activity(logs, 2)
        self.assertIs(state['sensor_streaming'], False)
        self.assertEqual(state['streaming_clients'], 0)

    def test_journal_when_pid_unknown(self):
        self.assertIsNone(m.parse_activity('x', None)['sensor_streaming'])

    def test_audio(self):
        a = m.parse_wpctl('''  * audio.channels = "4"\n  * node.name = "alsa_input.usb-Microsoft_Xbox_NUI_Sensor_ABC"\n  * node.description = "Xbox NUI Sensor Analogowe przestrzenne 4.0"''')
        self.assertEqual(a['channels'], 4)
        self.assertTrue(a['is_kinect'])

    def test_unlocked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = m.lock_status(Path(tmp) / 'test.lock')
            self.assertIs(state['held'], False)
            self.assertIsNone(state['owner_pid'])

    def test_locked_file(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.lock'
            with path.open('w') as fd:
                fcntl.flock(fd, fcntl.LOCK_EX)
                state = m.lock_status(path)
                self.assertIs(state['held'], True)
                fcntl.flock(fd, fcntl.LOCK_UN)


if __name__ == '__main__':
    unittest.main()
