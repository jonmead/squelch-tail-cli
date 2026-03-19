# Hardware Setup — squelch-tail-cli

## 1. Overview

squelch-tail-cli supports two display modes on Raspberry Pi: **E-ink** and **LCD**. Both use the same Python pygame display process launched by a shell script; the display mode is selected at launch time by choosing either `start-eink.sh` or `start-lcd.sh`. No code changes are required to switch modes.

The application connects to a scanner radio server over WebSocket, plays incoming audio via `ffplay`, and drives the display with call metadata (talkgroup, frequency, timestamp).

---

## 2. Supported Hardware

| Mode   | Hardware                          | Resolution   | Interface       |
|--------|-----------------------------------|--------------|-----------------|
| `eink` | Waveshare 2.13" V4 e-Paper HAT   | 250×122 B&W  | SPI (GPIO HAT)  |
| `lcd`  | 480×320 colour LCD HAT            | 480×320 colour | SPI/GPIO or HDMI |

Tested on: Raspberry Pi Zero 2W, Raspberry Pi OS Trixie 64-bit (Debian 13), kernel 6.12.x rpi-v8.

---

## 3. Guided Setup (Recommended)

The easiest way to set up a Pi from scratch is to run `setup-pi.sh`. It handles all steps below interactively and is safe to re-run.

```bash
git clone <repo-url> ~/squelch-tail-cli
cd ~/squelch-tail-cli
chmod +x setup-pi.sh
./setup-pi.sh
```

> Replace `<repo-url>` with the actual repository URL.

The script will:
- Verify you are running on a Raspberry Pi
- Enable SPI in `/boot/firmware/config.txt` if needed
- Add your user to the `spi`, `i2c`, and `gpio` groups
- Install all required system packages via `apt`
- Install Node.js via nvm
- Clone the Waveshare e-Paper library (E-ink mode only)
- Run `npm install`
- Run `pygame-display/ensure-venv.sh` to set up the Python environment
- Create a `config.json` template if one does not already exist

After running, follow any prompts about rebooting or logging out for group/SPI changes to take effect.

---

## 4. Manual Setup — Common Steps (Both Displays)

### 4.1 Operating System

Install **Raspberry Pi OS 64-bit** (Debian Bookworm or Trixie). This guide was tested on Trixie (Debian 13). Use the 64-bit image for best compatibility with modern Python packages.

### 4.2 Enable SPI

SPI is required for both the E-ink HAT and most GPIO LCD HATs.

**Option A — raspi-config:**
```bash
sudo raspi-config
# Interface Options > SPI > Enable
```

**Option B — manual edit:**

Add the following lines to `/boot/firmware/config.txt`:
```
dtparam=spi=on
dtparam=i2c_arm=on
```

Also configure I2C kernel modules to load at boot (required on Pi OS Trixie):
```bash
sudo bash -c 'echo -e "i2c-dev\ni2c-bcm2835" > /etc/modules-load.d/i2c.conf'
```

Reboot after enabling SPI/I2C:
```bash
sudo reboot
```

Verify SPI and I2C devices are present after reboot:
```bash
ls /dev/spidev0.*
# Should show: /dev/spidev0.0  /dev/spidev0.1

ls /dev/i2c-*
# Should show: /dev/i2c-1
```

### 4.3 User Groups

Your user must be a member of the `spi`, `i2c`, and `gpio` groups:

```bash
sudo usermod -aG spi,i2c,gpio $USER
```

Log out and back in (or start a new session with `newgrp gpio`) for group membership to take effect.

### 4.4 System Packages

