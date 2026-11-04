"""Pure, read-only helpers for Kinect2 Studio (no Qt, numpy or USB needed)."""
from __future__ import annotations



def studio_cpu_thread_default(logical_cores: int | None) -> str:
    """Conservative local Studio profile; users may override via ORT env.

    Returns the string for os.environ.setdefault, not a global mutation.
    One thread on single-core machines, at most four on larger CPUs.
    """
    return str(min(4, max(1, logical_cores or 1)))


def audio_presence(pactl_sources: str) -> dict[str, bool]:
    """Only matching live source NAMES count; don't infer signal from 'RUNNING'."""
    names = set()
    for line in pactl_sources.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            names.add(fields[1])
    return {
        "raw": any(
            name.startswith("alsa_input.usb-Microsoft_Xbox_NUI_Sensor_")
            and name.endswith(".analog-surround-40")
            for name in names
        ),
        "mono": "kinect2_linux_mono" in names,
        "stereo": "kinect2_linux_stereo" in names,
    }


def broker_summary(status: dict) -> str:
    """Keep missing/unknown broker fields separate from confirmed activity."""
    preview = status.get("frame_preview")
    if not isinstance(preview, dict):
        preview = {}
    enabled = preview.get("enabled")
    if enabled is not True:
        return "Broker aktywny, ale podgląd klatek nie jest dostępny"
    mode = preview.get("mode", "unknown")
    sensor = status.get("sensor_open")
    streaming = status.get("streaming")
    sensor_label = ("USB otwarte" if sensor is True else
                    "USB zamknięte" if sensor is False else "USB nieznane")
    stream_label = ("streaming" if streaming is True else
                    "standby" if streaming is False else "stan nieznany")
    return f"Broker dostępny · {sensor_label} · {stream_label} · tryb: {mode}"
