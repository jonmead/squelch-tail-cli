"""
E-ink display mode — 250×122 px Waveshare 2.13" HAT (landscape) on RPi Zero.

Design constraints:
  • Full refresh: ~2 s, causes flash — used only on call change / connect change.
  • Partial refresh: ~0.3 s — used for elapsed-time updates (every 10 s).
  • Black-and-white only (1-bit).
  • No animations; minimal CPU.
  • pygame runs off-screen via SDL_VIDEODRIVER=offscreen; surface converted to
    PIL Image and pushed to the Waveshare driver over SPI.

Layout (landscape 250×122):
  ┌──────────────────────────────────────────────────────┐
  │ ● LIVE  SQUELCH TAIL                          Q:2   │  status  y=0–13
  ├────────────────────────────────╥─────────────────────┤
  │ Metro Police                   ║  ★ EMERGENCY        │
  │ FIRE DISPATCH                  ║  [ENCRYPTED]        │  content y=15–103
  │ Fire Ops · 460.0000 MHz        ║                     │
  │                                ║  Units: 3           │
  │                                ║  1234 Engine 5      │
  │                                ║  5678 Dispatch      │
  ├────────────────────────────────╨─────────────────────┤
  │  12s                   VOL 80%                        │  bottom  y=104–121
  └──────────────────────────────────────────────────────┘

  Left col: x=0–154 (155px)   VSep: x=155   Right col: x=156–249 (94px)

Physical GPIO buttons (gpiozero, active-low, pull-up):
  SQUELCH_BTN_PAUSE   = BCM pin → play/pause toggle
  SQUELCH_BTN_VOL_UP  = BCM pin → volume up (opens vol menu)
  SQUELCH_BTN_VOL_DN  = BCM pin → volume down (opens vol menu)

  Example:  SQUELCH_BTN_PAUSE=5 SQUELCH_BTN_VOL_UP=6 SQUELCH_BTN_VOL_DN=13
"""

import os
import sys
import time

import pygame

from .ipc import IpcReader, send_command
from .state import DisplayState
from .volume import get_pulse_volume, set_pulse_volume

# Palette
WHITE = (255, 255, 255)
BLACK = (0,   0,   0)


_FULL    = 'full'
_PARTIAL = 'partial'

_IDLE_FRAMES   = 3
_IDLE_INTERVAL = 3.0   # seconds between standby animation ticks

# Vertical separator
_VSEP_X = 155


def _trunc(font, text: str, max_w: int) -> str:
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + '…')[0] > max_w:
        text = text[:-1]
    return text + '…'


def _fmt_freq(freq) -> str:
    if freq is None:
        return ''
    return f'{freq / 1_000_000:.4f} MHz'


