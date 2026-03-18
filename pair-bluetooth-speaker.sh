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
# pipewire-alsa routes ALSA applications (speaker-test, ffplay) through PipeWire.
# libspa-0.2-bluetooth is the PipeWire Bluetooth audio plugin.
AUDIO_PACKAGES=(pipewire pipewire-pulse pipewire-alsa wireplumber libspa-0.2-bluetooth)
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

if command -v wpctl &>/dev/null && wpctl status &>/dev/null; then
    ok "PipeWire is responsive"
else
    warn "wpctl not responding yet — audio may need a moment to start"
    warn "If this fails, try logging out and back in, then re-run this script"
fi

# ---------------------------------------------------------------------------
# Step 4: WirePlumber Bluetooth fix for headless Pi
# ---------------------------------------------------------------------------
step "Step 4: WirePlumber Headless Bluetooth Fix"

# On a headless Pi (no physical display), logind reports the session as
# "online" rather than "active". WirePlumber gates Bluetooth device
# enumeration behind an "active" seat, so A2DP profiles never register
# with BlueZ and connections fail with "br-connection-profile-unavailable".
# Fix: override monitors/bluez.lua in the user's local share directory to
# skip the seat check, so the Bluetooth monitor always starts.

BLUEZ_LUA_OVERRIDE="${HOME}/.local/share/wireplumber/scripts/monitors/bluez.lua"
BLUEZ_LUA_SYSTEM="/usr/share/wireplumber/scripts/monitors/bluez.lua"

if [[ -f "$BLUEZ_LUA_OVERRIDE" ]] && grep -q "config.seat_monitoring = false" "$BLUEZ_LUA_OVERRIDE" 2>/dev/null; then
    ok "WirePlumber headless Bluetooth fix already applied"
elif [[ -f "$BLUEZ_LUA_SYSTEM" ]]; then
    mkdir -p "$(dirname "$BLUEZ_LUA_OVERRIDE")"
    cp "$BLUEZ_LUA_SYSTEM" "$BLUEZ_LUA_OVERRIDE"
    sed -i 's/config\.seat_monitoring = Core\.test_feature.*/config.seat_monitoring = false/' "$BLUEZ_LUA_OVERRIDE"
    ok "WirePlumber headless Bluetooth fix applied"
    # Restart WirePlumber to pick up the new script
    systemctl --user restart wireplumber 2>/dev/null && sleep 2 && ok "WirePlumber restarted" || \
        warn "Could not restart WirePlumber — reboot may be required"
else
    warn "WirePlumber bluez.lua not found at ${BLUEZ_LUA_SYSTEM} — skipping fix"
    warn "Bluetooth may not work on a headless Pi without this fix"
fi

# ---------------------------------------------------------------------------
# Step 5: Enable Bluetooth auto-power on boot
# ---------------------------------------------------------------------------
step "Step 5: Bluetooth Auto-Power"

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
step "Step 6: Scan for Bluetooth Devices"

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
step "Step 7: Select Your Speaker"

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
step "Step 8: Pair, Trust, and Connect"

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
step "Step 9: Default Audio Sink"

# Give the audio subsystem a moment to register the new sink
sleep 3

# WirePlumber usually auto-selects the Bluetooth sink when it connects.
# Verify it appeared and is the default.
BT_SINK_LINE=$(wpctl status 2>/dev/null | grep -E '^\s+\*\s+[0-9]+\.' | head -1)
BT_SINK_ID=$(wpctl status 2>/dev/null | grep -E 'bluez5' | head -1 | awk '{print $1}' | tr -d '.')

if wpctl status 2>/dev/null | grep -q 'bluez5'; then
    ok "Bluetooth audio sink is visible to PipeWire"
    # If it is not already the default, set it
    if ! wpctl status 2>/dev/null | grep -E '^\s+\*' | grep -q 'bluez5\|XinYi'; then
        if [[ -n "$BT_SINK_ID" ]]; then
            wpctl set-default "$BT_SINK_ID" && ok "Set as default sink (id: ${BT_SINK_ID})"
        fi
    else
        ok "Bluetooth speaker is already the default sink"
    fi
else
    warn "Bluetooth audio sink not yet visible to PipeWire."
    echo "  This can happen if the speaker just connected. Try:"
    echo "    wpctl status                    # check audio sinks"
    echo "    wpctl set-default <sink-id>     # set it as default"
fi

# ---------------------------------------------------------------------------
# Step 9: Audio test
# ---------------------------------------------------------------------------
step "Step 10: Audio Test"

echo -e "${YELLOW}  Play a short test tone through the speaker? [Y/n]:${RESET} "
read -r PLAY_TEST
PLAY_TEST="${PLAY_TEST:-y}"

if [[ "$PLAY_TEST" =~ ^[Yy] ]]; then
    echo "  Playing test tone (2 seconds)..."
    TEST_PLAYED=false

    if command -v speaker-test &>/dev/null; then
        timeout 4 speaker-test -c 2 -t wav -l 1 2>/dev/null && TEST_PLAYED=true || true
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
            echo "    wpctl status"
        fi
    else
        warn "speaker-test not found — skipping audio test"
        echo "  Test manually: speaker-test -c 2 -t wav"
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
echo "    wpctl status                          # list audio sinks and devices"
echo "    wpctl set-default <sink-id>           # change default output"
echo "    speaker-test -c 2 -t wav              # play test audio"
echo ""
ok "Done."