Install all required system packages:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg python3-lgpio python3-spidev python3-gpiozero git curl
```

**Why these packages:**

| Package | Reason |
|---------|--------|
| `ffmpeg` / `ffplay` | Plays M4A audio from the scanner server. `aplay` only handles WAV and will silently fail on M4A. |
| `python3-lgpio` | GPIO driver for modern Pi OS (gpiochip interface, replaces legacy sysfs). Cannot be pip-installed — must come from apt. |
| `python3-spidev` | SPI bus access for the display HATs. |
| `python3-gpiozero` | Used by the Waveshare `epdconfig.py` driver. |
| `git` | Required to clone the Waveshare library. |
| `curl` | Required to download the nvm installer. |

### 4.5 Node.js

Install Node.js via nvm (the system Node.js packages are typically too old):

```bash
# Install nvm
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/HEAD/install.sh | bash

# Open a new shell or source nvm in the current one
source ~/.nvm/nvm.sh

# Install the latest LTS release
nvm install --lts

# Verify
node --version
npm --version
```

> Note: nvm installs Node.js into `~/.nvm/` and is not in the system PATH. The launcher scripts (`start-eink.sh`, `start-lcd.sh`) source `~/.nvm/nvm.sh` automatically, so Node is available when the app runs. The systemd service unit example in Section 8 accounts for this.

### 4.6 App Setup

```bash
cd ~/squelch-tail-cli
npm install
```

---

## 5. Manual Setup — E-ink (Waveshare 2.13" V4)

### 5.1 Hardware

The Waveshare 2.13" V4 e-Paper HAT connects directly to the GPIO header of the Raspberry Pi Zero 2W — no individual wiring is needed. It is a HAT (Hardware Attached on Top) that slots directly onto the 40-pin GPIO header.

Confirm that the HAT is firmly seated and that SPI is enabled before running the application.

The relevant GPIO pins used by the HAT are managed by the Waveshare driver; no manual GPIO configuration is required.

### 5.2 Waveshare Library

The pip package `waveshare-epaper` uses a different namespace (`epaper`) from the library expected by this project (`waveshare_epd`). You must use the cloned library:

```bash
git clone https://github.com/waveshare/e-Paper ~/epaper
```

The `ensure-venv.sh` script detects when running on a Pi and installs the library from `~/epaper` into the venv automatically.

### 5.3 Python Environment

The Python environment is managed by `pygame-display/ensure-venv.sh`. It is called automatically every time `start-eink.sh` runs, so no manual setup is needed.

What `ensure-venv.sh` does:
- Creates a venv at `pygame-display/.venv-pygame-display/` with `--system-site-packages` (so `lgpio`, `spidev`, and `gpiozero` from apt are accessible inside the venv)
- Installs `pygame-ce>=2.5.0` and `Pillow>=9.0.0` via pip
- On a Raspberry Pi, installs the Waveshare e-Paper driver from `~/epaper` via pip

> `pygame-ce` (Community Edition) is used instead of `pygame` because pygame 2.6.1 has a broken font module on Python 3.13+. `pygame-ce` is the actively maintained fork.

### 5.4 Running

```bash
./start-eink.sh ws://<server>:<port>
```

### 5.5 Environment Variables

These variables can be set in the shell before launching to override display behaviour:

| Variable | Default | Description |
|----------|---------|-------------|
| `SQUELCH_DISPLAY_MODE` | `eink` | Display mode (`eink` or `lcd`) |
| `SQUELCH_DISPLAY_WIDTH` | `250` | Display width in pixels |
| `SQUELCH_DISPLAY_HEIGHT` | `122` | Display height in pixels |
| `SQUELCH_DISPLAY_ROTATE` | `0` | Rotation in degrees (0, 90, 180, 270) |
| `SQUELCH_DISPLAY_PYTHON` | `python3` | Path to the Python binary to use |
| `SQUELCH_DISPLAY_EXTRA` | _(empty)_ | Extra argument string passed to the display process |
| `SQUELCH_DISPLAY_TEST` | unset | Set to `1` to open a desktop window instead of driving hardware |

### 5.6 Touch Input

The Waveshare 2.13" Touch e-Paper HAT includes a GT1151 capacitive touch controller on I2C address 0x14. Touch is enabled automatically when the GT1151 is detected on I2C bus 1 — no extra configuration is needed beyond enabling I2C (Section 4.2).

**Touch zones (landscape 250×122):**
- Tap the content area (middle of screen) → play/pause toggle
- Tap the bottom bar → open volume menu; then tap left half = vol down, right half = vol up

**Verify the touch controller is detected after boot:**
```bash
sudo i2cdetect -y 1
# Should show "14" at address 0x14
```

#### Physical Buttons (Alternative)

If using the non-touch Waveshare 2.13" V4 HAT (display-only), you can wire momentary push-buttons (active-low, GPIO → GND) to any free BCM GPIO pins and configure them via environment variables:

| Variable | Description |
|----------|-------------|
| `SQUELCH_BTN_PAUSE` | BCM pin → play/pause toggle |
| `SQUELCH_BTN_VOL_UP` | BCM pin → volume up (opens volume menu) |
| `SQUELCH_BTN_VOL_DN` | BCM pin → volume down (opens volume menu) |

Available BCM pins (not used by the e-ink HAT): 5, 6, 13, 19, 26 (and others — avoid 8, 17, 18, 24, 25).

**Example** — three buttons wired to BCM 5, 6, 13:

```bash
SQUELCH_BTN_PAUSE=5 SQUELCH_BTN_VOL_UP=6 SQUELCH_BTN_VOL_DN=13 \
  ./start-eink.sh ws://<server>:<port>
