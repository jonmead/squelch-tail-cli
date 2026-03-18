"""PulseAudio volume control via pactl."""

import subprocess
import sys


def set_pulse_volume(percent: int) -> None:
    """Set the default PulseAudio sink volume (0–150%)."""
    percent = max(0, min(150, int(percent)))
    try:
        subprocess.run(
            ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{percent}%'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except FileNotFoundError:
        pass  # pactl not installed (no PipeWire/PulseAudio)
    except Exception as e:
        print(f'[volume] pactl set failed: {e}', file=sys.stderr)


def get_pulse_volume() -> int:
    """Return the current default sink volume as an integer percentage (0–150)."""
    try:
        result = subprocess.run(
            ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
            capture_output=True,
            text=True,
            timeout=2,
        )
        # Output contains tokens like "100%"
        for token in result.stdout.split():
            if token.endswith('%'):
                return int(token.rstrip('%'))
    except Exception:
        pass
    return 100
