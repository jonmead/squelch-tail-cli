#!/usr/bin/env bash
# pair-bluetooth-speaker.sh — Pair and configure a Bluetooth speaker on Raspberry Pi
#
# Usage: ./pair-bluetooth-speaker.sh
#
# Run this on the Pi. It is safe to re-run to pair a different speaker.
# Installs required audio stack packages if not already present.

set -e

# ---------------------------------------------------------------------------
# Colors / helpers
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
# Banner
# ---------------------------------------------------------------------------
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║       squelch-tail-cli — Bluetooth Speaker Setup     ║"
echo "║                                                      ║"
echo "║  Pairs a Bluetooth speaker and sets it as the       ║"
echo "║  default audio output for squelch-tail-cli.         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ---------------------------------------------------------------------------
# Step 1: Check for Bluetooth hardware
# ---------------------------------------------------------------------------
step "Step 1: Bluetooth Hardware"

if ! hciconfig hci0 &>/dev/null; then
    err "No Bluetooth adapter found (hci0). Ensure Bluetooth is not disabled."
    echo "  On Raspberry Pi, Bluetooth should be built-in. Check:"
    echo "    - /boot/firmware/config.txt does not have 'dtoverlay=disable-bt'"
    echo "    - The Pi has not been disabled via raspi-config"
    exit 1
fi

BT_ADDR=$(hciconfig hci0 2>/dev/null | grep "BD Address" | awk '{print $3}')
ok "Bluetooth adapter hci0 found  (${BT_ADDR})"

# ---------------------------------------------------------------------------
# Step 2: Install audio stack
# ---------------------------------------------------------------------------
step "Step 2: Audio Stack (PipeWire)"

# PipeWire is the modern audio server on RPi OS Trixie.
# pipewire-pulse provides the PulseAudio-compatible pactl/paplay interface.
# libspa-0.2-bluetooth is the PipeWire Bluetooth audio plugin.
AUDIO_PACKAGES=(pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth)
NEED_INSTALL=()

for pkg in "${AUDIO_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        NEED_INSTALL+=("$pkg")
    fi
done