```

Or set them in a wrapper script or the systemd unit's `Environment=` lines.

---

## 6. Manual Setup — LCD (480×320 HAT)

### 6.1 Hardware

A 480×320 colour LCD HAT (e.g. Waveshare 3.5" or a compatible GPIO LCD). The HAT connects to the 40-pin GPIO header.

### 6.2 Display Driver / Overlay

GPIO LCD HATs require a device tree overlay to enable the SPI framebuffer driver. Add the appropriate overlay to `/boot/firmware/config.txt` and reboot.

**ILI9486-based 3.5" HATs** (e.g. lcdwiki, Waveshare 3.5" Rev2.1, and most compatible 480×320 HATs):
```
dtoverlay=piscreen,speed=16000000,rotate=270
```

The `rotate=270` value produces the correct landscape orientation for this HAT. If your image appears rotated, try `rotate=0`, `90`, or `180`.

After adding the overlay and rebooting, verify the framebuffer device exists:
```bash
ls /dev/fb1
# Should show: /dev/fb1
```

Other common overlays:
- `dtoverlay=piscreen2r` — alternative piscreen variant (try if `piscreen` does not work)
- Manufacturer-specific overlays — check the HAT's wiki or GitHub page

**HDMI-connected LCD displays** (those that present as a standard HDMI monitor) do not need a dtoverlay.

### 6.3 SDL Display Driver

The app detects your display hardware automatically and selects the correct rendering path:

| Hardware | `/dev/fb1` present? | Rendering method |
|----------|--------------------|-----------------------------------------|
| GPIO LCD HAT (fbtft) | Yes | Offscreen SDL surface flushed to `/dev/fb1` via mmap |
| HDMI / KMS display | No | `SDL_VIDEODRIVER=kmsdrm` |

> **Why not `SDL_VIDEODRIVER=fbcon`?** SDL2 on modern Raspberry Pi OS (Bookworm/Trixie) is built without fbcon support. The app works around this by rendering to an offscreen surface and writing each frame directly to the framebuffer as RGB565.

No manual `SDL_VIDEODRIVER` configuration is needed. To override, set it in your environment before running `start-lcd.sh`:
```bash
# Force KMS/DRM (e.g. HDMI monitor with no HAT):
SDL_VIDEODRIVER=kmsdrm ./start-lcd.sh ws://...

