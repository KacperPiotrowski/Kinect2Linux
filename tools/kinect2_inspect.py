#!/usr/bin/env python3
"""Read-only `kinect2 devices` and `kinect2 clients` views.

No extra dependencies. Uses the existing, tested status collector without
opening the sensor or changing system settings.
"""
from __future__ import annotations

import argparse
import json

import kinect2_status as status


def label(value: object) -> str:
    if value is None:
        return 'nieustalone'
    if value is True:
        return 'tak'
    if value is False:
        return 'nie'
    return str(value)


def select_view(data: dict, action: str) -> dict:
    if action == 'devices':
        return {
            'schema_version': data['schema_version'],
            'timestamp': data['timestamp'],
            'physical': data['device'],
            'video': {
                'rgb': {'path': data['rgb']['virtual_device'], 'present': data['rgb']['present']},
                'ir': {'path': data['ir']['virtual_device'], 'present': data['ir']['present']},
            },
            'default_audio_source': data['audio']['default_source'],
        }
    if action == 'clients':
        return {
            'schema_version': data['schema_version'],
            'timestamp': data['timestamp'],
            'rgb': {
                'service': data['rgb']['service'],
                'bridge_pid': data['rgb']['bridge_pid'],
                'sensor_streaming_last_known': data['rgb']['sensor_streaming'],
                'streaming_clients_last_known': data['rgb']['streaming_clients'],
                'last_event_at': data['rgb']['last_event_at'],
                'state_source': data['rgb'].get('state_source', 'unknown'),
                'state_fresh': data['rgb'].get('state_fresh', False),
                'state_age_ms': data['rgb'].get('state_age_ms'),
                'state_updated_at': data['rgb'].get('state_updated_at'),
                'capture_stats': data['rgb'].get('capture_stats'),
                'openers_not_necessarily_streaming': data['rgb']['openers'],
            },
            'usb_lock': data['usb_lock'],
            'note': ('Swieze dane pochodza z aktualizowanego stanu mostka; w przeciwnym razie '
                     'dane sa ostatnim znanym stanem. Otwarty deskryptor V4L2 nie dowodzi odbioru. '
                     'PipeWire moze ukrywac odbiorce.'),
        }
    raise ValueError(f'Unknown action: {action}')


def pretty_devices(view: dict) -> str:
    physical = view['physical']
    lines = [f"Kinect USB: {label(physical['connected'])} ({len(physical['sensors'])} urzadzen)"]
    for sensor in physical['sensors']:
        lines.append(f"  Kinect v2: serial={sensor.get('serial') or '?'}  USB={sensor.get('usb_device') or '?'}")
    lines.append('Kamery wirtualne (istnienie nie oznacza, ze fizyczny sensor strumieniuje):')
    for name, item in view['video'].items():
        lines.append(f"  {name.upper()}: {item['path']} — {'obecna' if item['present'] else 'brak'}")
    mic = view['default_audio_source']
    lines.append(f"Domyslny mikrofon: {mic.get('description') or mic.get('name') or 'nieustalony'}; "
                 f"kanaly: {label(mic.get('channels'))}")
    return '\n'.join(lines)


def pretty_clients(view: dict) -> str:
    rgb, lock = view['rgb'], view['usb_lock']
    lines = [
        f"Most RGB: usluga={rgb['service']} | PID={label(rgb['bridge_pid'])}",
        f"Kinect RGB strumieniuje ({'na żywo' if rgb['state_fresh'] else 'ostatni znany stan'}): {label(rgb['sensor_streaming_last_known'])}",
        f"Odbiorcy strumienia ({'na żywo' if rgb['state_fresh'] else 'ostatnie zdarzenie'}): {label(rgb['streaming_clients_last_known'])}",
        f"Źródło statusu: {rgb['state_source']} | wiek: {label(rgb['state_age_ms'])} ms",
        f"Ostatnia aktualizacja: {label(rgb['state_updated_at'] or rgb['last_event_at'])}",
        f"Blokada USB: {label(lock['held'])} | wlasciciel: {label(lock['owner_name'])} "
        f"PID={label(lock['owner_pid'])}",
        'Procesy z otwarta kamera (to NIE dowodzi pobierania klatek):',
    ]
    if not rgb['openers_not_necessarily_streaming']:
        lines.append('  brak widocznych procesow')
    else:
        for proc in rgb['openers_not_necessarily_streaming']:
            lines.append(f"  PID {proc['pid']}: {proc['process'] or '?'} [{proc['role']}]")
    lines.append('Uwaga: przy PipeWire/portalach faktyczny odbiorca moze byc niewidoczny.')
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Kinect2-Linux read-only devices/clients views')
    parser.add_argument('action', choices=('devices', 'clients'))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    view = select_view(status.get_status(), args.action)
    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print(pretty_devices(view) if args.action == 'devices' else pretty_clients(view))


if __name__ == '__main__':
    main()
