#!/usr/bin/env python3
"""Kinect2-Linux read-only status API (v0.1).

Never opens the physical sensor or changes camera, audio, or systemd state.
Best-effort diagnostics from sysfs, systemd, journal, PipeWire and /proc.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import subprocess

SERVICE = 'kinect2-rgb-webcam.service'
RGB_DEV = Path(os.environ.get('KINECT_RGB_DEVICE', '/dev/video11'))
IR_DEV = Path(os.environ.get('KINECT_IR_DEVICE', '/dev/video10'))
LOCK = Path(os.environ.get('XDG_RUNTIME_DIR', str(Path(__file__).resolve().parents[1]))) / 'kinect2-sensor.lock'


def command(*args: str, timeout: float = 3.0) -> str | None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def device_present(path: Path) -> bool:
    try:
        return stat.S_ISCHR(path.stat().st_mode)
    except OSError:
        return False


def physical_sensors() -> list[dict]:
    result = []
    sysfs = Path('/sys/bus/usb/devices')
    try:
        devices = list(sysfs.iterdir())
    except OSError:
        return result
    for dev in devices:
        try:
            vendor = (dev / 'idVendor').read_text().strip().lower()
            product = (dev / 'idProduct').read_text().strip().lower()
            if (vendor, product) != ('045e', '02c4'):
                continue
            def get(name):
                try:
                    return (dev / name).read_text().strip()
                except OSError:
                    return None
            result.append({'usb_device': dev.name, 'serial': get('serial'),
                           'bus': get('busnum'), 'address': get('devnum')})
        except OSError:
            continue
    return result


def service_props(raw: str | None) -> dict:
    props = {}
    for line in (raw or '').splitlines():
        if '=' in line:
            key, val = line.split('=', 1)
            props[key] = val
    try:
        pid = int(props.get('MainPID', '0')) or None
    except ValueError:
        pid = None
    return {'state': props.get('ActiveState', 'unknown'), 'pid': pid}


def parse_activity(raw: str | None, main_pid: int | None) -> dict:
    """Only logs of the *current* bridge PID can represent current state."""
    result = {'sensor_streaming': None, 'streaming_clients': None,
              'last_event': None, 'last_event_at': None}
    if not main_pid or not raw:
        return result
    for line in raw.splitlines():
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            continue
        if str(ev.get('_PID', '')) != str(main_pid):
            continue
        msg = ev.get('MESSAGE', '')
        changed = False
        if msg.startswith('Kinect RGB webcam ready') and '(on-demand' in msg:
            result['sensor_streaming'] = False
            result['streaming_clients'] = 0
            changed = True
        elif msg.startswith('Kinect ON:'):
            result['sensor_streaming'] = True
            changed = True
        elif msg.startswith('STANDBY: Kinect OFF'):
            result['sensor_streaming'] = False
            changed = True
        elif msg.startswith('Kinect RGB stopped:'):
            result['sensor_streaming'] = False
            changed = True
        elif msg.startswith('Camera clients streaming:'):
            found = re.search(r':\s*(\d+)', msg)
            if found:
                result['streaming_clients'] = int(found.group(1))
                changed = True
        if changed:
            result['last_event'] = msg
            try:
                micros = int(ev.get('__REALTIME_TIMESTAMP', ''))
                result['last_event_at'] = dt.datetime.fromtimestamp(
                    micros / 1_000_000, tz=dt.timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                result['last_event_at'] = None
    return result


def parse_wpctl(raw: str | None) -> dict:
    result = {'name': None, 'description': None, 'channels': None, 'is_kinect': None}
    if raw is None:
        return result
    fields = {}
    for key in ('node.name', 'node.description', 'audio.channels'):
        match = re.search(r'^\s*\*?\s*' + re.escape(key) + r'\s*=\s*"?([^"\n]+)', raw, re.MULTILINE)
        if match:
            fields[key] = match.group(1).strip()
    result['name'] = fields.get('node.name')
    result['description'] = fields.get('node.description')
    if 'audio.channels' in fields:
        try:
            result['channels'] = int(fields['audio.channels'])
        except ValueError:
            pass
    if result['name'] or result['description']:
        result['is_kinect'] = ('Xbox_NUI_Sensor' in (result['name'] or '')
                               or 'Xbox NUI Sensor' in (result['description'] or ''))
    return result


def find_lock_pid(raw: str | None, st: os.stat_result) -> int | None:
    """Match flock inode and device from /proc/locks (best effort)."""
    for line in (raw or '').splitlines():
        cols = line.split()
        if len(cols) < 6 or cols[1] != 'FLOCK' or cols[3] != 'WRITE':
            continue
        try:
            maj, minor, inode = cols[5].split(':')
            if (int(maj, 16), int(minor, 16), int(inode)) == (
                    os.major(st.st_dev), os.minor(st.st_dev), st.st_ino):
                pid = int(cols[4])
                return pid if pid > 0 else None
        except (ValueError, IndexError):
            pass
    return None


def process_name(pid: int) -> str | None:
    try:
        return (Path('/proc') / str(pid) / 'comm').read_text().strip()
    except OSError:
        return None


def lock_status(path: Path) -> dict:
    """Read /proc/locks without acquiring a lock or touching sensor hardware."""
    result = {'path': str(path), 'held': None, 'owner_pid': None, 'owner_name': None}
    try:
        st = path.stat()
    except FileNotFoundError:
        result['held'] = False
        return result
    except OSError:
        return result
    try:
        raw = Path('/proc/locks').read_text()
    except OSError:
        return result
    # pid may be unknown because the lock holder is outside our PID namespace.
    for line in raw.splitlines():
        cols = line.split()
        if len(cols) < 6 or cols[1] != 'FLOCK':
            continue
        try:
            maj, minor, inode = cols[5].split(':')
            if (int(maj, 16), int(minor, 16), int(inode)) != (
                    os.major(st.st_dev), os.minor(st.st_dev), st.st_ino):
                continue
            result['held'] = True
            pid = int(cols[4])
            result['owner_pid'] = pid if pid > 0 else None
            if result['owner_pid']:
                result['owner_name'] = process_name(result['owner_pid'])
            return result
        except (ValueError, IndexError):
            continue
    result['held'] = False
    return result


def camera_openers(path: Path, bridge_pid: int | None) -> list[dict]:
    """Visible processes holding a V4L2 node, NOT necessarily active readers.

    PipeWire/portals can hide the actual consuming application.
    """
    targets = []
    proc = Path('/proc')
    if not device_present(path):
        return targets
    try:
        major_minor = path.stat().st_rdev
        processes = proc.iterdir()
    except OSError:
        return targets
    for p in processes:
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        try:
            fds = (p / 'fd').iterdir()
            hit = False
            for fd in fds:
                try:
                    fstat = os.stat(fd)
                    if fstat.st_rdev == major_minor and stat.S_ISCHR(fstat.st_mode):
                        hit = True
                        break
                except OSError:
                    continue
            if hit:
                targets.append({'pid': pid, 'process': process_name(pid),
                                'role': 'bridge' if pid == bridge_pid else 'opener_not_proven_streaming'})
        except OSError:
            continue
    return sorted(targets, key=lambda x: x['pid'])


def get_status() -> dict:
    props = service_props(command('systemctl', '--user', 'show', SERVICE,
                                  '-p', 'ActiveState', '-p', 'MainPID'))
    journal = None
    if props['state'] == 'active' and props['pid']:
        journal = command('journalctl', '--user', '-b', '-u', SERVICE, '-n', '1000',
                          '-o', 'json', '--no-pager', timeout=4.0)
    activity = parse_activity(journal, props['pid'])
    audio = parse_wpctl(command('wpctl', 'inspect', '@DEFAULT_AUDIO_SOURCE@'))
    sensors = physical_sensors()
    return {
        'schema_version': 1,
        'timestamp': dt.datetime.now(dt.timezone.utc).isoformat(),
        'device': {'connected': bool(sensors), 'sensors': sensors},
        'rgb': {'virtual_device': str(RGB_DEV), 'present': device_present(RGB_DEV),
                'service': props['state'], 'bridge_pid': props['pid'],
                **activity, 'openers': camera_openers(RGB_DEV, props['pid'])},
        'ir': {'virtual_device': str(IR_DEV), 'present': device_present(IR_DEV)},
        'audio': {'default_source': audio},
        'usb_lock': lock_status(LOCK),
        'note': ('Device USB, V4L2 and microphone states are distinct. '
                 'Openers are not necessarily actual viewers; PipeWire/portals '
                 'may obscure consumer identity. Null means unknown.'),
    }


def pretty(v: dict) -> str:
    device = v['device']
    rgb = v['rgb']
    lock = v['usb_lock']
    audio = v['audio']['default_source']
    def label(val):
        return 'nieustalone' if val is None else ('tak' if val is True else 'nie' if val is False else str(val))
    lines = [
        f"Kinect USB: {'podłączony' if device['connected'] else 'nie wykryto (USB sysfs)'}",
        f"RGB: {rgb['virtual_device']} | usługa={rgb['service']} | PID={label(rgb['bridge_pid'])}",
        f"RGB aktywny: {label(rgb['sensor_streaming'])} | odbiorcy strumienia: {label(rgb['streaming_clients'])}",
        f"IR: {v['ir']['virtual_device']} (urządzenie wirtualne: {label(v['ir']['present'])})",
        f"USB zajęte przez proces Kinect2-Linux (flock): {label(lock['held'])}",
        f"Właściciel blokady: {label(lock['owner_name'])} PID={label(lock['owner_pid'])}",
        f"Domyślny mikrofon: {audio['description'] or audio['name'] or 'nieustalony'}",
        f"Liczba kanałów domyślnego mikrofonu: {label(audio['channels'])}",
    ]
    if rgb['openers']:
        lines.append('Procesy z otwartym /dev/video11 (niekoniecznie nagrywające):')
        for proc in rgb['openers']:
            lines.append(f"  PID {proc['pid']}: {proc['process'] or '?'} ({proc['role']})")
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Kinect2-Linux read-only status API')
    parser.add_argument('--json', action='store_true', help='print machine-readable JSON')
    args = parser.parse_args()
    result = get_status()
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else pretty(result))


if __name__ == '__main__':
    main()