# Force a different framebuffer device:
SDL_FBDEV=/dev/fb0 ./start-lcd.sh ws://...
```

### 6.4 Touch Input

GPIO LCD HATs typically expose a touch controller via `/dev/input/event*`. No additional configuration is required — the LCD app reads touch input through pygame mouse events, which SDL maps from the touch device automatically.

If touch is not working, verify the touch input device is present:
```bash
ls /dev/input/event*
# Test raw input events:
sudo evtest /dev/input/event0
```

### 6.5 Python Environment

The same `pygame-display/ensure-venv.sh` is used for LCD mode. No Waveshare library is needed. The script is called automatically by `start-lcd.sh` on each run.

### 6.6 Running

```bash
./start-lcd.sh ws://<server>:<port>

# Optional flags passed through to the Python display process:
./start-lcd.sh ws://<server>:<port> --fullscreen
./start-lcd.sh ws://<server>:<port> --no-touch
./start-lcd.sh ws://<server>:<port> --fullscreen --no-touch
```

| Flag | Effect |
|------|--------|
| `--fullscreen` | Run pygame in fullscreen mode (fills the display) |
| `--no-touch` | Disable touch input handling |

### 6.7 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SQUELCH_DISPLAY_MODE` | `lcd` | Display mode (`eink` or `lcd`) |
| `SQUELCH_DISPLAY_WIDTH` | `480` | Display width in pixels |
| `SQUELCH_DISPLAY_HEIGHT` | `320` | Display height in pixels |
| `SQUELCH_DISPLAY_ROTATE` | `0` | Rotation in degrees (0, 90, 180, 270) |
| `SQUELCH_DISPLAY_PYTHON` | `python3` | Path to the Python binary to use |
| `SQUELCH_DISPLAY_EXTRA` | _(empty)_ | Extra argument string passed to the display process |
| `SQUELCH_DISPLAY_TEST` | unset | Set to `1` to open a desktop window instead of driving hardware |
| `SDL_VIDEODRIVER` | auto | Override SDL video driver. Auto-detected: `offscreen` when `/dev/fb1` exists, `kmsdrm` otherwise |
| `SDL_FBDEV` | `/dev/fb1` | Framebuffer device path for GPIO LCD HAT rendering |

---

## 7. Configuration (config.json)

Create `config.json` in the project root (the setup script creates a template automatically). Fill in your scanner server address before running.

```json
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
```

| Field | Description |
|-------|-------------|
| `server` | WebSocket URL of your scanner radio server |
| `monitor` | Array of systems (and optionally talkgroups) to monitor. Omit `talkgroups` to monitor all talkgroups on a system. |
| `monitorExclude` | Array of systems/talkgroups to exclude from monitoring |
| `interactive` | Enable interactive keyboard control |
| `search` | Enable search/scan mode |
| `autoPlay` | Automatically start playback on connect |
| `audio.noAudio` | Set to `true` to disable audio playback entirely |
| `audio.player` | Audio player binary override (`null` = auto-detect). Must support M4A — use `ffplay`. |
| `audio.volume` | Playback volume (0–100) |
| `avoidMinutes` | How long to avoid a talkgroup after manually skipping it |
| `logLevel` | Log verbosity: `error`, `warn`, `info`, `debug` |
| `logFilePath` | Write logs to this file path in addition to stdout (`null` = disabled) |
| `plugins` | List of plugin modules to load. The pygame display plugin is `./src/plugins/pygame-display.js`. |

---

## 8. Autostart with systemd

To have the application start automatically on boot, create a systemd service unit.

**Example unit file — E-ink:**

```ini
[Unit]
Description=squelch-tail-cli E-ink Display
After=network.target
Wants=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/squelch-tail-cli
ExecStart=/bin/bash /home/admin/squelch-tail-cli/start-eink.sh ws://YOUR_SERVER_ADDRESS:PORT
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> The `ExecStart` uses the full path to `bash` because `nvm` is not in the system PATH. The `start-eink.sh` script sources `~/.nvm/nvm.sh` internally, making Node.js available at runtime without needing it in the system PATH.

**Install and enable:**

```bash
# Copy the unit file
sudo cp squelch-tail.service /etc/systemd/system/squelch-tail.service

