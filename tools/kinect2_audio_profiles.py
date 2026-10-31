#!/usr/bin/env python3
"""Opt-in Kinect v2 PipeWire/Pulse mono and stereo remaps; raw 4ch stays unchanged."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

PREFIX = "alsa_input.usb-Microsoft_Xbox_NUI_Sensor_"
SUFFIX = ".analog-surround-40"
STATE_FILE = "kinect2-linux-audio-profiles.json"
SERVICE = "kinect2-audio-profiles.service"
PROFILES = {
    "mono": ("kinect2_linux_mono", "mono", "front-left", "Kinect2_Mono"),
    "stereo": ("kinect2_linux_stereo", "front-left,front-right",
               "front-left,front-right", "Kinect2_Stereo"),
}


class AudioError(Exception):
    pass


def command(*args: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise AudioError(f"Missing program: {args[0]}") from exc
    if result.returncode:
        raise AudioError(f"{args[0]} {args[1] if len(args) > 1 else ''} failed: "
                         f"{result.stderr.strip() or 'nonzero exit status'}")
    return result.stdout.strip()


def state_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_dir():
        raise AudioError("XDG_RUNTIME_DIR missing (log in to a graphical user session).")
    return Path(runtime) / STATE_FILE


def read_state() -> dict:
    file = state_path()
    if not file.exists():
        return {}
    if file.is_symlink() or not file.is_file():
        raise AudioError("Refusing non-regular or symlinked audio state file.")
    try:
        state = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AudioError("Cannot read existing audio profile state; inspect it manually.") from exc
    if not isinstance(state, dict):
        raise AudioError("Unexpected audio state; inspect it manually.")
    return state


def save_state(state: dict) -> None:
    file = state_path()
    if file.is_symlink():
        raise AudioError("Refusing symlinked audio state file.")
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=file.parent,
                                     prefix=".kinect-audio-", delete=False) as tmp:
        os.chmod(tmp.name, 0o600)
        json.dump(state, tmp)
        temp_path = Path(tmp.name)
    try:
        temp_path.replace(file)
    finally:
        temp_path.unlink(missing_ok=True)


def sources() -> list[tuple[str, str]]:
    found = []
    for line in command("pactl", "list", "short", "sources").splitlines():
        fields = line.split()
        if len(fields) >= 4:
            found.append((fields[1], " ".join(fields[3:])))
    return found


def hardware_source() -> str:
    matches = [(name, specs) for name, specs in sources()
               if name.startswith(PREFIX) and name.endswith(SUFFIX)]
    if len(matches) != 1:
        raise AudioError(f"Expected exactly one Kinect v2 Surround 4.0 source; found {len(matches)}.")
    name, specs = matches[0]
    if "4ch" not in specs or "16000Hz" not in specs:
        raise AudioError("Kinect source is not exposed as 4ch / 16000 Hz; refusing mapping.")
    return name


def modules() -> dict[int, tuple[str, dict[str, str]]]:
    result = {}
    for line in command("pactl", "list", "short", "modules").splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) < 2 or not fields[0].isdigit():
            continue
        options = {}
        if len(fields) > 2:
            for part in fields[2].split():
                if "=" in part:
                    key, value = part.split("=", 1)
                    options[key] = value
        result[int(fields[0])] = fields[1], options
    return result


def matches(info: tuple[str, dict[str, str]] | None, name: str, master: str) -> bool:
    if info is None:
        return False
    mod, options = info
    return (mod == "module-remap-source"
            and options.get("source_name") == name
            and options.get("master") == master)


def start(*, quiet: bool = False, master: str | None = None) -> bool:
    """Create only missing owned aliases; report whether any were created."""
    if master is None:
        master = hardware_source()
    state = read_state()
    active = modules()
    created = False
    for key, (name, mapping, original, label) in PROFILES.items():
        rec = state.get(key)
        if isinstance(rec, dict) and isinstance(rec.get("id"), int):
            if matches(active.get(rec["id"]), name, master):
                if not quiet:
                    print(f"{label}: already active")
                continue
        # Never replace or unload someone else's alias.
        if any(info[1].get("source_name") == name for info in active.values()):
            raise AudioError(f"{name} exists but is not tracked by Kinect2Linux; refusing duplicate.")
        opts = (
            "master=" + master, "source_name=" + name,
            "channels=" + ("1" if key == "mono" else "2"),
            "channel_map=" + mapping, "master_channel_map=" + original,
            "remix=no", "source_properties=device.description=" + label,
        )
        value = command("pactl", "load-module", "module-remap-source", *opts)
        if not re.fullmatch(r"[0-9]+", value):
            raise AudioError(f"Unexpected pactl load result for {key}; inspect active modules.")
        module_id = int(value)
        state[key] = {"id": module_id, "master": master}
        save_state(state)
        active[module_id] = ("module-remap-source",
                             {"source_name": name, "master": master})
        created = True
        if not quiet:
            print(f"{label}: created ({module_id})")
    if not quiet:
        print("Original Kinect 4ch source is unchanged. Default microphone was not changed.")
    return created


def stop(*, quiet: bool = False) -> None:
    state = read_state()
    active = modules()
    for key, (name, _, __, label) in PROFILES.items():
        rec = state.get(key)
        if not isinstance(rec, dict) or not isinstance(rec.get("id"), int):
            continue
        ident, master = rec["id"], rec.get("master", "")
        if matches(active.get(ident), name, master):
            command("pactl", "unload-module", str(ident))
            if not quiet:
                print(f"{label}: removed")
        elif not quiet:
            print(f"{label}: previous module is gone; no other module touched")
        state.pop(key)
        save_state(state)
    if not quiet:
        print("Original Kinect 4ch source and unrelated modules remain untouched.")


def watch(poll_seconds: float) -> None:
    """Recover late Kinect discovery, hotplug and PipeWire/Pulse restarts.

    Never opens USB or changes default input. Only tracked remap modules are
    unloaded; foreign aliases remain untouched.
    """
    previous = None
    while True:
        repaired = False
        try:
            master = hardware_source()
        except AudioError as exc:
            state = f"waiting for Kinect/PipeWire: {exc}"
            # Hot-unplug can leave aliases pointing at a vanished master.
            try:
                if read_state():
                    stop(quiet=True)
            except AudioError as cleanup_exc:
                state += f"; cleanup pending: {cleanup_exc}"
        else:
            try:
                repaired = start(quiet=True, master=master)
                state = "profiles ready"
            except AudioError as exc:
                state = f"profiles unavailable: {exc}"
        if state != previous or repaired:
            print(f"Kinect audio monitor: {state}", flush=True)
        previous = state
        time.sleep(poll_seconds)


def status() -> None:
    current = sources()
    state = read_state()
    active = modules()
    matches_4ch = [(name, spec) for name, spec in current
                   if name.startswith(PREFIX) and name.endswith(SUFFIX)]
    print("Kinect 4ch:", "available" if matches_4ch else "not found")
    for key, (name, _, __, label) in PROFILES.items():
        rec = state.get(key)
        owned = (isinstance(rec, dict) and isinstance(rec.get("id"), int)
                 and matches(active.get(rec["id"]), name, rec.get("master", "")))
        present = any(src == name for src, _ in current)
        print(f"{label}: {'active (managed)' if owned else 'present (external)' if present else 'inactive'}")
    print("Original Kinect 4ch stays available independently of these profiles.")


def install_service(enable: bool) -> None:
    if not Path("/usr/bin/python3").is_file():
        raise AudioError("Service requires /usr/bin/python3.")
    source = Path(__file__).resolve()
    # Never persist a systemd launcher pointing at a disposable /tmp smoke-test copy.
    if (source.name != "kinect2_audio_profiles.py" or source.parent.name != "tools"
            or not (source.parent / "install_kinect2.sh").is_file()):
        raise AudioError("Install the service from a persistent Kinect2Linux repository checkout, "
                         "not a temporary standalone copy.")
    home = Path.home()
    bindir = home / ".local/bin"
    unitdir = home / ".config/systemd/user"
    launcher = bindir / "kinect2-audio-profiles"
    unit = unitdir / SERVICE
    # Upgrade only an exact older unit generated by Kinect2Linux itself.
    legacy_body = """# Managed by Kinect2-Linux optional audio profiles.
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
"""
    body = """# Managed by Kinect2-Linux optional audio profiles.
