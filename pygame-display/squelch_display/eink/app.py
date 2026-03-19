"""E-ink display application — 250×122 Waveshare 2.13" HAT."""

import datetime
import io
import json
import os
import sys
import time

import pygame
import pygame_gui

from ..ipc import IpcReader, send_command
from ..state import DisplayState
from ..volume import get_pulse_volume, set_pulse_volume
from .layout import (
    W, H, BLACK, WHITE,
    STATUS_BAR_HEIGHT, TALKGROUP_Y, TALKGROUP_HEIGHT,
    SYSTEM_INFO_Y, ROW_HEIGHT, UNITS_Y,
    TOP_DIVIDER_Y, BOTTOM_DIVIDER_Y, VOLUME_Y,
    STATUS_FONT_SIZE, TALKGROUP_FONT_SIZE, CLOCK_FONT_SIZE, ROW_FONT_SIZE,
    TALKGROUP_CALL_HEIGHT, TALKGROUP_CALL_FONT_SIZE,
)

# Full refresh (displayPartBaseImage) every N seconds to clear ghosting.
_FULL_REFRESH_INTERVAL = 60.0


def _build_theme(theme_path: str) -> io.StringIO:
    """Load theme.json and inject computed font sizes from layout.py."""
    with open(theme_path) as f:
        theme = json.load(f)
    theme['defaults']['font']['size']       = str(ROW_FONT_SIZE)
    theme.setdefault('#status',         {}).setdefault('font', {})['size'] = str(STATUS_FONT_SIZE)
    theme.setdefault('#appname',        {}).setdefault('font', {})['size'] = str(STATUS_FONT_SIZE)
    theme.setdefault('#talkgroup',      {}).setdefault('font', {})['size'] = str(TALKGROUP_FONT_SIZE)
    theme.setdefault('#talkgroup-call', {}).setdefault('font', {})['size'] = str(TALKGROUP_CALL_FONT_SIZE)
    theme.setdefault('#clock',          {}).setdefault('font', {})['size'] = str(CLOCK_FONT_SIZE)
    theme.setdefault('#freq',           {}).setdefault('font', {})['size'] = str(ROW_FONT_SIZE)
    return io.StringIO(json.dumps(theme))


