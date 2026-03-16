#!/bin/bash
VENV_DIR="$(pwd)/.venv-pygame-display"
echo $VENV_DIR

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
fi
    echo "Activating virtual environment"
    pwd
    source "$VENV_DIR/bin/activate"
    echo "Installing requirements"
    pip3 install -r requirements.txt
