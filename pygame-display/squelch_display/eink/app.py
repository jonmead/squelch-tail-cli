"""E-ink display application — 250×122 Waveshare 2.13" HAT."""

import datetime
import os
import sys
import time

import pygame
import pygame_gui

from ..ipc import IpcReader, send_command
from ..state import DisplayState
from ..volume import get_pulse_volume, set_pulse_volume

W, H  = 250, 122
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# ── Layout ────────────────────────────────────────────────────────────────────
BAR_H  = 18                  # status bar
DIV1   = BAR_H               # first divider
TG_Y   = DIV1 + 1            # talkgroup row
TG_H   = 42
INFO_Y = TG_Y  + TG_H        # system · freq row
INFO_H = 16
UNIT_Y = INFO_Y + INFO_H     # units row
UNIT_H = 16
DIV2   = UNIT_Y + UNIT_H + 2 # second divider
VOL_Y  = DIV2 + 1            # volume row
VOL_H  = H - VOL_Y


class EinkApp:
    def __init__(self, width=250, height=122, test=False):
        self.test    = test
        self.state   = DisplayState()
        self.ipc     = IpcReader()
        self._volume        = 100
        self._running       = True
        self._dirty         = True
        self._partial_count = 0
        self._epd           = None
        self._touch_reader  = None
        self._last_time_str = ''

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._init_hardware()
        self._init_pygame()
        self._volume = get_pulse_volume()
        self.ipc.start()

        clock = pygame.time.Clock()

        while self._running:
            for msg in self.ipc.poll():
                if msg.get('type') == 'quit':
                    self._running = False
                    break
                elif msg.get('type') == 'state':
                    self.state.update(msg)
                    self._dirty = True

            # Redraw on standby when the minute changes
            if not self.state.call:
                now = datetime.datetime.now().strftime('%H:%M')
                if now != self._last_time_str:
                    self._dirty = True

            if self.test:
                dt = clock.tick(20) / 1000.0
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self._running = False
                    elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        self._running = False
                    elif ev.type == pygame.MOUSEBUTTONDOWN:
                        self._on_touch(*ev.pos)
                self._mgr.update(dt)
                self._render_and_push()
            elif self._dirty:
                self._mgr.update(1 / 20)
                self._render_and_push()
                self._dirty = False
                time.sleep(0.05)
            else:
                time.sleep(0.05)

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

        _here  = os.path.dirname(__file__)
        _fonts = os.path.normpath(os.path.join(_here, '..', '..', 'fonts'))
        _theme = os.path.join(_here, 'theme.json')

        if self.test:
            self._screen = pygame.display.set_mode((W, H))
            pygame.display.set_caption('Squelch Tail — e-ink')
        else:
            self._screen = None

        self._surf = pygame.Surface((W, H))
        self._mgr  = pygame_gui.UIManager((W, H), _theme)

        self._mgr.add_font_paths(
            'bitter',
            regular_path=os.path.join(_fonts, 'Bitter-Regular.ttf'),
            bold_path=os.path.join(_fonts, 'Bitter-Bold.ttf'),
        )
        self._mgr.preload_fonts([
            {'name': 'bitter', 'point_size': 12, 'style': 'regular'},
            {'name': 'bitter', 'point_size': 12, 'style': 'bold'},
            {'name': 'bitter', 'point_size': 26, 'style': 'bold'},
        ])

        p = 2  # padding
        self._lbl = {
            'status':  pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, p, W * 2 // 3, BAR_H - 2 * p),
                text='', manager=self._mgr, object_id='#status'),
            'appname': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(W * 2 // 3, p, W // 3 - p, BAR_H - 2 * p),
                text='squelch-tail', manager=self._mgr, object_id='#appname'),
            'tg': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, TG_Y + 1, W - 2 * p, TG_H - 2),
                text='', manager=self._mgr, object_id='#talkgroup'),
            'info': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, INFO_Y + 1, W - 2 * p, INFO_H - 2),
                text='', manager=self._mgr, object_id='#info'),
            'units': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, UNIT_Y + 1, W - 2 * p, UNIT_H - 2),
                text='', manager=self._mgr, object_id='#units'),
            'vol': pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(p, VOL_Y + 1, W - 2 * p, VOL_H - 2),
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
            info  = '  ·  '.join(x for x in [sys_l, freq] if x)
            seen, parts = set(), []
            for u in (s.call.units or []):
                key = u.tag if u.unitId == -1 else u.unitId
                if key not in seen:
                    seen.add(key)
                    parts.append(u.tag or str(u.unitId))
            units = ', '.join(parts)
        else:
            self._last_time_str = tg = datetime.datetime.now().strftime('%H:%M')
            info = units = ''

        self._lbl['tg'].set_text(tg)
        self._lbl['info'].set_text(info)
        self._lbl['units'].set_text(units)
        self._lbl['vol'].set_text(f'VOL {self._volume}%')

    def _render_and_push(self) -> None:
        self._update_labels()
        self._surf.fill(WHITE)
        self._mgr.draw_ui(self._surf)
        pygame.draw.line(self._surf, BLACK, (0, DIV1), (W, DIV1))
        pygame.draw.line(self._surf, BLACK, (0, DIV2), (W, DIV2))

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
            if self._partial_count >= 20:
                self._epd.init_fast()
                self._epd.displayPartBaseImage(buf)
                self._partial_count = 0
            else:
                self._epd.displayPartial(buf)
                self._partial_count += 1
        except Exception as exc:
            print(f'[eink] Push error: {exc}', file=sys.stderr)

    # ── Touch ─────────────────────────────────────────────────────────────────

    def _on_touch(self, x: int, y: int) -> None:
        if y >= DIV2:
            # Bottom bar: left = vol down, right = vol up
            self._volume = max(0, self._volume - 10) if x < W // 2 else min(100, self._volume + 10)
            set_pulse_volume(self._volume)
            send_command({'type': 'volume', 'value': self._volume})
        else:
            send_command({'type': 'pause'})
        self._dirty = True
