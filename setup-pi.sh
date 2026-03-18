#!/usr/bin/env bash
# setup-pi.sh — Guided setup script for squelch-tail-cli on Raspberry Pi
# Supports: E-ink Waveshare 2.13" V4 and LCD 480×320 HAT display modes
#
# Usage: ./setup-pi.sh
#
# Run this on the Pi. It is idempotent — safe to re-run.

# ---------------------------------------------------------------------------
# Resolve script directory regardless of where the script is called from
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}  [OK]${RESET} $*"; }
warn() { echo -e "${YELLOW}  [WARN]${RESET} $*"; }
err()  { echo -e "${RED}  [ERROR]${RESET} $*"; }
step() { echo -e "\n${CYAN}━━━ $* ━━━${RESET}"; }

# ---------------------------------------------------------------------------
# Prompt helper
# ---------------------------------------------------------------------------
ask_yes_no() {
    # ask_yes_no "Question?" [default=y]
    local prompt="$1"
    local default="${2:-y}"
    local reply
    if [[ "$default" == "y" ]]; then
        read -r -p "$(echo -e "${YELLOW}${prompt} [Y/n]:${RESET} ")" reply
        reply="${reply:-y}"
    else
        read -r -p "$(echo -e "${YELLOW}${prompt} [y/N]:${RESET} ")" reply
        reply="${reply:-n}"
    fi
    [[ "$reply" =~ ^[Yy] ]]
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║          squelch-tail-cli — Pi Setup Script          ║"
echo "║                                                      ║"
echo "║  Sets up everything needed to run the scanner       ║"
echo "║  radio display on a Raspberry Pi.                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  Working directory: ${SCRIPT_DIR}"
echo ""

# ---------------------------------------------------------------------------
# Track state for final summary
# ---------------------------------------------------------------------------
SPI_JUST_ENABLED=false
GROUPS_ADDED=()
DISPLAY_TYPE=""

# ---------------------------------------------------------------------------
# Step 0: Choose display type
# ---------------------------------------------------------------------------
step "Display Type Selection"
echo "  Which display will you be using?"
echo "  (1) E-ink Waveshare 2.13\" V4  (250×122, B&W, SPI HAT)"
echo "  (2) LCD 480×320 HAT            (colour, SPI/GPIO or HDMI)"
echo ""
while true; do
    read -r -p "$(echo -e "${YELLOW}  Enter 1 or 2:${RESET} ")" DISPLAY_CHOICE
    case "$DISPLAY_CHOICE" in
        1) DISPLAY_TYPE="eink"; ok "Selected: E-ink"; break ;;
        2) DISPLAY_TYPE="lcd";  ok "Selected: LCD";   break ;;
        *) warn "Please enter 1 or 2." ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1: OS check
# ---------------------------------------------------------------------------
step "Step 1: OS Check"

if [[ -f /proc/device-tree/model ]]; then
    MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')
    if [[ "$MODEL" == *"Raspberry Pi"* ]]; then
        ok "Detected: ${MODEL}"
    else
        warn "This does not appear to be a Raspberry Pi (model: ${MODEL})."
        if ! ask_yes_no "Continue anyway?" "n"; then
            echo "Aborted."
            exit 1
        fi
    fi
else
    warn "/proc/device-tree/model not found — cannot confirm this is a Raspberry Pi."
    if ! ask_yes_no "Continue anyway?" "n"; then
        echo "Aborted."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: SPI enable
# ---------------------------------------------------------------------------
step "Step 2: SPI Enable"

CONFIG_FILE="/boot/firmware/config.txt"

if [[ ! -f "$CONFIG_FILE" ]]; then
    warn "${CONFIG_FILE} not found — skipping SPI check."
elif grep -q "^dtparam=spi=on" "$CONFIG_FILE" 2>/dev/null; then
    ok "SPI already enabled in ${CONFIG_FILE}"
else
    echo "  SPI is not enabled. Enabling now..."
    if sudo bash -c "echo 'dtparam=spi=on' >> ${CONFIG_FILE}"; then
        ok "Added 'dtparam=spi=on' to ${CONFIG_FILE}"
        SPI_JUST_ENABLED=true
        warn "A reboot will be required before the display will work, but setup will continue."
    else
        err "Failed to write to ${CONFIG_FILE}. You may need to enable SPI manually via raspi-config."
    fi
fi

# ---------------------------------------------------------------------------
# Step 3: User groups
# ---------------------------------------------------------------------------
step "Step 3: User Groups"

REQUIRED_GROUPS=(spi i2c gpio)