if [[ ${#NEED_INSTALL[@]} -eq 0 ]]; then
    ok "Audio stack already installed"
else
    echo "  Installing: ${NEED_INSTALL[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${NEED_INSTALL[@]}"
    ok "Audio stack installed"
fi

# ---------------------------------------------------------------------------
# Step 3: Start PipeWire user services
# ---------------------------------------------------------------------------
step "Step 3: PipeWire Services"

PIPEWIRE_SERVICES=(pipewire pipewire-pulse wireplumber)

for svc in "${PIPEWIRE_SERVICES[@]}"; do
    if systemctl --user is-active --quiet "$svc" 2>/dev/null; then
        ok "${svc} already running"
    else
        echo "  Starting ${svc}..."
        systemctl --user enable --now "$svc" 2>/dev/null || \
            warn "Could not enable ${svc} — may already be managed by socket activation"
    fi
done

# Give PipeWire a moment to settle
sleep 2

if command -v pactl &>/dev/null && pactl info &>/dev/null; then
    ok "PipeWire/PulseAudio interface is responsive"
else
    warn "pactl not responding yet — audio may need a moment to start"
    warn "If this fails, try logging out and back in, then re-run this script"
fi

# ---------------------------------------------------------------------------
# Step 4: Enable Bluetooth auto-power on boot
# ---------------------------------------------------------------------------
step "Step 4: Bluetooth Auto-Power"

BT_CONF="/etc/bluetooth/main.conf"

if grep -q "^AutoEnable=true" "$BT_CONF" 2>/dev/null; then
    ok "AutoEnable already set in ${BT_CONF}"
else
    echo "  Enabling AutoEnable in ${BT_CONF}..."
    if grep -q "^\[Policy\]" "$BT_CONF" 2>/dev/null; then
        # Insert AutoEnable after the [Policy] section header
        sudo sed -i '/^\[Policy\]/a AutoEnable=true' "$BT_CONF"
    else
        # Append a new [Policy] section
        echo -e '\n[Policy]\nAutoEnable=true' | sudo tee -a "$BT_CONF" >/dev/null
    fi
    ok "AutoEnable=true written to ${BT_CONF}"
fi

# Power on the adapter now
bluetoothctl power on >/dev/null 2>&1 && ok "Bluetooth adapter powered on" || \
    warn "Could not power on adapter — it may already be on"

# ---------------------------------------------------------------------------
# Step 5: Scan for devices
# ---------------------------------------------------------------------------
step "Step 5: Scan for Bluetooth Devices"

echo "  Make sure your speaker is in pairing mode, then press Enter to start scanning..."
read -r -p ""

echo "  Scanning for 20 seconds — turn on your speaker now..."
echo ""

# Run a single bluetoothctl session: power on, scan for 20 s, then stop
(
    echo "agent NoInputNoOutput"
    echo "default-agent"
    echo "scan on"
    sleep 20
    echo "scan off"
    echo "quit"
) | bluetoothctl 2>/dev/null | grep --line-buffered "NEW\|Device" | \
    sed 's/^.*NEW.*Device/  Found:/' | \
    sed 's/^.*Device \([A-F0-9:]*\) /  Found: \1  /' || true

echo ""

# Collect discovered devices into an array
mapfile -t DEVICES < <(bluetoothctl devices 2>/dev/null | grep "^Device " | sed 's/^Device //')
# Each entry format: "AA:BB:CC:DD:EE:FF  Device Name"

if [[ ${#DEVICES[@]} -eq 0 ]]; then
    err "No Bluetooth devices found."
    echo "  Make sure your speaker is in pairing mode and try again."
    exit 1
fi

echo "  Discovered devices:"
echo ""
for i in "${!DEVICES[@]}"; do
    MAC=$(echo "${DEVICES[$i]}" | awk '{print $1}')
    NAME=$(echo "${DEVICES[$i]}" | cut -d' ' -f2-)
    printf "    ${CYAN}%2d${RESET}. %s  —  %s\n" "$((i+1))" "$MAC" "$NAME"
done
echo ""

# ---------------------------------------------------------------------------
# Step 6: Select device
# ---------------------------------------------------------------------------
step "Step 6: Select Your Speaker"

SELECTED_MAC=""
SELECTED_NAME=""

while true; do
    read -r -p "$(echo -e "${YELLOW}  Enter number (or type a MAC address directly):${RESET} ")" CHOICE

    # Check if it looks like a MAC address
    if [[ "$CHOICE" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
        SELECTED_MAC="$CHOICE"
        SELECTED_NAME="$CHOICE"
        ok "Using MAC: ${SELECTED_MAC}"
        break
    fi

    # Check if it is a valid list number
    if [[ "$CHOICE" =~ ^[0-9]+$ ]] && \
       [[ "$CHOICE" -ge 1 ]] && \
       [[ "$CHOICE" -le "${#DEVICES[@]}" ]]; then
        SELECTED_MAC=$(echo "${DEVICES[$((CHOICE-1))]}" | awk '{print $1}')
        SELECTED_NAME=$(echo "${DEVICES[$((CHOICE-1))]}" | cut -d' ' -f2-)
        ok "Selected: ${SELECTED_NAME}  (${SELECTED_MAC})"
        break
    fi

    warn "Invalid selection. Enter a number from the list or a full MAC address."
done

# ---------------------------------------------------------------------------
# Step 7: Pair, trust, connect
# ---------------------------------------------------------------------------
step "Step 7: Pair, Trust, and Connect"

echo "  Pairing with ${SELECTED_NAME}..."
if bluetoothctl pair "$SELECTED_MAC" 2>&1 | grep -qi "successful\|already\|yes"; then
    ok "Paired"
elif bluetoothctl info "$SELECTED_MAC" 2>/dev/null | grep -q "Paired: yes"; then
    ok "Already paired"
else
    # Some speakers pair without an explicit confirmation — check status
    if bluetoothctl info "$SELECTED_MAC" 2>/dev/null | grep -q "Paired: yes"; then
        ok "Paired"
    else
        warn "Pairing result unclear — continuing (the device may have auto-paired)"
    fi
fi

echo "  Trusting ${SELECTED_NAME} (enables auto-connect)..."
bluetoothctl trust "$SELECTED_MAC" >/dev/null 2>&1 && ok "Trusted" || warn "Trust command returned non-zero (may already be trusted)"

echo "  Connecting to ${SELECTED_NAME}..."
# Retry connect up to 3 times — speakers sometimes need a moment
CONNECTED=false
for attempt in 1 2 3; do
    if bluetoothctl connect "$SELECTED_MAC" 2>&1 | grep -qi "successful\|already connected"; then
        ok "Connected"
        CONNECTED=true
        break
    fi
    [[ $attempt -lt 3 ]] && echo "  Retrying (attempt $((attempt+1)))..." && sleep 3
done

if [[ "$CONNECTED" == false ]]; then
    warn "Could not confirm connection — the speaker may still have connected."
    warn "Check with: bluetoothctl info ${SELECTED_MAC}"
fi

# ---------------------------------------------------------------------------
# Step 8: Set as default audio sink
# ---------------------------------------------------------------------------
step "Step 8: Default Audio Sink"

# Give the audio subsystem a moment to register the new sink
sleep 3

BT_SINK=$(pactl list sinks short 2>/dev/null | grep -i "bluez\|blue" | awk '{print $2}' | head -1)

if [[ -n "$BT_SINK" ]]; then
    pactl set-default-sink "$BT_SINK"
    ok "Default audio sink set to: ${BT_SINK}"
else
    warn "Bluetooth audio sink not yet visible to PipeWire."
    echo "  This can happen if the speaker just connected. Try:"
    echo "    pactl list sinks short          # find the bluez sink name"
    echo "    pactl set-default-sink <name>   # set it as default"
fi

# ---------------------------------------------------------------------------
# Step 9: Audio test
# ---------------------------------------------------------------------------
step "Step 9: Audio Test"

echo -e "${YELLOW}  Play a short test tone through the speaker? [Y/n]:${RESET} "
read -r PLAY_TEST
PLAY_TEST="${PLAY_TEST:-y}"

if [[ "$PLAY_TEST" =~ ^[Yy] ]]; then
    echo "  Playing test tone..."
    TEST_PLAYED=false

    # Try paplay with a system sound first
    if command -v paplay &>/dev/null; then
        SOUND_FILE=""
        for f in /usr/share/sounds/alsa/Front_Left.wav \
                 /usr/share/sounds/freedesktop/stereo/audio-test-signal.oga \
                 /usr/share/sounds/freedesktop/stereo/bell.oga; do
            [[ -f "$f" ]] && SOUND_FILE="$f" && break
        done

        if [[ -n "$SOUND_FILE" ]]; then
            paplay "$SOUND_FILE" 2>/dev/null && TEST_PLAYED=true
        fi
    fi

    # Fall back to speaker-test
    if [[ "$TEST_PLAYED" == false ]] && command -v speaker-test &>/dev/null; then
        timeout 3 speaker-test -t sine -f 880 -l 1 2>/dev/null && TEST_PLAYED=true || true
    fi

    if [[ "$TEST_PLAYED" == true ]]; then
        echo ""
        echo -e "${YELLOW}  Did you hear the test sound? [Y/n]:${RESET} "
        read -r HEARD
        HEARD="${HEARD:-y}"
        if [[ "$HEARD" =~ ^[Yy] ]]; then
            ok "Audio confirmed working through Bluetooth speaker"
        else
            warn "Audio not heard. Check speaker volume and connection."
            echo "  Diagnostics:"
            echo "    bluetoothctl info ${SELECTED_MAC}"
            echo "    pactl list sinks short"
        fi
    else
        warn "No test sound file found — skipping audio playback test"
        echo "  Test manually: paplay /path/to/file.wav"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
step "Setup Complete"

echo ""
echo -e "  Speaker: ${CYAN}${SELECTED_NAME}${RESET}"
echo -e "  MAC:     ${CYAN}${SELECTED_MAC}${RESET}"
echo ""
echo "  The speaker has been paired and trusted. It will reconnect automatically"
echo "  whenever it is powered on and in range."
echo ""
echo "  To re-run this script to pair a different speaker:"
echo "    $(dirname "$0")/pair-bluetooth-speaker.sh"
echo ""
echo "  Useful commands:"
echo "    bluetoothctl info ${SELECTED_MAC}     # check connection status"
echo "    bluetoothctl connect ${SELECTED_MAC}  # reconnect manually"
echo "    pactl list sinks short                # list audio sinks"
echo "    pactl set-default-sink <sink-name>    # change default output"
echo ""
ok "Done."
