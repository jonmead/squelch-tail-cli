"""
LCD display mode — 480×320 colour touchscreen (Raspberry Pi GPIO LCD HAT).

Layout (landscape 480×320):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ ● LIVE   SQUELCH TAIL                Metro Police          Q:2  HTG    │  header 40px
  ├─────────────────────────────────────╥────────────────────────────────────┤
  │ FIRE DISPATCH                       ║  UNITS (5)                        │
  │ Fire Operations Center              ║    ★ 1234  Engine 5               │  content
  │ Fire · EMS                          ║      5678  Dispatch                │  220px
  │ 460.0000 MHz  ·  12:34:56           ║      9012  Unit 3                 │
  │ ★ EMERGENCY   🔒 ENCRYPTED         ║      5432  …                      │
  ├─────────────────────────────────────╫────────────────────────────────────┤
  │ ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░  7.3s           ║  [⏭ SKIP] [⏸ PAUSE] [−] 80% [+] │  bottom 60px
  └─────────────────────────────────────╨────────────────────────────────────┘

  Left column: 0–269 px   Vertical separator: x=270   Right column: 271–479 px
"""

import datetime
import os
import sys

import pygame

from .ipc import IpcReader, send_command
from .state import DisplayState
from .volume import get_pulse_volume, set_pulse_volume

# ── Colour palette (dark scanner theme) ──────────────────────────────────────
C_BG     = (13,  17,  23)
C_PANEL  = (22,  27,  34)
C_BORDER = (48,  54,  61)
C_TEXT   = (230, 237, 243)
C_DIM    = (110, 118, 129)
C_GREEN  = (63,  185,  80)
C_RED    = (248,  81,  73)
C_ORANGE = (240, 136,  62)
C_BLUE   = (31,  111, 235)
C_CYAN   = (121, 192, 255)
C_YELLOW = (210, 153,  34)
C_PURPLE = (210, 168, 255)
C_BTN    = (36,   41,  47)
C_BTN_P  = (56,  139, 253)   # pressed

M      = 8    # outer margin
VSEP_X = 270  # x of the vertical separator


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


class Button:
    def __init__(self, rect, label: str, fg=None):
        self.rect    = pygame.Rect(rect)
        self.label   = label
        self.fg      = fg or C_TEXT
        self.pressed = False

    def draw(self, surf, font) -> None:
        bg = C_BTN_P if self.pressed else C_BTN
        pygame.draw.rect(surf, bg,       self.rect, border_radius=6)
        pygame.draw.rect(surf, C_BORDER, self.rect, 1, border_radius=6)
        txt = font.render(self.label, True, self.fg)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos)


