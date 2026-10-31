"""Mock PipeWire/Pulse CLI; no microphone or systemd writes in offline tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/kinect2_audio_profiles.py"
HARDWARE = "alsa_input.usb-Microsoft_Xbox_NUI_Sensor_TEST-02.analog-surround-40"


class AudioProfileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="kinect2-audio-test-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.home, self.runtime, self.bin = root / "home", root / "runtime", root / "bin"
        for path in (self.home, self.runtime, self.bin):
            path.mkdir()
        self.db = root / "db.json"
        self.log = root / "sysctl.log"
        self.db.write_text(json.dumps({
            "hardware": True,
            "modules": {
                "17": {"name": "module-remap-source", "args":
                       "master=" + HARDWARE + " source_name=kinect2_mono_test channels=1"}
            }, "next": 536870916,
        }))
        pactl = self.bin / "pactl"
        pactl.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
dbfile = Path(os.environ["MOCK_PACTL_DB"])
db = json.loads(dbfile.read_text())
args = sys.argv[1:]
if not db.get("online", True):
    print("Connection refused", file=sys.stderr)
    sys.exit(1)
if args == ["list", "short", "sources"]:
    if db.get("hardware"):
        print("29\\talsa_input.usb-Microsoft_Xbox_NUI_Sensor_TEST-02.analog-surround-40\\tPipeWire\\ts32le 4ch 16000Hz\\tSUSPENDED")
    for mid, m in db["modules"].items():
        for arg in m["args"].split():
            if arg.startswith("source_name="):
                print("49\\t" + arg.partition("=")[2] + "\\tPipeWire\\ts16le 1ch 16000Hz\\tSUSPENDED")
elif args == ["list", "short", "modules"]:
    for mid, m in db["modules"].items():
        print(mid + "\\t" + m["name"] + "\\t" + m["args"])
elif args[:2] == ["load-module", "module-remap-source"]:
    module_id = str(db["next"])
    db["next"] += 1
    db["modules"][module_id] = {"name": "module-remap-source", "args": " ".join(args[2:])}
    print(module_id)
elif args[:1] == ["unload-module"]:
    db["modules"].pop(args[1])
else:
    print("unexpected pactl invocation", args, file=sys.stderr)
    sys.exit(2)
if args[:1] in (["load-module"], ["unload-module"]):
    dbfile.write_text(json.dumps(db))
''')
        pactl.chmod(0o755)
        ctl = self.bin / "systemctl"
        ctl.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_CTL_LOG"\n')
        ctl.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update(HOME=str(self.home), XDG_RUNTIME_DIR=str(self.runtime),
                        MOCK_PACTL_DB=str(self.db), MOCK_CTL_LOG=str(self.log))
        self.env["PATH"] = str(self.bin) + ":" + self.env.get("PATH", "")

    def run_action(self, arg):
        return subprocess.run(["python3", str(SCRIPT), arg], env=self.env,
                              capture_output=True, text=True, check=False)

    def db_data(self):
        return json.loads(self.db.read_text())

    def save_db(self, **changes):
        db = self.db_data()
        db.update(changes)
        self.db.write_text(json.dumps(db))

    def wait_for(self, predicate, *, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.05)
        self.fail("audio watcher did not reach expected state within 5 seconds")

    def spawn_watch(self):
        process = subprocess.Popen(
            ["python3", str(SCRIPT), "watch", "--poll-seconds", "0.1"],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        def stop_process():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)

        self.addCleanup(stop_process)
        return process

    def test_status_is_read_only(self):
        response = self.run_action("status")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("Kinect 4ch: available", response.stdout)
        self.assertIn("Kinect2_Mono: inactive", response.stdout)
        self.assertFalse((self.runtime / "kinect2-linux-audio-profiles.json").exists())

    def test_start_adds_two_options_preserves_default_and_is_idempotent(self):
        result = self.run_action("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        modules = self.db_data()["modules"]
        self.assertEqual(len(modules), 3)
        args = {entry["args"].split("source_name=")[1].split()[0]: entry["args"]
                for entry in modules.values()}
        self.assertIn("channels=1 channel_map=mono master_channel_map=front-left remix=no",
                      args["kinect2_linux_mono"])
        self.assertIn("channels=2 channel_map=front-left,front-right master_channel_map=front-left,front-right remix=no",
                      args["kinect2_linux_stereo"])
        self.assertIn("kinect2_mono_test", args)
        self.assertTrue(self.db_data()["hardware"])
        self.assertEqual(self.run_action("start").returncode, 0)
        self.assertEqual(len(self.db_data()["modules"]), 3)

    def test_stop_leaves_untracked_and_raw_source(self):
        self.assertEqual(self.run_action("start").returncode, 0)
        self.assertEqual(self.run_action("stop").returncode, 0)
        db = self.db_data()
        self.assertEqual(list(db["modules"]), ["17"])
        self.assertTrue(db["hardware"])
        self.assertEqual(self.run_action("stop").returncode, 0)

    def test_missing_hardware_fails_without_changes(self):
        db = self.db_data()
        db["hardware"] = False
        self.db.write_text(json.dumps(db))
        response = self.run_action("start")
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("Expected exactly one Kinect", response.stderr)
        self.assertEqual(len(self.db_data()["modules"]), 1)

    def test_foreign_alias_refused(self):
        db = self.db_data()
        db["modules"]["23"] = {
            "name": "module-remap-source",
            "args": "master=" + HARDWARE + " source_name=kinect2_linux_mono remix=no",
        }
        self.db.write_text(json.dumps(db))
        result = self.run_action("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exists but is not tracked", result.stderr)
        self.assertEqual(len(self.db_data()["modules"]), 2)

    def test_service_installed_disabled_no_audio_changes(self):
        result = self.run_action("install-service")
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = self.home / ".config/systemd/user/kinect2-audio-profiles.service"
        self.assertIn("Type=simple", unit.read_text())
        self.assertIn("ExecStart=/usr/bin/python3 %h/.local/bin/kinect2-audio-profiles watch", unit.read_text())
        self.assertIn("Restart=on-failure", unit.read_text())
        self.assertNotIn("RemainAfterExit=yes", unit.read_text())
        self.assertIn("ExecStop=", unit.read_text())
        self.assertEqual(self.log.read_text().splitlines(), ["--user daemon-reload"])
        self.assertEqual(len(self.db_data()["modules"]), 1)
        self.assertEqual(self.run_action("install-service").returncode, 0)

    def test_service_refuses_ephemeral_standalone_script(self):
        import shutil
        temp_script = self.bin / "kinect2_audio_profiles.py"
        shutil.copyfile(SCRIPT, temp_script)
        response = subprocess.run(["python3", str(temp_script), "install-service"],
                                  env=self.env, capture_output=True, text=True)
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("persistent Kinect2Linux repository checkout", response.stderr)
        self.assertFalse((self.home / ".config/systemd/user/kinect2-audio-profiles.service").exists())

    def test_service_refuses_foreign_unit(self):
        unit = self.home / ".config/systemd/user/kinect2-audio-profiles.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\\nExecStart=/usr/bin/true\\n")
        result = self.run_action("enable-service")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing modified/foreign unit", result.stderr)
        self.assertFalse(self.log.exists())

    def test_upgrade_exact_legacy_managed_service_only(self):
        unit = self.home / ".config/systemd/user/kinect2-audio-profiles.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("""# Managed by Kinect2-Linux optional audio profiles.
