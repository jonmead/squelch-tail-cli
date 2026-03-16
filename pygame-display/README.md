# squelch-tail-display

Pygame display client for [squelch-tail-cli](../squelch-tail-cli). Runs on a
Raspberry Pi as a plugin and shows live-feed call information on either:

- **LCD mode** — 320×480 colour GPIO touchscreen (e.g. 3.5" ILI9486 HAT)
- **E-ink mode** — 250×122 Waveshare 2.13" e-Paper HAT (RPi Zero)

State is received as newline-delimited JSON from the CLI plugin over stdin.
Commands (skip, pause, volume) are sent back over stdout.

---

## Installation

```bash
pip install -r requirements.txt
```

For e-ink mode, also install the Waveshare driver:
```bash
pip install waveshare-epaper
# or from source:
git clone https://github.com/waveshare/e-Paper
pip install ./e-Paper/RaspberryPi_JetsonNano/python/
```

---

## Usage as a CLI plugin

Add the plugin to your squelch-tail-cli config or command line:

```bash
squelch-tail ws://myserver:5000/ws \
  --plugin ~/dev/squelch-tail-display/plugin/pygame-display.js
```

Configure via environment variables before launching:

| Variable                  | Default | Description                          |
|---------------------------|---------|--------------------------------------|
| `SQUELCH_DISPLAY_MODE`    | `lcd`   | `lcd` or `eink`                      |
| `SQUELCH_DISPLAY_WIDTH`   | 320/250 | Display width in pixels              |
| `SQUELCH_DISPLAY_HEIGHT`  | 480/122 | Display height in pixels             |
| `SQUELCH_DISPLAY_PYTHON`  | `python3` | Python binary to use               |
| `SQUELCH_DISPLAY_ROTATE`  | `0`     | Screen rotation (0/90/180/270, LCD)  |
| `SQUELCH_DISPLAY_EXTRA`   | —       | Extra args passed to `main.py`       |

Example for e-ink:
```bash
export SQUELCH_DISPLAY_MODE=eink
squelch-tail ws://myserver:5000/ws --plugin ~/dev/squelch-tail-display/plugin/pygame-display.js
```

---

## LCD mode (320×480)

Raspberry Pi SDL config for GPIO LCD HAT:
```bash
export SDL_VIDEODRIVER=fbcon
export SDL_FBDEV=/dev/fb1
export SDL_MOUSEDRV=TSLIB
export TSLIB_FBDEVICE=/dev/fb1
```

**Touch controls:**
- **⏭ SKIP** — skip current call
- **⏸ PAUSE / ⏵ PLAY** — pause or resume the queue
- **− / +** — adjust PulseAudio system volume in 5% steps

**Keyboard controls (development):**
- `Space` — skip, `p` — pause, `+/-` — volume, `Esc` — quit

---

## E-ink mode (250×122)

The Waveshare 2.13" HAT uses a 250×122 monochrome display. Refresh strategy:

- **Full refresh** (~2 s, flashes): on call change, connect/disconnect, pause toggle
- **Partial refresh** (~0.3 s): elapsed time update every 10 s during playback

**Touch zones** (I²C GT1151 touch controller, handled via evdev):

```
┌──────────┬──────────┬──────────┐
│          │          │          │
│   SKIP   │  VOL −   │  VOL +   │
│  (x<83)  │ (83≤x<166)│ (x≥166) │
└──────────┴──────────┴──────────┘
```

The touch driver reads `/dev/input/eventN` via `evdev`. Wire it up in
`eink_app.py`'s `_on_touch()` method or extend the app with an evdev thread.

Volume is set locally on the Pi via `pactl set-sink-volume @DEFAULT_SINK@ N%`
and also forwarded to the CLI's software volume.

---

## Manual testing (no RPi)

```bash
echo '{"type":"state","connected":true,"lfActive":true,"playing":true,
  "elapsed":5.2,"queueLen":1,"volume":80,"paused":false,
  "call":{"systemId":1,"systemLabel":"Metro Police",
          "talkgroupId":100,"tgLabel":"Fire Dispatch",
          "freq":460012500,"emergency":false,"encrypted":false,
          "units":[{"unitId":1234,"tag":"Engine 5"},{"unitId":5678}]}}' \
| python3 main.py --mode lcd
```