# Edit the unit file to set your server address
sudo nano /etc/systemd/system/squelch-tail.service

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable squelch-tail.service
sudo systemctl start squelch-tail.service

# Check status
sudo systemctl status squelch-tail.service

# View live logs
journalctl -u squelch-tail.service -f
```

For LCD mode, replace `start-eink.sh` with `start-lcd.sh` (and add any flags you need, e.g. `--fullscreen`) in the `ExecStart` line.

---

## 9. Troubleshooting

### "waveshare_epd not installed — simulation mode"

`~/epaper` has not been cloned, or the venv was not set up correctly. Fix:

```bash
# Re-clone the library if missing
git clone https://github.com/waveshare/e-Paper ~/epaper

# Re-run the venv setup
bash ~/squelch-tail-cli/pygame-display/ensure-venv.sh

# Or simply re-run the full setup script
~/squelch-tail-cli/setup-pi.sh
```

### "GPIO busy" / GPIO error on startup

Another process is already holding the GPIO lines. Kill all related processes and retry:

```bash
pkill -9 -f 'main.py'
pkill -9 -f 'node.*index.js'
```

### Audio plays but the display shows nothing new

Verify that `ffplay` is installed and on the PATH:

```bash
which ffplay
ffplay -version
```

If `ffplay` is missing, install it: `sudo apt-get install -y ffmpeg`. The `aplay` command cannot play M4A files and will fail silently — `ffplay` is required.

### "No module named pygame"

The venv was created without `pygame-ce` (or was created before it was added to the install list). Delete the venv and re-create it:

```bash
rm -rf ~/squelch-tail-cli/pygame-display/.venv-pygame-display
bash ~/squelch-tail-cli/pygame-display/ensure-venv.sh
```

### Display flickers or inverts on every call

This is a known characteristic of e-ink displays — a full refresh (which briefly inverts the display) is triggered whenever a large black fill area changes. The current display design uses a white-background layout to minimise the frequency of full refreshes.

### Node not found when running start-eink.sh or start-lcd.sh

Node.js was installed via nvm and is not in the system PATH. The launcher scripts source `~/.nvm/nvm.sh` automatically. Possible causes:

- nvm was installed under a different user account — confirm you are running as the same user that ran `setup-pi.sh`
- nvm install was interrupted — re-run `setup-pi.sh` or manually re-install nvm

### Screen shows wrong or stale content after reboot

The application is not set to autostart. Follow the systemd instructions in Section 8, or run the launcher script manually after each boot.

### LCD screen is blank / `video system not initialized`

**1. Check that the fbtft overlay is loaded and `/dev/fb1` exists:**
```bash
ls /dev/fb1
dmesg | grep fb_ili9486
```
If `/dev/fb1` is missing, the dtoverlay was not added or the reboot did not complete. Add `dtoverlay=piscreen,speed=16000000,rotate=270` to `/boot/firmware/config.txt` and reboot (see Section 6.2).

**2. Check that the user has access to the framebuffer:**
```bash
groups   # should include 'video'
ls -la /dev/fb1   # should be group 'video', mode crw-rw----
```
If not in the `video` group: `sudo usermod -aG video $USER` then log out and back in.

**3. Verify the venv was rebuilt after adding numpy:**
```bash
/path/to/.venv-pygame-display/bin/python3 -c "import numpy; print('ok')"
```
If that fails: `rm -rf pygame-display/.venv-pygame-display && bash pygame-display/ensure-venv.sh`

### SDL / pygame fails to open the display (LCD mode)

The app auto-detects the rendering method (see Section 6.3). If you need to force a specific driver:
```bash
# GPIO HAT with framebuffer on /dev/fb0 instead of /dev/fb1:
SDL_FBDEV=/dev/fb0 ./start-lcd.sh ws://...

# HDMI display / no HAT:
SDL_VIDEODRIVER=kmsdrm ./start-lcd.sh ws://...
```