class EinkApp:
    def __init__(self, width=250, height=122, test=False):
        self.test  = test
        self.state = DisplayState()
        self.ipc   = IpcReader()

        self._volume           = 100
        self._running          = True
        self._epd              = None
        self._touch_reader     = None
        self._last_full_refresh = 0.0  # time.time() of last displayPartBaseImage

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._init_hardware()
        self._init_pygame()
        self._volume = get_pulse_volume()
        self.ipc.start()

        clock = pygame.time.Clock()

        while self._running:
            # Process all pending IPC messages before rendering.
            for msg in self.ipc.poll():
                if msg.get('type') == 'quit':
                    self._running = False
                    break
                elif msg.get('type') == 'state':
                    self.state.update(msg)

            if not self._running:
                break

            if self.test:
                # Test mode: pygame window at ~20 fps, no hardware I/O.
                dt = clock.tick(20) / 1000.0
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self._running = False
                    elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        self._running = False
                    elif ev.type == pygame.MOUSEBUTTONDOWN:
                        self._on_touch(*ev.pos)
                self._mgr.update(dt)
                self._render_and_push(full=False)
            else:
                # Production mode: mirror the Waveshare sample — run
                # displayPartial() in a continuous loop, exactly like the
                # sample calls it in a tight loop after displayPartBaseImage().
                # Keeping the controller exercised this way avoids the idle-gap
                # problem where a long pause after a full refresh leaves the
                # controller in a state that makes the next partial hang.
                #
                # displayPartBaseImage() (~2-3 s) is called once at startup
                # and then every _FULL_REFRESH_INTERVAL seconds to clear
                # ghosting and reset the 0x26 base register.
                #
                # displayPartial() (~0.3 s) handles all other frames and
                # naturally paces the loop — no sleep needed.
                now = time.time()
                full = (now - self._last_full_refresh) >= _FULL_REFRESH_INTERVAL
                self._mgr.update(1 / 20)
                self._render_and_push(full=full)
                if full:
                    self._last_full_refresh = time.time()

        self._cleanup()

    # ── Hardware init ─────────────────────────────────────────────────────────

    def _init_hardware(self) -> None:
        try:
            from waveshare_epd import epd2in13_V4 as mod
            self._epd = mod.EPD()
            self._epd.init()
            self._epd.Clear(0xFF)
        except ImportError:
            print('[eink] waveshare_epd not installed — simulation mode', file=sys.stderr)
        except Exception as exc:
            print(f'[eink] Hardware init error: {exc}', file=sys.stderr)

        if not self.test:
            self._init_touch()

    def _init_touch(self) -> None:
        try:
            from ..gt1151 import GT1151Reader
            bus = int(os.environ.get('SQUELCH_I2C_BUS', '1'))
            reader = GT1151Reader(on_touch=self._on_touch, i2c_bus=bus)
            if reader.start():
                self._touch_reader = reader
        except Exception as exc:
            print(f'[eink] Touch init error: {exc}', file=sys.stderr)

    def _cleanup(self) -> None:
        if self._touch_reader:
            self._touch_reader.stop()
        if self._epd:
            try:
                self._epd.init()
                self._epd.Clear(0xFF)
                self._epd.sleep()
            except Exception:
                pass
        pygame.quit()

    # ── Pygame / GUI init ─────────────────────────────────────────────────────

    def _init_pygame(self) -> None:
        if not self.test:
            os.environ['SDL_VIDEODRIVER'] = 'offscreen'
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
        pygame.init()

        _here  = os.path.dirname(os.path.abspath(__file__))
        _fonts = os.path.normpath(os.path.join(_here, '..', '..', 'fonts'))
        _theme = os.path.join(_here, 'theme.json')

        if self.test:
            info = pygame.display.Info()
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{info.current_w - W},0'
            self._screen = pygame.display.set_mode((W, H))
            pygame.display.set_caption('Squelch Tail — e-ink')
        else:
            # set_mode is required even in offscreen mode to establish a pixel
            # format; without it, Surface.convert() raises "No convert format".
            pygame.display.set_mode((W, H))
            self._screen = None

        self._surf = pygame.Surface((W, H))

        # Init order: UIManager (no theme) → register font paths → preload
        # → load theme with injected sizes.  Fonts must be registered before
        # the theme references them or pygame-gui falls back to system font.
        self._mgr = pygame_gui.UIManager((W, H))
        self._mgr.add_font_paths(
            'roboto',
            regular_path=os.path.join(_fonts, 'Roboto-Medium.ttf'),
            bold_path=os.path.join(_fonts, 'Roboto-Bold.ttf'),
        )
        self._mgr.add_font_paths(
            'roboto-mono',
            regular_path=os.path.join(_fonts, 'RobotoMono-Medium.ttf'),
            bold_path=os.path.join(_fonts, 'RobotoMono-Medium.ttf'),
        )
        _sizes = sorted({ROW_FONT_SIZE, STATUS_FONT_SIZE, TALKGROUP_FONT_SIZE, CLOCK_FONT_SIZE, TALKGROUP_CALL_FONT_SIZE})
        self._mgr.preload_fonts(
            [{'name': 'roboto',      'point_size': s, 'style': 'regular'} for s in _sizes] +
            [{'name': 'roboto',      'point_size': s, 'style': 'bold'}    for s in _sizes] +
            [{'name': 'roboto-mono', 'point_size': s, 'style': 'regular'} for s in _sizes]
        )
        self._mgr.get_theme().load_theme(_build_theme(_theme))

        # Pre-render volume hint arrows using Nerd Font icons at a large size then
        # scale down — bypasses pygame-gui's text pipeline and produces clean shapes.
        # \uf063 = nf-fa-arrow_down, \uf062 = nf-fa-arrow_up
        _hint_font_large = pygame.font.Font(
            os.path.join(_fonts, 'CaskaydiaMonoNerdFontPropo-Regular.ttf'), 64)
        _arrow_h = (H - VOLUME_Y) - 4
        def _make_arrow(ch):
            raw = _hint_font_large.render(ch, True, BLACK, WHITE).convert()
            w = max(1, int(raw.get_width() * _arrow_h / raw.get_height()))
            return pygame.transform.smoothscale(raw, (w, _arrow_h))
        self._glyph_vol_dn = _make_arrow('\uf063')
        self._glyph_vol_up = _make_arrow('\uf062')

        p = 2  # inner padding
        self._lbl = {
            'status':  pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, 0, W // 2, STATUS_BAR_HEIGHT),
                text='', manager=self._mgr, object_id='#status'),
            'appname': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(W // 2, 0, W // 2 - p, STATUS_BAR_HEIGHT),
                text='squelch-tail', manager=self._mgr, object_id='#appname'),
            'tg': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, TALKGROUP_Y, W - 2 * p, TALKGROUP_HEIGHT),
                text='', manager=self._mgr, object_id='#talkgroup'),
            'tg_call': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, 0, W - 2 * p, TALKGROUP_CALL_HEIGHT),
                text='', manager=self._mgr, object_id='#talkgroup-call'),
            'clock': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(0, TALKGROUP_Y, W, BOTTOM_DIVIDER_Y - TALKGROUP_Y),
                text='', manager=self._mgr, object_id='#clock'),
            'sys_info': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, SYSTEM_INFO_Y, W // 2 - p, ROW_HEIGHT),
                text='', manager=self._mgr, object_id='#sys-info'),
            'freq': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(W // 2, SYSTEM_INFO_Y, W // 2 - p, ROW_HEIGHT),
                text='', manager=self._mgr, object_id='#freq'),
            'units': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, UNITS_Y, W - 2 * p, ROW_HEIGHT),
                text='', manager=self._mgr, object_id='#units'),
            'vol': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(W // 8, VOLUME_Y, W * 3 // 4, H - VOLUME_Y),
                text='', manager=self._mgr, object_id='#volume'),
        }

    # ── Render ────────────────────────────────────────────────────────────────

    def _update_labels(self) -> None:
        s = self.state

        if s.paused:
            status = '|| PAUSED'
        elif s.lfActive:
            status = '● LIVE'
        elif s.connected:
            status = '● CONN'
        else:
            status = 'OFFLINE'
        self._lbl['status'].set_text(status)

        if s.call:
            tg    = s.call.tgLabel or str(s.call.talkgroupId)
            sys_l = s.call.systemLabel or f'Sys {s.call.systemId}'
            freq  = f'{s.call.freq / 1_000_000:.4f} MHz' if s.call.freq else ''
            seen, parts = set(), []
            for u in (s.call.units or []):
                key = u.tag if u.unitId == -1 else u.unitId
                if key not in seen:
                    seen.add(key)
                    parts.append(u.tag or str(u.unitId))
            units = ', '.join(parts)
            self._lbl['tg'].hide()
            self._lbl['tg_call'].set_text(tg)
            self._lbl['tg_call'].show()
            self._lbl['status'].hide()
            self._lbl['appname'].hide()
            self._lbl['clock'].set_text('')
        else:
            self._lbl['tg_call'].hide()
            self._lbl['tg'].set_text('')
            self._lbl['tg'].show()
            self._lbl['status'].show()
            self._lbl['appname'].show()
            self._lbl['clock'].set_text(datetime.datetime.now().strftime('%H:%M'))
            sys_l = freq = units = ''

        self._lbl['sys_info'].set_text(sys_l)
        self._lbl['freq'].set_text(freq)
        self._lbl['units'].set_text(units)
        self._lbl['vol'].set_text(f'VOL {self._volume}%')

    def _render_and_push(self, full: bool = False) -> None:
        self._update_labels()
        self._surf.fill(WHITE)
        self._mgr.draw_ui(self._surf)
        if not self.state.call:
            pygame.draw.line(self._surf, BLACK, (0, TOP_DIVIDER_Y), (W, TOP_DIVIDER_Y))
        pygame.draw.line(self._surf, BLACK, (0, BOTTOM_DIVIDER_Y), (W, BOTTOM_DIVIDER_Y))

        bar_h = H - VOLUME_Y
        dn_x = W // 16 - self._glyph_vol_dn.get_width() // 2
        up_x = W - W // 16 - self._glyph_vol_up.get_width() // 2
        glyph_y = VOLUME_Y + (bar_h - self._glyph_vol_dn.get_height()) // 2
        self._surf.blit(self._glyph_vol_dn, (dn_x, glyph_y))
        self._surf.blit(self._glyph_vol_up, (up_x, glyph_y))

        if self.test and self._screen:
            self._screen.blit(self._surf, (0, 0))
            pygame.display.flip()
            return

        if self._epd is None:
            return

        try:
            from PIL import Image
            raw = pygame.image.tostring(self._surf, 'RGB')
            img = Image.frombytes('RGB', (W, H), raw).convert('1')
            buf = self._epd.getbuffer(img)
            if full:
                # Full refresh: sets both 0x24 and 0x26 to buf, applies slow
                # waveform (~2-3 s).  Clears ghosting and re-establishes the
                # base image for subsequent partial diffs.
                self._epd.displayPartBaseImage(buf)
            else:
                # Partial refresh: write new frame to 0x24, diff against 0x26,
                # apply fast waveform (~0.3 s).  Then sync 0x26 to the current
                # screen so the next partial diff is always against what is
                # physically showing.
                self._epd.displayPartial(buf)
                self._epd.SetCursor(0, 0)
                self._epd.send_command(0x26)
                self._epd.send_data2(buf)
        except Exception as exc:
            print(f'[eink] Push error: {exc}', file=sys.stderr)

    # ── Touch ─────────────────────────────────────────────────────────────────

    def _on_touch(self, x: int, y: int) -> None:
        if y >= BOTTOM_DIVIDER_Y:
            self._volume = max(0, self._volume - 10) if x < W // 2 else min(100, self._volume + 10)
            set_pulse_volume(self._volume)
            send_command({'type': 'volume', 'value': self._volume})
        else:
            # Optimistically flip paused state so the display updates immediately.
            self.state.paused = not self.state.paused
            # If a call is currently playing, skip it (interrupt immediately)
            # before toggling pause so the queue doesn't start the next call.
            if self.state.call:
                send_command({'type': 'skip'})
            send_command({'type': 'pause'})
