#!/bin/bash
# Creates the pygame-display venv and installs/updates dependencies.
# Safe to run repeatedly — exits immediately if everything is already up to date.
# On Raspberry Pi, uses --system-site-packages so that hardware drivers (lgpio,
# spidev, RPi.GPIO) provided by the OS are accessible without needing to build them.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv-pygame-display"

# Recreate the venv if it's missing or lacks system-site-packages access
if [ ! -d "$VENV" ] || ! grep -q "include-system-site-packages = true" "$VENV/pyvenv.cfg" 2>/dev/null; then
    [ -d "$VENV" ] && echo "[display] Recreating venv with system-site-packages..."
    rm -rf "$VENV"
    python3 -m venv --system-site-packages "$VENV"
fi

"$VENV/bin/pip" install -q --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"

# On Raspberry Pi: auto-install the waveshare_epd driver if not already available.
# Looks for the Waveshare e-Paper library cloned from https://github.com/waveshare/e-Paper
if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    if ! "$VENV/bin/python3" -c "from waveshare_epd import epd2in13_V4" 2>/dev/null; then
        for EPAPER_DIR in "$HOME/epaper" "/home/pi/epaper" "/opt/epaper"; do
            if [ -f "$EPAPER_DIR/setup.py" ]; then
                echo "[display] Installing waveshare-epd from $EPAPER_DIR..."
                "$VENV/bin/pip" install -q --disable-pip-version-check "$EPAPER_DIR"
                break
            fi
        done
    fi
fi
