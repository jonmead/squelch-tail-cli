#!/bin/bash
# Starts squelch-tail-cli with the LCD display on a Raspberry Pi.
# Handles nvm PATH, venv setup, and display driver configuration automatically.
# All arguments are passed through to node (e.g. the server URL).
#
# Usage: ./start-lcd.sh ws://<server>:<port> [--fullscreen] [--no-touch]
#
# SDL display driver defaults to kmsdrm. If your LCD uses a framebuffer, set:
#   SDL_VIDEODRIVER=fbcon SDL_FBDEV=/dev/fb1 ./start-lcd.sh ws://...
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

# Default SDL driver for Pi GPIO LCD (kmsdrm). Override via env if needed.
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-kmsdrm}"
export SDL_VIDEO_HIGHDPI_DISABLED=1
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"

SQUELCH_DISPLAY_MODE=lcd \
SQUELCH_DISPLAY_PYTHON="$SCRIPT_DIR/pygame-display/.venv-pygame-display/bin/python3" \
exec node "$SCRIPT_DIR/index.js" "$@"