for grp in "${REQUIRED_GROUPS[@]}"; do
    if id -nG "$USER" | grep -qw "$grp"; then
        ok "User '${USER}' is already in group '${grp}'"
    else
        echo "  Adding '${USER}' to group '${grp}'..."
        if sudo usermod -aG "$grp" "$USER"; then
            ok "Added '${USER}' to group '${grp}'"
            GROUPS_ADDED+=("$grp")
        else
            warn "Could not add '${USER}' to group '${grp}'. The group may not exist yet."
        fi
    fi
done

if [[ ${#GROUPS_ADDED[@]} -gt 0 ]]; then
    warn "Group changes take effect on next login."
fi

# ---------------------------------------------------------------------------
# Step 4: System packages
# ---------------------------------------------------------------------------
step "Step 4: System Packages"

REQUIRED_PACKAGES=(ffmpeg python3-lgpio python3-spidev python3-gpiozero git curl)

echo "  Updating package index..."
sudo apt-get update -qq

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if dpkg -s "$pkg" &>/dev/null 2>&1; then
        ok "${pkg} already installed"
    else
        echo "  Installing ${pkg}..."
        if sudo apt-get install -y -qq "$pkg"; then
            ok "${pkg} installed"
        else
            err "Failed to install ${pkg}. Check your internet connection and apt sources."
        fi
    fi
done

# ---------------------------------------------------------------------------
# Step 5: Node.js via nvm
# ---------------------------------------------------------------------------
step "Step 5: Node.js via nvm"

NVM_DIR="${HOME}/.nvm"
NVM_SCRIPT="${NVM_DIR}/nvm.sh"

if [[ -f "$NVM_SCRIPT" ]]; then
    ok "nvm already installed at ${NVM_DIR}"
else
    echo "  Installing nvm..."
    # Download and run the nvm install script
    if curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/HEAD/install.sh | bash; then
        ok "nvm installed"
    else
        err "nvm installation failed. Install manually from https://github.com/nvm-sh/nvm"
        echo "  Continuing — you can install Node.js later."
    fi
fi

# Source nvm so we can use it in this session
if [[ -f "$NVM_SCRIPT" ]]; then
    # shellcheck disable=SC1090
    source "$NVM_SCRIPT"
    ok "nvm sourced"
else
    warn "nvm script not found at ${NVM_SCRIPT} — skipping Node.js setup."
fi

# Check if node is available; install LTS if not
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version)
    ok "Node.js already available: ${NODE_VERSION}"
else
    echo "  Node.js not found — installing LTS..."
    if nvm install --lts; then
        NODE_VERSION=$(node --version)
        ok "Node.js LTS installed: ${NODE_VERSION}"
    else
        err "nvm install --lts failed. You may need to install Node.js manually."
    fi
fi

# Check npm
if command -v npm &>/dev/null; then
    NPM_VERSION=$(npm --version)
    ok "npm available: ${NPM_VERSION}"
else
    err "npm not found. Something may have gone wrong with the Node.js install."
fi

# ---------------------------------------------------------------------------
# Step 6: Waveshare e-Paper library (eink only)
# ---------------------------------------------------------------------------
if [[ "$DISPLAY_TYPE" == "eink" ]]; then
    step "Step 6: Waveshare e-Paper Library (E-ink)"

    EPAPER_DIR="${HOME}/epaper"

    if [[ -f "${EPAPER_DIR}/setup.py" ]]; then
        ok "Waveshare e-Paper library already cloned at ${EPAPER_DIR}"
    else
        echo "  Cloning Waveshare e-Paper library to ${EPAPER_DIR}..."
        if git clone https://github.com/waveshare/e-Paper "$EPAPER_DIR"; then
            ok "Cloned Waveshare e-Paper library to ${EPAPER_DIR}"
        else
            err "Failed to clone Waveshare e-Paper library."
            warn "The display will run in simulation mode until the library is available."
            warn "Try manually: git clone https://github.com/waveshare/e-Paper ~/epaper"
        fi
    fi
else
    step "Step 6: Waveshare e-Paper Library (Skipped — LCD mode)"
    ok "Not required for LCD display mode"
fi

# ---------------------------------------------------------------------------
# Step 7: npm install
# ---------------------------------------------------------------------------
step "Step 7: npm Install"

echo "  Running npm install in ${SCRIPT_DIR}..."
if (cd "$SCRIPT_DIR" && npm install --silent); then
    ok "npm install completed"
else
    err "npm install failed. Check Node.js is installed and ${SCRIPT_DIR}/package.json exists."
fi

# ---------------------------------------------------------------------------
# Step 8: Python venv setup
# ---------------------------------------------------------------------------
step "Step 8: Python Virtual Environment"

ENSURE_VENV="${SCRIPT_DIR}/pygame-display/ensure-venv.sh"

if [[ ! -f "$ENSURE_VENV" ]]; then
    err "ensure-venv.sh not found at ${ENSURE_VENV}"
    err "The repository may be incomplete. Try re-cloning."
else
    echo "  Running ${ENSURE_VENV}..."
    if bash "$ENSURE_VENV"; then
        ok "Python venv setup completed"
    else
        err "ensure-venv.sh failed. Check the output above for details."
        warn "You can re-run it manually: bash ${ENSURE_VENV}"
    fi
fi

# ---------------------------------------------------------------------------
# Step 9: config.json
# ---------------------------------------------------------------------------
step "Step 9: Application Configuration"

CONFIG_JSON="${SCRIPT_DIR}/config.json"

if [[ -f "$CONFIG_JSON" ]]; then
    ok "config.json already exists at ${CONFIG_JSON}"
else
    echo "  Creating config.json template..."
    cat > "$CONFIG_JSON" <<'EOF'
{
  "server": "ws://YOUR_SERVER_ADDRESS:PORT",

  "monitor": [
    { "system": 1 }
  ],

  "monitorExclude": [],

  "interactive": false,
  "search": false,
  "autoPlay": false,

  "audio": {
    "noAudio": false,
    "player": null,
    "volume": 100
  },

  "avoidMinutes": 15,

  "logLevel": "info",
  "logFilePath": null,

  "plugins": [
    { "path": "./src/plugins/pygame-display.js", "enabled": true }
  ]
}
EOF
    ok "Created config.json template at ${CONFIG_JSON}"
    warn "IMPORTANT: Edit ${CONFIG_JSON} and set your server URL before running."
fi

# ---------------------------------------------------------------------------
# Step 10: Bluetooth Speaker (Optional)
# ---------------------------------------------------------------------------
step "Step 10: Bluetooth Speaker (Optional)"

BT_SCRIPT="${SCRIPT_DIR}/pair-bluetooth-speaker.sh"

if [[ ! -f "$BT_SCRIPT" ]]; then
    warn "pair-bluetooth-speaker.sh not found — skipping Bluetooth setup"
else
    echo "  Would you like to pair a Bluetooth speaker now?"
    echo "  This installs PipeWire (the audio server) and walks you through"
    echo "  pairing and setting a speaker as the default audio output."
    echo "  You can also run this later at any time: ./pair-bluetooth-speaker.sh"
    echo ""
    read -r -p "$(echo -e "${YELLOW}  Set up a Bluetooth speaker? [y/N]:${RESET} ")" BT_CHOICE
    BT_CHOICE="${BT_CHOICE:-n}"

    if [[ "$BT_CHOICE" =~ ^[Yy] ]]; then
        bash "$BT_SCRIPT"
    else
        ok "Skipped — run ./pair-bluetooth-speaker.sh whenever you are ready"
    fi
fi

# ---------------------------------------------------------------------------
# Step 11: Summary
# ---------------------------------------------------------------------------
step "Step 11: Setup Summary"

echo ""
echo -e "${CYAN}  Setup complete for display mode: ${DISPLAY_TYPE}${RESET}"
echo ""

if [[ "$SPI_JUST_ENABLED" == true ]]; then
    echo -e "${YELLOW}  ⚠  REBOOT REQUIRED before the display will work:${RESET}"
    echo "      sudo reboot"
    echo ""
fi

if [[ ${#GROUPS_ADDED[@]} -gt 0 ]]; then
    GROUPS_STR=$(IFS=,; echo "${GROUPS_ADDED[*]}")
    echo -e "${YELLOW}  ⚠  Log out and back in (or run: newgrp gpio) before running,${RESET}"
    echo "     because you were added to group(s): ${GROUPS_STR}"
    echo ""
fi

if [[ -f "${CONFIG_JSON}" ]]; then
    if grep -q "YOUR_SERVER_ADDRESS" "${CONFIG_JSON}" 2>/dev/null; then
        echo -e "${YELLOW}  ⚠  Edit config.json before running:${RESET}"
        echo "      ${CONFIG_JSON}"
        echo ""
    fi
fi

echo "  To run the application:"
echo ""
if [[ "$DISPLAY_TYPE" == "eink" ]]; then
    echo "      ./start-eink.sh ws://<server>:<port>"
else
    echo "      ./start-lcd.sh ws://<server>:<port>"
    echo "      ./start-lcd.sh ws://<server>:<port> --fullscreen"
    echo "      ./start-lcd.sh ws://<server>:<port> --no-touch"
fi
echo ""
echo "  Both launcher scripts source nvm automatically and call"
echo "  pygame-display/ensure-venv.sh on each startup."
echo ""
ok "Done."
