#!/bin/bash
# Creates the pygame-display venv and installs/updates dependencies.
# Safe to run repeatedly — exits immediately if everything is already up to date.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv-pygame-display"

if [ ! -d "$VENV" ]; then
    echo "[display] Creating virtual environment..."
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install -q --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"
