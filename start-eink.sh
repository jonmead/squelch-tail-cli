#!/bin/bash
# Starts squelch-tail-cli with the e-ink display on a Raspberry Pi.
# Handles nvm PATH, venv setup, and waveshare driver installation automatically.
#
# Optional GPIO button env vars (BCM pin numbers):
#   SQUELCH_BTN_PAUSE=5 SQUELCH_BTN_VOL_UP=6 SQUELCH_BTN_VOL_DN=13 ./start-eink.sh ws://...
#
# Pins used by the Waveshare 2.13" V4 HAT (avoid): 8, 17, 18, 24, 25
# Free pins commonly used for buttons: 5, 6, 13, 19, 26
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load nvm if node isn't already in PATH
if ! command -v node >/dev/null 2>&1; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
fi

if ! command -v node >/dev/null 2>&1; then
    echo "Error: node not found. Install Node.js via nvm or package manager." >&2
    exit 1
fi

# Ensure the Python venv and all dependencies are ready
"$SCRIPT_DIR/pygame-display/ensure-venv.sh"

SQUELCH_DISPLAY_MODE=eink \
SQUELCH_DISPLAY_PYTHON="$SCRIPT_DIR/pygame-display/.venv-pygame-display/bin/python3" \
exec node "$SCRIPT_DIR/index.js" "$@"