[Unit]
Description=Optional Kinect v2 mono + stereo microphone sources
After=pipewire-pulse.socket
Wants=pipewire-pulse.socket

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 %h/.local/bin/kinect2-audio-profiles start
ExecStop=/usr/bin/python3 %h/.local/bin/kinect2-audio-profiles stop

[Install]
WantedBy=default.target
""")
        response = self.run_action("install-service")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("Upgraded the old managed audio unit", response.stdout)
        self.assertIn("Type=simple", unit.read_text())
        self.assertIn(" watch", unit.read_text())

    def test_watcher_waits_for_late_usb_and_repairs_pulse_restart(self):
        # Start the user service while Kinect has not yet been enumerated.
        self.save_db(hardware=False)
        process = self.spawn_watch()
        time.sleep(0.2)
        self.assertIsNone(process.poll())
        self.assertEqual(len(self.db_data()["modules"]), 1)

        # Kinect becomes visible AFTER systemd starts the watcher.
        self.save_db(hardware=True)
        self.wait_for(lambda: len(self.db_data()["modules"]) == 3)
        self.assertEqual(self.run_action("status").returncode, 0)

        # PipeWire disappears and comes back: old remap module IDs are lost.
        self.save_db(online=False)
        time.sleep(0.2)
        db = self.db_data()
        db["modules"] = {"17": db["modules"]["17"]}
        db["online"] = True
        self.db.write_text(json.dumps(db))
        self.wait_for(lambda: len(self.db_data()["modules"]) == 3)
        self.assertIsNone(process.poll())

        # Physical hot-unplug: remove only our aliases, not a foreign one.
        self.save_db(hardware=False)
        self.wait_for(lambda: list(self.db_data()["modules"]) == ["17"])
        self.assertIsNone(process.poll())

        # Replugging the sensor recovers both profiles without a manual restart.
        self.save_db(hardware=True)
        self.wait_for(lambda: len(self.db_data()["modules"]) == 3)

    def test_watcher_never_takes_over_foreign_alias(self):
        db = self.db_data()
        db["modules"]["23"] = {
            "name": "module-remap-source",
            "args": "master=" + HARDWARE + " source_name=kinect2_linux_mono remix=no",
        }
        self.db.write_text(json.dumps(db))
        process = self.spawn_watch()
        time.sleep(0.35)
        self.assertIsNone(process.poll())
        self.assertEqual(len(self.db_data()["modules"]), 2)

    def test_enable_service_explicit(self):
        result = self.run_action("enable-service")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [
            "--user daemon-reload",
            "--user enable --now kinect2-audio-profiles.service",
        ])


if __name__ == "__main__":
    unittest.main()