class LcdApp:
    _HEAD_H   = 40   # header height
    _BOTTOM_H = 60   # bottom bar height (progress + controls)

    def __init__(self, width=480, height=320, rotate=0, fullscreen=False, touch=True, test=False):
        self.W          = width
        self.H          = height
        self.rotate     = rotate
        self.fullscreen = fullscreen
        self.touch      = touch
        self.test       = test

        self.state      = DisplayState()
        self.ipc        = IpcReader()
        self._volume    = 100
        self._running   = True
        self._dirty     = True
        self._held_btn  = None

    def run(self) -> None:
        if not self.test:
            # SDL hints for Pi GPIO displays — skipped in test mode
            os.environ.setdefault('SDL_FBDEV',      '/dev/fb1')
            os.environ.setdefault('SDL_VIDEODRIVER', 'fbcon')
            os.environ.setdefault('SDL_MOUSEDRV',    'TSLIB')
            os.environ.setdefault('TSLIB_FBDEVICE',  '/dev/fb1')

        os.environ['SDL_VIDEO_HIGHDPI_DISABLED'] = '1'
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')  # don't claim the audio device
        pygame.init()
        pygame.mouse.set_visible(self.test)

        flags = 0
        if not self.test:
            flags |= pygame.NOFRAME
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((self.W, self.H), flags)
        pygame.display.set_caption('Squelch Tail')

        self._init_fonts()
        self._init_buttons()
        self._volume = get_pulse_volume()

        self.ipc.start()
        clock = pygame.time.Clock()

        while self._running:
            self._handle_events()
            self._handle_ipc()

            if self._dirty:
                self._render()
                pygame.display.flip()
                self._dirty = False

            clock.tick(30)
            if self.state.playing:
                self._dirty = True   # animate elapsed bar

        pygame.quit()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_fonts(self):
        for name in ('DejaVu Sans', 'Liberation Sans', 'FreeSans', 'Ubuntu', None):
            try:
                pygame.font.SysFont(name, 12)
                self._font_name = name
                break
            except Exception:
                pass

        def F(size, bold=False):
            try:
                return pygame.font.SysFont(self._font_name, size, bold=bold)
            except Exception:
                return pygame.font.Font(None, size)

        self.f_head  = F(16, bold=True)
        self.f_sys   = F(17)
        self.f_tg    = F(28, bold=True)
        self.f_body  = F(16)
        self.f_small = F(14)
        self.f_badge = F(13, bold=True)
        self.f_btn   = F(14, bold=True)
        self.f_vol   = F(16, bold=True)

    def _init_buttons(self):
        W, H = self.W, self.H

        # Bottom-right quadrant: controls (right of VSEP_X, bottom _BOTTOM_H rows)
        btn_y  = H - self._BOTTOM_H + 9
        btn_h  = self._BOTTOM_H - 18
        x      = VSEP_X + M

        self.btn_skip    = Button((x, btn_y, 50, btn_h), '⏭ SKIP')
        x += 50 + 4
        self.btn_pause   = Button((x, btn_y, 58, btn_h), '⏸ PAUSE')
        x += 58 + 8

        self.btn_vol_dn  = Button((x, btn_y, 28, btn_h), '−', fg=C_CYAN)
        x += 28 + 2
        self._vol_rect   = pygame.Rect(x, btn_y, 38, btn_h)
        x += 38 + 2
        self.btn_vol_up  = Button((x, btn_y, 28, btn_h), '+', fg=C_CYAN)

        self._buttons = [self.btn_skip, self.btn_pause, self.btn_vol_dn, self.btn_vol_up]

    # ── Event handling ────────────────────────────────────────────────────────

    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self._running = False

            elif ev.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                self._on_down(self._ev_pos(ev))

            elif ev.type in (pygame.MOUSEBUTTONUP, pygame.FINGERUP):
                self._on_up(self._ev_pos(ev))

            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_ESCAPE:                          self._running = False
                elif k == pygame.K_SPACE:                         self._do_skip()
                elif k == pygame.K_p:                             self._do_pause()
                elif k in (pygame.K_EQUALS, pygame.K_PLUS):      self._vol_up()
                elif k == pygame.K_MINUS:                         self._vol_dn()

    def _ev_pos(self, ev):
        if ev.type in (pygame.FINGERDOWN, pygame.FINGERUP):
            return (int(ev.x * self.W), int(ev.y * self.H))
        return pygame.mouse.get_pos()

    def _on_down(self, pos):
        for btn in self._buttons:
            if btn.hit(pos):
                btn.pressed    = True
                self._held_btn = btn
                self._dirty    = True
                return

    def _on_up(self, pos):
        btn = self._held_btn
        self._held_btn = None
        if btn:
            btn.pressed = False
            self._dirty = True
            if btn.hit(pos):
                if   btn is self.btn_skip:   self._do_skip()
                elif btn is self.btn_pause:  self._do_pause()
                elif btn is self.btn_vol_dn: self._vol_dn()
                elif btn is self.btn_vol_up: self._vol_up()

    def _handle_ipc(self):
        for msg in self.ipc.poll():
            if msg.get('type') == 'quit':
                self._running = False
            elif msg.get('type') == 'state':
                self.state.update(msg)
                self._dirty = True

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_skip(self):  send_command({'type': 'skip'})
    def _do_pause(self): send_command({'type': 'pause'})

    def _vol_up(self):
        self._volume = min(150, self._volume + 5)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': min(100, self._volume)})
        self._dirty = True

    def _vol_dn(self):
        self._volume = max(0, self._volume - 5)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': min(100, self._volume)})
        self._dirty = True

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        s    = self.state
        surf = self.screen
        W, H = self.W, self.H

        surf.fill(C_BG)

        self._draw_header(surf, s)
        self._vline(surf, VSEP_X, self._HEAD_H, H)

        content_top    = self._HEAD_H + 4
        content_bottom = H - self._BOTTOM_H - 1

        if s.call:
            self._draw_call_left(surf, s, content_top, content_bottom)
            self._draw_units_right(surf, s, content_top, content_bottom)
        else:
            self._draw_idle(surf, s, content_top)

        self._hline(surf, H - self._BOTTOM_H, W)
        self._draw_bottom(surf, s)

    # ── Header ────────────────────────────────────────────────────────────────

    def _draw_header(self, surf, s):
        W = self.W
        pygame.draw.rect(surf, C_PANEL, (0, 0, W, self._HEAD_H))
        self._hline(surf, self._HEAD_H, W)

        cy = self._HEAD_H // 2

        # Title (left)
        title = self.f_head.render('SQUELCH TAIL', True, C_YELLOW)
        surf.blit(title, (M, cy - title.get_height() // 2))

        # Status dot + label (left-centre)
        if s.paused:
            dot_c, label = C_YELLOW, 'PAUSED'
        elif s.lfActive:
            dot_c, label = C_GREEN,  'LIVE'
        elif s.connected:
            dot_c, label = C_ORANGE, 'CONNECTED'
        else:
            dot_c, label = C_DIM,    'OFFLINE'

        st_x = M + title.get_width() + 20
        pygame.draw.circle(surf, dot_c, (st_x, cy), 4)
        st = self.f_head.render(label, True, dot_c)
        surf.blit(st, (st_x + 8, cy - st.get_height() // 2))

        # System name (centre, if call active)
        if s.call:
            sys_str = _trunc(self.f_head,
                              s.call.systemLabel or f'System {s.call.systemId}',
                              VSEP_X - st_x - st.get_width() - 24)
            sys_s = self.f_head.render(sys_str, True, C_DIM)
            sys_x = st_x + st.get_width() + 16
            surf.blit(sys_s, (sys_x, cy - sys_s.get_height() // 2))

        # Right: queue / hold / avoid badges
        parts = []
        if s.queueLen  > 0:           parts.append(f'Q:{s.queueLen}')
        if s.avoidCount > 0:          parts.append(f'A:{s.avoidCount}')
        if s.holdSys is not None:     parts.append('HSY')
        if s.holdTg  is not None:     parts.append('HTG')
        if parts:
            info = self.f_small.render('  '.join(parts), True, C_DIM)
            surf.blit(info, (W - M - info.get_width(), cy - info.get_height() // 2))

    # ── Left column: call metadata ────────────────────────────────────────────

    def _draw_call_left(self, surf, s, y_top, y_bottom):
        call = s.call
        col_w = VSEP_X - M * 2   # usable width in left column
        y = y_top

        def row(font, text, color=C_TEXT, gap=3):
            nonlocal y
            txt = _trunc(font, text, col_w)
            r   = font.render(txt, True, color)
            surf.blit(r, (M, y))
            y  += r.get_height() + gap

        # Talkgroup label (hero)
        tg_str = call.tgLabel or str(call.talkgroupId)
        row(self.f_tg, tg_str, C_TEXT, gap=2)

        # TG full name
        if call.tgName and call.tgName != call.tgLabel:
            row(self.f_body, call.tgName, C_DIM, gap=2)

        # Group · Tag
        grp_parts = [p for p in [call.tgGroup, call.tgGroupTag] if p]
        if grp_parts:
            row(self.f_body, ' · '.join(grp_parts), C_CYAN, gap=2)

        # Freq + time
        freq_str = _fmt_freq(call.freq)
        time_str = ''
        if call.startTime:
            try:
                dt = datetime.datetime.fromisoformat(call.startTime.replace('Z', '+00:00')).astimezone()
            except (ValueError, AttributeError):
                dt = datetime.datetime.fromtimestamp(float(call.startTime) / 1000)
            time_str = dt.strftime('%H:%M:%S')
        line = '  ·  '.join(p for p in [freq_str, time_str] if p)
        if line:
            row(self.f_body, line, C_CYAN, gap=4)

        # Badges
        bx, badge_h = M, 0
        if call.emergency:
            b = self._make_badge('★ EMERGENCY', C_RED, C_TEXT)
            surf.blit(b, (bx, y)); bx += b.get_width() + 6; badge_h = b.get_height()
        if call.encrypted:
            b = self._make_badge('ENCRYPTED', C_PURPLE, C_BG)
            surf.blit(b, (bx, y)); badge_h = max(badge_h, b.get_height())
        if badge_h:
            y += badge_h + 4

    # ── Right column: units ───────────────────────────────────────────────────

    def _draw_units_right(self, surf, s, y_top, y_bottom):
        call    = s.call
        x0      = VSEP_X + M
        col_w   = self.W - x0 - M
        y       = y_top

        if not call.units:
            return

        seen  = set()
        units = []
        for u in call.units:
            if u.unitId == -1 or u.unitId in seen:
                continue
            seen.add(u.unitId)
            units.append(u)

        if not units:
            return

        hdr = self.f_small.render(f'UNITS ({len(units)})', True, C_DIM)
        surf.blit(hdr, (x0, y))
        y += hdr.get_height() + 3

        unit_h    = self.f_small.get_linesize() + 4
        max_units = max(0, (y_bottom - y) // unit_h)

        for u in units[:max_units]:
            emr  = '★ ' if u.emergency else '  '
            tag  = f'  {u.tag}' if u.tag else ''
            line = _trunc(self.f_small, f'{emr}{u.unitId}{tag}', col_w)
            clr  = C_RED if u.emergency else C_TEXT
            surf.blit(self.f_small.render(line, True, clr), (x0, y))
            y += unit_h

        if len(units) > max_units:
            more = self.f_small.render(
                f'… +{len(units) - max_units}', True, C_DIM)
            surf.blit(more, (x0, y))

    # ── Idle state ────────────────────────────────────────────────────────────

    def _draw_idle(self, surf, s, y_top):
        if not s.connected:
            text, color = 'Connecting…', C_DIM
        elif s.paused:
            text, color = 'Paused', C_YELLOW
        else:
            text, color = 'Waiting for calls…', C_DIM

        idle = self.f_tg.render(text, True, color)
        surf.blit(idle, (M, y_top + 16))

    # ── Bottom bar: progress (left) + controls (right) ────────────────────────

    def _draw_bottom(self, surf, s):
        W, H = self.W, self.H
        bar_y = H - self._BOTTOM_H

        # Progress — left column
        prog_x  = M
        prog_w  = VSEP_X - M * 2 - 52   # leave room for elapsed text
        prog_cy = bar_y + self._BOTTOM_H // 2

        if s.playing:
            elapsed = s.elapsed
            filled  = int(prog_w * (elapsed % 60) / 60)
            pygame.draw.rect(surf, C_PANEL,  (prog_x, prog_cy - 7, prog_w, 14), border_radius=3)
            if filled > 0:
                pygame.draw.rect(surf, C_BLUE, (prog_x, prog_cy - 7, filled, 14), border_radius=3)
            pygame.draw.rect(surf, C_BORDER, (prog_x, prog_cy - 7, prog_w, 14), 1, border_radius=3)
            el = self.f_body.render(f'{elapsed:.1f}s', True, C_TEXT)
            surf.blit(el, (prog_x + prog_w + 6, prog_cy - el.get_height() // 2))
        else:
            dash = self.f_body.render('—', True, C_DIM)
            surf.blit(dash, (prog_x, prog_cy - dash.get_height() // 2))

        # Controls — right column
        self.btn_pause.label = '⏵ PLAY' if s.paused else '⏸ PAUSE'
        for btn in self._buttons:
            btn.draw(surf, self.f_btn)

        vol = self.f_vol.render(f'{self._volume}%', True, C_CYAN)
        surf.blit(vol, vol.get_rect(center=self._vol_rect.center))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hline(self, surf, y, w):
        pygame.draw.line(surf, C_BORDER, (0, y), (w, y))

    def _vline(self, surf, x, y0, y1):
        pygame.draw.line(surf, C_BORDER, (x, y0), (x, y1))

    def _make_badge(self, text, bg, fg) -> pygame.Surface:
        txt = self.f_badge.render(text, True, fg)
        pad = 4
        s   = pygame.Surface((txt.get_width() + pad * 2, txt.get_height() + pad),
                              pygame.SRCALPHA)
        pygame.draw.rect(s, bg, s.get_rect(), border_radius=4)
        s.blit(txt, (pad, pad // 2))
        return s