[Unit]
Description=Optional Kinect v2 mono + stereo microphone sources
After=pipewire-pulse.socket
Wants=pipewire-pulse.socket

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/.local/bin/kinect2-audio-profiles watch
ExecStop=/usr/bin/python3 %h/.local/bin/kinect2-audio-profiles stop
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=default.target
"""
    # Validate everything before modifying either path.
    if launcher.is_symlink():
        if launcher.resolve() != source:
            raise AudioError(f"Refusing foreign symlink: {launcher}")
    elif launcher.exists():
        raise AudioError(f"Refusing existing launcher: {launcher}")
    if unit.is_symlink():
        raise AudioError(f"Refusing symlinked unit: {unit}")
    if unit.exists():
        old_body = unit.read_text(encoding="utf-8")
        if old_body not in (body, legacy_body):
            raise AudioError(f"Refusing modified/foreign unit: {unit}")
    bindir.mkdir(parents=True, exist_ok=True)
    unitdir.mkdir(parents=True, exist_ok=True)
    if not launcher.is_symlink():
        launcher.symlink_to(source)
    if not unit.exists():
        with unit.open("x", encoding="utf-8") as output:
            output.write(body)
    elif old_body == legacy_body:
        # Atomically replace this known older unit only. daemon-reload does
        # not implicitly restart the running service.
        import tempfile
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=unitdir,
                prefix=".kinect-audio-unit-", delete=False) as output:
            output.write(body)
            candidate = Path(output.name)
        try:
            candidate.replace(unit)
        finally:
            candidate.unlink(missing_ok=True)
        print("Upgraded the old managed audio unit; restart it to apply.")
    command("systemctl", "--user", "daemon-reload")
    print(f"Installed optional unit {SERVICE} (default: disabled).")
    if enable:
        command("systemctl", "--user", "enable", "--now", SERVICE)
        print("Enabled audio profiles at login; original 4ch source unchanged.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional Kinect v2 4ch + Mono + Stereo PipeWire sources.")
    parser.add_argument("action", nargs="?", choices=("status", "start", "stop", "watch",
                                                      "install-service", "enable-service",
                                                      "disable-service"), default="status")
    parser.add_argument("--poll-seconds", type=float, default=3.0,
                        help="Watch retry interval (default: 3s).")
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 3600:
        parser.error("--poll-seconds must be between 0.1 and 3600.")
    if os.geteuid() == 0:
        parser.exit(2, "Do not run Kinect audio profiles as root or with sudo.\n")
    try:
        if args.action == "start":
            start()
        elif args.action == "stop":
            stop()
        elif args.action == "status":
            status()
        elif args.action == "watch":
            watch(args.poll_seconds)
        elif args.action in ("install-service", "enable-service"):
            install_service(enable=args.action == "enable-service")
        elif args.action == "disable-service":
            command("systemctl", "--user", "disable", "--now", SERVICE)
            stop()  # Stop any manually enabled remaps as well.
    except AudioError as exc:
        print(f"Kinect audio: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