class EinkApp:
    _W = 250
    _H = 122
    _ELAPSED_INTERVAL = 10   # seconds between partial elapsed updates

    def __init__(self, width=250, height=122, test=False):
        self._W   = 250   # fixed; Waveshare 2.13" is always 250×122
        self._H   = 122
        self.test = test

        self.state    = DisplayState()
        self.ipc      = IpcReader()
        self._volume  = 100
        self._running = True
        self._epd     = None
        self._epd_mod = None

        self._prev_call_tg   = None
        self._prev_connected = None
        self._prev_paused    = None
        self._prev_playing   = None
        self._last_elapsed_t = 0.0

        self._vol_menu_active  = False
        self._vol_menu_t       = 0.0
        self._VOL_MENU_TIMEOUT = 4.0   # seconds before auto-dismiss
        self._prev_vol_menu    = False
        self._prev_volume      = 100

        self._idle_frame   = 0
        self._idle_frame_t = 0.0

        self._partial_count = 0   # tracks partials since last full refresh
        self._gpio_btns     = []  # gpiozero Button objects (for cleanup)
        self._touch_reader  = None

    def run(self) -> None:
        self._init_hardware()
        self._init_pygame()
        self._volume = get_pulse_volume()
        self.ipc.start()

        self._render_and_push(_FULL)

        while self._running:
            msgs = self.ipc.poll()
            for msg in msgs:
                if msg.get('type') == 'quit':
                    self._running = False
                    break
                elif msg.get('type') == 'state':
                    self.state.update(msg)

            needs = self._classify_change()
            if needs:
                self._render_and_push(needs)
                self._snapshot()
            elif (not self._vol_menu_active and
                  self.state.playing and
                  time.monotonic() - self._last_elapsed_t > self._ELAPSED_INTERVAL):
                self._render_and_push(_PARTIAL)
                self._last_elapsed_t = time.monotonic()
            elif (not self._vol_menu_active and
                  not self.state.playing and
                  self.state.call is None and
                  time.monotonic() - self._idle_frame_t > _IDLE_INTERVAL):
                self._idle_frame    = (self._idle_frame + 1) % _IDLE_FRAMES
                self._idle_frame_t  = time.monotonic()
                # Periodic full cleanup when idle: ~60 s (20 ticks × 3 s interval)
                # prevents ghosting accumulation; flash only visible when quiet
                mode = _FULL if self._partial_count >= 20 else _PARTIAL
                self._render_and_push(mode)

            # Auto-dismiss volume menu after timeout
            if (self._vol_menu_active and
                    time.monotonic() - self._vol_menu_t > self._VOL_MENU_TIMEOUT):
                self._vol_menu_active = False
                self._render_and_push(_PARTIAL)
                self._snapshot()

            if self.test:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self._running = False
                    elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        self._running = False
                    elif ev.type == pygame.MOUSEBUTTONDOWN:
                        self._on_touch(*pygame.mouse.get_pos())
            else:
                time.sleep(0.05)

        self._cleanup()

    # ── Hardware ──────────────────────────────────────────────────────────────

    def _init_hardware(self) -> None:
        try:
            from waveshare_epd import epd2in13_V4 as epd_mod
            self._epd_mod = epd_mod
            self._epd = epd_mod.EPD()
            self._epd.init()
            self._epd.Clear(0xFF)
            print('[eink] Waveshare 2.13" V4 initialised', file=sys.stderr)
        except ImportError:
            print('[eink] waveshare_epd not installed — simulation mode', file=sys.stderr)
        except Exception as exc:
            print(f'[eink] Hardware init error: {exc}', file=sys.stderr)

        if not self.test:
            self._init_touch()
            self._init_gpio_buttons()

    def _init_touch(self) -> None:
        """Start GT1151 capacitive touch reader (I2C bus 1)."""
        try:
            from .gt1151 import GT1151Reader
            i2c_bus = int(os.environ.get('SQUELCH_I2C_BUS', '1'))
            reader = GT1151Reader(on_touch=self._on_touch, i2c_bus=i2c_bus)
            if reader.start():
                self._touch_reader = reader
        except Exception as exc:
            print(f'[eink] Touch init error: {exc}', file=sys.stderr)

    def _init_gpio_buttons(self) -> None:
        """Wire physical GPIO buttons via env vars (BCM pin numbers)."""
        try:
            from gpiozero import Button as GPIOButton
        except ImportError:
            print('[eink] gpiozero not available — GPIO buttons disabled', file=sys.stderr)
            return

        btn_map = {
            'SQUELCH_BTN_PAUSE':  lambda: self._on_touch(self._W // 2, self._H // 2),
            'SQUELCH_BTN_VOL_UP': lambda: self._on_gpio_vol(+1),
            'SQUELCH_BTN_VOL_DN': lambda: self._on_gpio_vol(-1),
        }
        for env_var, callback in btn_map.items():
            pin_str = os.environ.get(env_var)
            if not pin_str:
                continue
            try:
                pin = int(pin_str)
                btn = GPIOButton(pin, pull_up=True, bounce_time=0.05)
                btn.when_pressed = callback
                self._gpio_btns.append(btn)
                print(f'[eink] GPIO button on BCM pin {pin} → {env_var}', file=sys.stderr)
            except Exception as exc:
                print(f'[eink] GPIO button setup error ({env_var}={pin_str}): {exc}',
                      file=sys.stderr)

        if not self._gpio_btns:
            print('[eink] No GPIO buttons configured '
                  '(set SQUELCH_BTN_PAUSE / SQUELCH_BTN_VOL_UP / SQUELCH_BTN_VOL_DN)',
                  file=sys.stderr)

    def _init_pygame(self) -> None:
        if not self.test:
            os.environ['SDL_VIDEODRIVER'] = 'offscreen'
        os.environ['SDL_VIDEO_HIGHDPI_DISABLED'] = '1'
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')  # don't claim the audio device
        pygame.init()

        if self.test:
            self._scale  = 1
            self._screen = pygame.display.set_mode((self._W, self._H))
            pygame.display.set_caption(f'Squelch Tail — e-ink ({self._W}×{self._H})')
        else:
            self._scale  = 1
            self._screen = None

        self._surf = pygame.Surface((self._W, self._H))

        _fonts_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'fonts'))

        def _font(filename, size):
            p = os.path.join(_fonts_dir, filename)
            if os.path.exists(p):
                return pygame.font.Font(p, size)
            return pygame.font.SysFont(None, size)

        # Bitter (serif) — content: talkgroup labels, system name, body, units
        self._FT      = lambda size: _font('Bitter-Bold.ttf',    size)   # for _tg_font auto-sizer
        self.f_units  = _font('Bitter-Regular.ttf', 14)
        self.f_sys    = _font('Bitter-Regular.ttf', 14)
        self.f_body   = _font('Bitter-Regular.ttf', 14)
        self.f_badge  = _font('Bitter-Bold.ttf',    12)

        # Fira Sans (sans-serif) — UI chrome: top bar, bottom bar, volume controls
        self._FT_fira = lambda size: _font('FiraSans-Bold.ttf',  size)   # for _ui_font auto-sizer
        self.f_title  = _font('FiraSans-Bold.ttf',       24)
        self.f_italic = _font('FiraSans-BoldItalic.ttf', 17)
        self.f_small  = _font('FiraSans-Bold.ttf',       14)

    # ── Change detection ──────────────────────────────────────────────────────

    def _classify_change(self):
        s       = self.state
        call_tg = s.call.talkgroupId if s.call else None

        # Vol menu toggled → partial (avoid flash on open/close)
        if self._vol_menu_active != self._prev_vol_menu:
            return _PARTIAL

        # While menu is open, only volume changes matter
        if self._vol_menu_active:
            return _PARTIAL if self._volume != self._prev_volume else None

        # All content changes use partial — avoids full-refresh cascade on hardware
        # (a full refresh blocks the loop for ~2 s while state keeps changing)
        if (call_tg     != self._prev_call_tg   or
                s.connected != self._prev_connected or
                s.paused    != self._prev_paused    or
                s.playing   != self._prev_playing):
            return _PARTIAL

        return None

    def _snapshot(self) -> None:
        s = self.state
        self._prev_call_tg   = s.call.talkgroupId if s.call else None
        self._prev_connected = s.connected
        self._prev_paused    = s.paused
        self._prev_playing   = s.playing
        self._prev_vol_menu  = self._vol_menu_active
        self._prev_volume    = self._volume

    # ── Render & push ─────────────────────────────────────────────────────────

    def _render_and_push(self, mode: str) -> None:
        self._render()
        self._last_elapsed_t = time.monotonic()

        if self.test and self._screen:
            scaled = pygame.transform.scale(
                self._surf, (self._W * self._scale, self._H * self._scale))
            self._screen.blit(scaled, (0, 0))
            pygame.display.flip()
            return

        if self._epd is None:
            return

        try:
            from PIL import Image
            raw = pygame.image.tostring(self._surf, 'RGB')
            img = Image.frombytes('RGB', (self._W, self._H), raw).convert('1')
            buf = self._epd.getbuffer(img)
            if mode == _FULL:
                # Full refresh: init_fast + displayPartBaseImage writes to both
                # RAM buffers (0x24 + 0x26) so subsequent partial refreshes diff
                # against the correct base and don't invert.
                self._epd.init_fast()
                self._epd.displayPartBaseImage(buf)
                self._partial_count = 0
            else:
                self._epd.displayPartial(buf)
                self._partial_count += 1
        except Exception as exc:
            print(f'[eink] Push error: {exc}', file=sys.stderr)

    # ── Render ────────────────────────────────────────────────────────────────

    def _render(self) -> None:
        if self._vol_menu_active:
            self._render_vol_menu()
            return

        s  = self.state
        sf = self._surf
        W  = self._W
        H  = self._H

        sf.fill(WHITE)

        # ── Status bar (y=0–19) — white bg, black text, bottom border line ─────
        BAR_H = 20
        cy    = BAR_H // 2

        if s.paused:
            status = 'PAUSED'
        elif s.lfActive:
            status = 'LIVE'
        elif s.connected:
            status = 'CONN'
        else:
            status = 'OFFLINE'

        if not s.paused:
            pygame.draw.circle(sf, BLACK, (7, cy), 4)

        st = self.f_title.render(status, True, BLACK)
        sf.blit(st, (16, cy - st.get_height() // 2))
        title = self.f_small.render('squelch-tail', True, BLACK)
        sf.blit(title, (W // 2 - title.get_width() // 2, cy - title.get_height() // 2))
        if s.queueLen > 0:
            q = self.f_small.render(f'Q:{s.queueLen}', True, BLACK)
            sf.blit(q, (W - q.get_width() - 3, cy - q.get_height() // 2))

        pygame.draw.line(sf, BLACK, (0, BAR_H), (W, BAR_H))

        # ── Content area ──────────────────────────────────────────────────────
        content_top = BAR_H + 2
        units_h     = self.f_units.get_linesize() + 2
        content_bot = H - 18 - units_h   # leave room for units row + bottom bar

        if s.call:
            self._draw_call(sf, s.call, content_top, content_bot)
        else:
            self._draw_idle(sf, s, content_top)

        # ── Units row ─────────────────────────────────────────────────────────
        if s.call and s.call.units:
            units_y = H - 18 - units_h + 1
            parts = []
            seen = set()
            for u in s.call.units:
                if u.unitId == -1 or u.unitId in seen:
                    continue
                seen.add(u.unitId)
                parts.append(u.tag if u.tag else str(u.unitId))
            units_str = _trunc(self.f_units, '  ·  '.join(parts), W - 6)
            sf.blit(self.f_units.render(units_str, True, BLACK), (3, units_y))

        # ── Bottom bar — white bg, black text, top border line ────────────────
        bar_y = H - 17
        pygame.draw.line(sf, BLACK, (0, bar_y - 1), (W, bar_y - 1))

        if s.playing:
            el = self.f_small.render(f'{s.elapsed:.0f}s', True, BLACK)
            sf.blit(el, (3, bar_y))

        vol_s = self.f_small.render(f'VOL {self._volume}%', True, BLACK)
        sf.blit(vol_s, (W // 2 - vol_s.get_width() // 2, bar_y))


    def _render_vol_menu(self) -> None:
        sf = self._surf
        W, H = self._W, self._H

        sf.fill(WHITE)

        # Compact title bar — auto-size "VOLUME" to fill it
        title_h = 20
        f_ttl = self._ui_font('VOLUME', W - 8, title_h - 2)
        t = f_ttl.render('VOLUME', True, BLACK)
        sf.blit(t, (W // 2 - t.get_width() // 2, (title_h - t.get_height()) // 2))
        pygame.draw.line(sf, BLACK, (0, title_h), (W, title_h))

        # Main area fills all remaining height
        avail_h = H - title_h
        mid_y   = title_h + avail_h // 2

        col = W // 3
        pygame.draw.line(sf, BLACK, (col,     title_h), (col,     H))
        pygame.draw.line(sf, BLACK, (2 * col, title_h), (2 * col, H))

        pad = 4

        def _blit_centered(font, text, cx):
            s = font.render(text, True, BLACK)
            sf.blit(s, (cx - s.get_width() // 2, mid_y - s.get_height() // 2))

        _blit_centered(self._ui_font('−',    col - pad, avail_h - pad), '−',    col // 2)
        vol_str = f'{self._volume}%'
        _blit_centered(self._ui_font(vol_str, col - pad, avail_h - pad), vol_str, col + col // 2)
        _blit_centered(self._ui_font('+',    col - pad, avail_h - pad), '+',    2 * col + col // 2)

    def _tg_font(self, text: str, max_w: int, max_h: int):
        """Largest Bitter Bold that fits text within max_w × max_h."""
        return self._auto_size(self._FT, text, max_w, max_h)

    def _ui_font(self, text: str, max_w: int, max_h: int):
        """Largest Fira Sans Bold that fits text within max_w × max_h."""
        return self._auto_size(self._FT_fira, text, max_w, max_h)

    def _auto_size(self, factory, text: str, max_w: int, max_h: int):
        size = 8
        font = factory(size)
        while True:
            next_f = factory(size + 1)
            w, h = next_f.size(text)
            if w > max_w or h > max_h:
                break
            size += 1
            font = next_f
        return font

    def _draw_call(self, sf, call, y_top, y_bot) -> None:
        W      = self._W
        lw     = W - 6
        freq_h = self.f_body.get_linesize()

        # Talkgroup — auto-sized to fill space above the info line
        tg_max_h = y_bot - y_top - freq_h - 2
        tg_str   = (call.tgLabel or str(call.talkgroupId))[:12]
        f_tg     = self._tg_font(tg_str, lw, tg_max_h)
        sf.blit(f_tg.render(tg_str, True, BLACK), (3, y_top))

        # Info line: "System Name · 460.0000 MHz"
        sys_label = call.systemLabel or f'Sys {call.systemId}'
        parts = [p for p in [sys_label, _fmt_freq(call.freq)] if p]
        if parts:
            row = _trunc(self.f_body, '  ·  '.join(parts), lw)
            sf.blit(self.f_body.render(row, True, BLACK), (3, y_bot - freq_h))

    def _draw_idle(self, sf, s, y_top) -> None:
        import datetime
        import math
        W       = self._W
        mid_top = y_top
        mid_h   = self._H - 18 - y_top   # to bottom bar

        # ── Left 2/3: time, horizontally centred + bottom aligned ────────────
        split_x  = W * 2 // 3
        mid_bot  = mid_top + mid_h
        now_str  = datetime.datetime.now().strftime('%H:%M')
        f_time   = self._tg_font(now_str, split_x - 4, mid_h - 2)
        t        = f_time.render(now_str, True, BLACK)
        sf.blit(t, (split_x // 2 - t.get_width() // 2,
                    mid_bot - t.get_height()))

        # ── Right: broadcast tower ────────────────────────────────────────────
        right_w  = W - split_x
        twr_cx   = split_x + right_w // 2

        # Wave parameters
        arc_half = math.pi / 3          # ±60° from horizontal → 120° arc
        r1, r2, r3 = 8, 14, 20         # inner, mid, outer radii

        # Tower dimensions
        ball_r    = 3
        body_h    = 38
        base_half = 16
        foot_h    = 4

        # Vertical centering — full icon spans: wave_above + ball + body + feet
        wave_above = int(r3 * math.sin(arc_half)) + 1
        total_h    = wave_above + 2 * ball_r + body_h + foot_h
        y_off      = mid_top + max(0, (mid_h - total_h) // 2)

        ball_cy = y_off + wave_above + ball_r
        twr_top = ball_cy + ball_r          # apex (bottom of ball)
        base_y  = twr_top + body_h

        # Four levels: (y, outer half-width) at 0%, 40%, 80%, 100% of body_h
        lv = [
            (twr_top,                    0),
            (twr_top + body_h * 2 // 5,  base_half * 2 // 5),
            (twr_top + body_h * 4 // 5,  base_half * 4 // 5),
            (base_y,                     base_half),
        ]

        W2 = 2   # uniform stroke width for every element

        # Outer legs (apex → base corners)
        pygame.draw.line(sf, BLACK, (twr_cx, lv[0][0]), (twr_cx - lv[3][1], lv[3][0]), W2)
        pygame.draw.line(sf, BLACK, (twr_cx, lv[0][0]), (twr_cx + lv[3][1], lv[3][0]), W2)
        # Horizontal crossbars
        pygame.draw.line(sf, BLACK, (twr_cx - lv[1][1], lv[1][0]), (twr_cx + lv[1][1], lv[1][0]), W2)
        pygame.draw.line(sf, BLACK, (twr_cx - lv[2][1], lv[2][0]), (twr_cx + lv[2][1], lv[2][0]), W2)
        # X-braces (interior diagonals in middle and lower sections)
        pygame.draw.line(sf, BLACK, (twr_cx - lv[1][1], lv[1][0]), (twr_cx + lv[2][1], lv[2][0]), W2)
        pygame.draw.line(sf, BLACK, (twr_cx + lv[1][1], lv[1][0]), (twr_cx - lv[2][1], lv[2][0]), W2)
        pygame.draw.line(sf, BLACK, (twr_cx - lv[2][1], lv[2][0]), (twr_cx + lv[3][1], lv[3][0]), W2)
        pygame.draw.line(sf, BLACK, (twr_cx + lv[2][1], lv[2][0]), (twr_cx - lv[3][1], lv[3][0]), W2)
        # Ground bar + feet
        pygame.draw.line(sf, BLACK, (twr_cx - base_half - 4, base_y), (twr_cx + base_half + 4, base_y), W2)
        pygame.draw.rect(sf, BLACK, pygame.Rect(twr_cx - base_half - 3, base_y + 1, 7, foot_h))
        pygame.draw.rect(sf, BLACK, pygame.Rect(twr_cx + base_half - 3, base_y + 1, 7, foot_h))
        # Ball at tip
        pygame.draw.circle(sf, BLACK, (twr_cx, ball_cy), ball_r)

        # ── Animated waves: frame 0=none, 1=inner 2, 2=all 3 ─────────────────
        # pygame.draw.arc has pixel gaps at small radii; plot pixels manually instead.
        def _arc(r, a0, a1):
            steps = max(int(r * abs(a1 - a0)) * 2 + 4, 16)
            for i in range(steps + 1):
                a  = a0 + (a1 - a0) * i / steps
                ca, sa = math.cos(a), math.sin(a)
                sf.set_at((round(twr_cx + r       * ca), round(ball_cy - r       * sa)), BLACK)
                sf.set_at((round(twr_cx + (r - 1) * ca), round(ball_cy - (r - 1) * sa)), BLACK)

        n_active = (0, 2, 3)[self._idle_frame % 3]
        for i in range(n_active):
            r = (r1, r2, r3)[i]
            _arc(r, -arc_half, arc_half)
            _arc(r, math.pi - arc_half, math.pi + arc_half)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        if self._touch_reader:
            self._touch_reader.stop()
        for btn in self._gpio_btns:
            try:
                btn.close()
            except Exception:
                pass
        if self._epd:
            try:
                self._epd.init()
                self._epd.Clear(0xFF)
                self._epd.sleep()
            except Exception:
                pass
        pygame.quit()

    # ── Touch (external evdev — call _on_touch from your evdev thread) ────────

    def _on_touch(self, x: int, y: int) -> None:
        if self._vol_menu_active:
            if x < self._W // 2:
                self._vol_dn()
            else:
                self._vol_up()
            self._vol_menu_t = time.monotonic()
            return

        # Middle content area → play/pause toggle
        if 15 < y < self._H - 17:
            send_command({'type': 'pause'})
            return

        # Bottom bar tap → open volume menu
        if y >= self._H - 17:
            self._vol_menu_active = True
            self._vol_menu_t = time.monotonic()

    def _on_gpio_vol(self, direction: int) -> None:
        """Called from gpiozero callback thread for vol up/down buttons."""
        if not self._vol_menu_active:
            self._vol_menu_active = True
        self._vol_menu_t = time.monotonic()
        if direction > 0:
            self._vol_up()
        else:
            self._vol_dn()

    def _vol_up(self) -> None:
        self._volume = min(100, self._volume + 10)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': self._volume})

    def _vol_dn(self) -> None:
        self._volume = max(0, self._volume - 10)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': self._volume})
