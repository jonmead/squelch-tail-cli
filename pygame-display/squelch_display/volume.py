"""PipeWire volume control via wpctl."""

import subprocess
import sys


def set_pulse_volume(percent: int) -> None:
    """Set the default sink volume (0–150%)."""
    percent = max(0, min(150, int(percent)))
    try:
        subprocess.run(
            ['wpctl', 'set-volume', '@DEFAULT_SINK@', f'{percent}%'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except FileNotFoundError:
        pass  # wpctl not installed
    except Exception as e:
        print(f'[volume] wpctl set failed: {e}', file=sys.stderr)


def get_pulse_volume() -> int:
    """Return the current default sink volume as an integer percentage (0–150)."""
    try:
        result = subprocess.run(
            ['wpctl', 'get-volume', '@DEFAULT_SINK@'],
            capture_output=True,
            text=True,
            timeout=2,
        )
        # Output is "Volume: 0.80" — convert to percentage
        for token in result.stdout.split():
            try:
                return round(float(token) * 100)
            except ValueError:
                continue
    except Exception:
        pass
    return 100
