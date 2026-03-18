"""
LCD display application — 480×320 colour touchscreen (Raspberry Pi GPIO LCD HAT).

Layout (landscape 480×320):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ SQUELCH TAIL  ● LIVE     Metro Police          Q:2  HTG                 │  header 40px
  ├─────────────────────────────────────╥────────────────────────────────────┤
  │ FIRE DISPATCH                       ║  UNITS (5)                        │
  │ Fire Operations Center              ║    ★ 1234  Engine 5               │  content
  │ Fire · EMS                          ║      5678  Dispatch               │  220px
  │ 460.0000 MHz  ·  12:34:56           ║      9012  Unit 3                 │
  │ ★ EMERGENCY   ENCRYPTED            ║      5432  …                      │
  ├─────────────────────────────────────╫────────────────────────────────────┤
  │ ▓▓▓▓▓▓░░░░░  7.3s                  ║  [SKIP] [PAUSE]  [−] 80% [+]     │  bottom 60px
  └─────────────────────────────────────╨────────────────────────────────────┘

  Left column: 0–269 px   Vertical separator: x=270   Right column: 271–479 px
"""

import datetime
import io
import json
import os

import pygame
import pygame_gui

from ..ipc import IpcReader, send_command
from ..state import DisplayState
from ..volume import get_pulse_volume, set_pulse_volume
from .layout import (
    W, H, MARGIN,
    HEADER_HEIGHT, SEPARATOR_X, CONTENT_Y, BOTTOM_Y,
    HEADER_FONT_SIZE, TALKGROUP_FONT_SIZE, BODY_FONT_SIZE,
    SMALL_FONT_SIZE, BADGE_FONT_SIZE, BUTTON_FONT_SIZE, VOLUME_FONT_SIZE,
    PROG_X, PROG_W, PROG_H, PROG_CY,
    BTN_H, BTN_Y,
    BTN_SKIP_X, BTN_SKIP_W, BTN_PAUSE_X, BTN_PAUSE_W,
    BTN_VOL_DN_X, BTN_VOL_DN_W, VOL_DISP_X, VOL_DISP_W,
    BTN_VOL_UP_X, BTN_VOL_UP_W,
    TITLE_X, TITLE_W, STATUS_X, STATUS_W,
    SYSNAME_X, SYSNAME_W, HDR_INFO_X, HDR_INFO_W,
    LEFT_X, LEFT_W_INNER,
    TALKGROUP_Y, TALKGROUP_H, TG_NAME_Y, ROW_H,
    TG_GROUP_Y, FREQ_TIME_Y, BADGES_AREA_Y,
    RIGHT_X, RIGHT_W_INNER,
    UNITS_HDR_Y, UNITS_HDR_H, UNIT_ROW_H, UNIT_FIRST_Y, MAX_UNIT_LABELS,
    IDLE_Y, IDLE_H,
    ELAPSED_X, ELAPSED_Y, ELAPSED_W, ELAPSED_H,
    COLOR_BACKGROUND, COLOR_PANEL, COLOR_BORDER,
    COLOR_BLUE, COLOR_RED, COLOR_PURPLE,
)


def _build_theme(theme_path: str) -> io.StringIO:
    """Load theme.json and inject computed font sizes from layout.py."""
    with open(theme_path) as f:
        theme = json.load(f)

    def _set(keys, value):
        node = theme
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    _set(['defaults',    'font', 'size'],                 str(BODY_FONT_SIZE))
    _set(['UIButton',    'font', 'size'],                 str(BUTTON_FONT_SIZE))
    _set(['#title',      'font', 'size'],                 str(HEADER_FONT_SIZE))
    _set(['#talkgroup',  'font', 'size'],                 str(TALKGROUP_FONT_SIZE))
    _set(['#idle',       'font', 'size'],                 str(TALKGROUP_FONT_SIZE))
    _set(['#idle-paused','font', 'size'],                 str(TALKGROUP_FONT_SIZE))
    _set(['#volume',     'font', 'size'],                 str(VOLUME_FONT_SIZE))
    _set(['#freq-time',  'font', 'size'],                 str(BODY_FONT_SIZE))
    for sid in ('#status-live', '#status-connected',
                '#status-paused', '#status-offline'):
        _set([sid, 'font', 'size'],                       str(HEADER_FONT_SIZE))
    for uid in ('#units-hdr', '#unit', '#unit-emergency'):
        _set([uid, 'font', 'size'],                       str(SMALL_FONT_SIZE))

    return io.StringIO(json.dumps(theme))


def _fmt_freq(freq) -> str:
    if freq is None:
        return ''
    return f'{freq / 1_000_000:.4f} MHz'


class LcdApp:
    def __init__(self, width=480, height=320, rotate=0,
                 fullscreen=False, touch=True, test=False):
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

        # Tracked object IDs for dynamic theming
        self._status_id = '#status-offline'
        self._idle_id   = '#idle'
        self._unit_ids  = ['#unit'] * MAX_UNIT_LABELS

        # Stored for per-frame manual drawing
        self._call_emergency = False
        self._call_encrypted = False

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        if not self.test:
            # SDL hints for Pi GPIO displays — skipped in test mode
            os.environ.setdefault('SDL_FBDEV',       '/dev/fb1')
            os.environ.setdefault('SDL_VIDEODRIVER',  'fbcon')
            os.environ.setdefault('SDL_MOUSEDRV',     'TSLIB')
            os.environ.setdefault('TSLIB_FBDEVICE',   '/dev/fb1')

        os.environ['SDL_VIDEO_HIGHDPI_DISABLED'] = '1'
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

        pygame.init()
        pygame.mouse.set_visible(self.test)

        flags = 0
        if not self.test:
            flags |= pygame.NOFRAME
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        if self.test:
            info = pygame.display.Info()
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{info.current_w - self.W},0'
        self._screen = pygame.display.set_mode((self.W, self.H), flags)
        pygame.display.set_caption('Squelch Tail')

        self._init_pygame_gui()
        self._volume = get_pulse_volume()
        self._update_ui()   # set initial label state

        self.ipc.start()
        clock = pygame.time.Clock()

        while self._running:
            dt = clock.tick(30) / 1000.0
            self._handle_events()
            self._handle_ipc()
            self._update_elapsed()
            self._mgr.update(dt)
            self._render()
            pygame.display.flip()

        pygame.quit()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_pygame_gui(self) -> None:
        _here  = os.path.dirname(os.path.abspath(__file__))
        _fonts = os.path.normpath(os.path.join(_here, '..', '..', 'fonts'))
        _theme = os.path.join(_here, 'theme.json')

        # Init order: UIManager (no theme) → register font paths → preload
        # → load theme with injected sizes.  Fonts must be registered before
        # the theme references them or pygame-gui falls back to system font.
        self._mgr = pygame_gui.UIManager((self.W, self.H))
        self._mgr.add_font_paths(
            'caskaydia-propo',
            regular_path=os.path.join(_fonts, 'CaskaydiaMonoNerdFontPropo-Regular.ttf'),
            bold_path=os.path.join(_fonts, 'CaskaydiaMonoNerdFontPropo-Bold.ttf'),
        )
        self._mgr.add_font_paths(
            'caskaydia-mono',
            regular_path=os.path.join(_fonts, 'CaskaydiaMonoNerdFontMono-Regular.ttf'),
            bold_path=os.path.join(_fonts, 'CaskaydiaMonoNerdFontMono-Bold.ttf'),
        )
        _sizes = sorted({BODY_FONT_SIZE, HEADER_FONT_SIZE, TALKGROUP_FONT_SIZE,
                         SMALL_FONT_SIZE, BUTTON_FONT_SIZE, VOLUME_FONT_SIZE})
        self._mgr.preload_fonts(
            [{'name': 'caskaydia-propo', 'point_size': s, 'style': 'regular'} for s in _sizes] +
            [{'name': 'caskaydia-propo', 'point_size': s, 'style': 'bold'}    for s in _sizes] +
            [{'name': 'caskaydia-mono',  'point_size': s, 'style': 'regular'} for s in _sizes]
        )
        self._mgr.get_theme().load_theme(_build_theme(_theme))

        # Badge font — loaded directly for manual pygame rendering
        self._badge_font = pygame.font.Font(
            os.path.join(_fonts, 'CaskaydiaMonoNerdFontPropo-Bold.ttf'), BADGE_FONT_SIZE)

        self._create_labels()
        self._create_buttons()

    def _create_labels(self) -> None:
        m = self._mgr
        R = pygame.Rect

        # ── Header row (full width) ───────────────────────────────────────────
        self._lbl_title = pygame_gui.elements.UILabel(
            R(TITLE_X,   0, TITLE_W,   HEADER_HEIGHT), 'SQUELCH TAIL',
            m, object_id='#title')
        self._lbl_status = pygame_gui.elements.UILabel(
            R(STATUS_X,  0, STATUS_W,  HEADER_HEIGHT), '',
            m, object_id='#status-offline')
        self._lbl_sysname = pygame_gui.elements.UILabel(
            R(SYSNAME_X, 0, SYSNAME_W, HEADER_HEIGHT), '',
            m, object_id='#sys-name')
        self._lbl_hdr_info = pygame_gui.elements.UILabel(
            R(HDR_INFO_X, 0, HDR_INFO_W, HEADER_HEIGHT), '',
            m, object_id='#hdr-info')

        # ── Left column: call metadata ────────────────────────────────────────
        self._lbl_talkgroup = pygame_gui.elements.UILabel(
            R(LEFT_X, TALKGROUP_Y, LEFT_W_INNER, TALKGROUP_H), '',
            m, object_id='#talkgroup')
        self._lbl_tg_name = pygame_gui.elements.UILabel(
            R(LEFT_X, TG_NAME_Y,   LEFT_W_INNER, ROW_H), '',
            m, object_id='#tg-name')
        self._lbl_tg_group = pygame_gui.elements.UILabel(
            R(LEFT_X, TG_GROUP_Y,  LEFT_W_INNER, ROW_H), '',
            m, object_id='#tg-group')
        self._lbl_freq_time = pygame_gui.elements.UILabel(
            R(LEFT_X, FREQ_TIME_Y, LEFT_W_INNER, ROW_H), '',
            m, object_id='#freq-time')

        # ── Right column: units ───────────────────────────────────────────────
        self._lbl_units_hdr = pygame_gui.elements.UILabel(
            R(RIGHT_X, UNITS_HDR_Y, RIGHT_W_INNER, UNITS_HDR_H), '',
            m, object_id='#units-hdr')
        self._unit_labels = [
            pygame_gui.elements.UILabel(
                R(RIGHT_X, UNIT_FIRST_Y + i * UNIT_ROW_H, RIGHT_W_INNER, UNIT_ROW_H),
                '', m, object_id='#unit')
            for i in range(MAX_UNIT_LABELS)
        ]

        # ── Idle message (shown when no active call) ──────────────────────────
        self._lbl_idle = pygame_gui.elements.UILabel(
            R(MARGIN, IDLE_Y, W - MARGIN * 2, IDLE_H), '',
            m, object_id='#idle')

        # ── Bottom bar ────────────────────────────────────────────────────────
        self._lbl_elapsed = pygame_gui.elements.UILabel(
            R(ELAPSED_X, ELAPSED_Y, ELAPSED_W, ELAPSED_H), '',
            m, object_id='#elapsed')
        self._lbl_volume = pygame_gui.elements.UILabel(
            R(VOL_DISP_X, BTN_Y, VOL_DISP_W, BTN_H), '',
            m, object_id='#volume')

    def _create_buttons(self) -> None:
        m = self._mgr
        R = pygame.Rect
        self._btn_skip   = pygame_gui.elements.UIButton(
            R(BTN_SKIP_X,   BTN_Y, BTN_SKIP_W,   BTN_H), 'SKIP',
            m, object_id='#btn-skip')
        self._btn_pause  = pygame_gui.elements.UIButton(
            R(BTN_PAUSE_X,  BTN_Y, BTN_PAUSE_W,  BTN_H), 'PAUSE',
            m, object_id='#btn-pause')
        self._btn_vol_dn = pygame_gui.elements.UIButton(
            R(BTN_VOL_DN_X, BTN_Y, BTN_VOL_DN_W, BTN_H), '−',
            m, object_id='#btn-vol-dn')
        self._btn_vol_up = pygame_gui.elements.UIButton(
            R(BTN_VOL_UP_X, BTN_Y, BTN_VOL_UP_W, BTN_H), '+',
            m, object_id='#btn-vol-up')

    # ── Event handling ────────────────────────────────────────────────────────

    def _handle_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self._running = False

            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if   k == pygame.K_ESCAPE:                      self._running = False
                elif k == pygame.K_SPACE:                       self._do_skip()
                elif k == pygame.K_p:                           self._do_pause()
                elif k in (pygame.K_EQUALS, pygame.K_PLUS):    self._vol_up()
                elif k == pygame.K_MINUS:                       self._vol_dn()

            elif ev.type == pygame_gui.UI_BUTTON_PRESSED:
                if   ev.ui_element is self._btn_skip:   self._do_skip()
                elif ev.ui_element is self._btn_pause:  self._do_pause()
                elif ev.ui_element is self._btn_vol_dn: self._vol_dn()
                elif ev.ui_element is self._btn_vol_up: self._vol_up()

            elif ev.type in (pygame.FINGERDOWN, pygame.FINGERUP):
                # Pi GPIO LCD may send FINGER events; synthesize mouse events
                # so pygame-gui can handle button press/release correctly.
                pos = (int(ev.x * self.W), int(ev.y * self.H))
                btn = pygame.MOUSEBUTTONDOWN if ev.type == pygame.FINGERDOWN \
                      else pygame.MOUSEBUTTONUP
                self._mgr.process_events(
                    pygame.event.Event(btn, pos=pos, button=1, touch=True))
                continue

            self._mgr.process_events(ev)

    def _handle_ipc(self) -> None:
        for msg in self.ipc.poll():
            if msg.get('type') == 'quit':
                self._running = False
            elif msg.get('type') == 'state':
                self.state.update(msg)
                self._update_ui()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_skip(self):  send_command({'type': 'skip'})
    def _do_pause(self): send_command({'type': 'pause'})

    def _vol_up(self):
        self._volume = min(150, self._volume + 5)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': min(100, self._volume)})
        self._lbl_volume.set_text(f'{self._volume}%')

    def _vol_dn(self):
        self._volume = max(0, self._volume - 5)
        set_pulse_volume(self._volume)
        send_command({'type': 'volume', 'value': min(100, self._volume)})
        self._lbl_volume.set_text(f'{self._volume}%')

    # ── UI state updates ──────────────────────────────────────────────────────

    def _update_ui(self) -> None:
        s = self.state
        self._update_status(s)
        self._update_header_info(s)
        self._btn_pause.set_text('▶ PLAY' if s.paused else '⏸ PAUSE')
        self._lbl_volume.set_text(f'{self._volume}%')
        if s.call:
            self._show_call(s)
        else:
            self._show_idle(s)

    def _update_status(self, s) -> None:
        if s.paused:
            new_id, text = '#status-paused',    '⏸ PAUSED'
        elif s.lfActive:
            new_id, text = '#status-live',      '● LIVE'
        elif s.connected:
            new_id, text = '#status-connected', '● CONN'
        else:
            new_id, text = '#status-offline',   'OFFLINE'

        if new_id != self._status_id:
            self._lbl_status.change_object_id(new_id)
            self._status_id = new_id
        self._lbl_status.set_text(text)

    def _update_header_info(self, s) -> None:
        parts = []
        if s.queueLen  > 0:       parts.append(f'Q:{s.queueLen}')
        if s.avoidCount > 0:      parts.append(f'A:{s.avoidCount}')
        if s.holdSys is not None: parts.append('HSY')
        if s.holdTg  is not None: parts.append('HTG')
        self._lbl_hdr_info.set_text('  '.join(parts))
        self._lbl_sysname.set_text(
            (s.call.systemLabel or f'System {s.call.systemId}') if s.call else '')

    def _show_call(self, s) -> None:
        call = s.call
        self._lbl_idle.hide()

        # Left column
        self._lbl_talkgroup.show()
        self._lbl_talkgroup.set_text(call.tgLabel or str(call.talkgroupId))

        self._lbl_tg_name.show()
        self._lbl_tg_name.set_text(
            call.tgName if (call.tgName and call.tgName != call.tgLabel) else '')

        self._lbl_tg_group.show()
        grp_parts = [p for p in [call.tgGroup, call.tgGroupTag] if p]
        self._lbl_tg_group.set_text(' · '.join(grp_parts))

        self._lbl_freq_time.show()
        freq_str = _fmt_freq(call.freq)
        time_str = ''
        if call.startTime:
            try:
                dt = datetime.datetime.fromisoformat(
                    call.startTime.replace('Z', '+00:00')).astimezone()
            except (ValueError, AttributeError):
                dt = datetime.datetime.fromtimestamp(float(call.startTime) / 1000)
            time_str = dt.strftime('%H:%M:%S')
        self._lbl_freq_time.set_text('  ·  '.join(p for p in [freq_str, time_str] if p))

        # Badge state stored for per-frame drawing
        self._call_emergency = call.emergency
        self._call_encrypted = call.encrypted

        # Right column: de-duplicate units
        seen, units = set(), []
        for u in call.units:
            if u.unitId == -1 or u.unitId in seen:
                continue
            seen.add(u.unitId)
            units.append(u)

        if units:
            self._lbl_units_hdr.show()
            self._lbl_units_hdr.set_text(f'UNITS ({len(units)})')
        else:
            self._lbl_units_hdr.hide()

        for i, lbl in enumerate(self._unit_labels):
            if i < len(units):
                u = units[i]
                prefix = '★ ' if u.emergency else ''
                tag    = f'  {u.tag}' if u.tag else ''
                lbl.set_text(f'{prefix}{u.unitId}{tag}')
                target_id = '#unit-emergency' if u.emergency else '#unit'
                if self._unit_ids[i] != target_id:
                    lbl.change_object_id(target_id)
                    self._unit_ids[i] = target_id
                lbl.show()
            else:
                lbl.set_text('')
                lbl.hide()

    def _show_idle(self, s) -> None:
        for lbl in (self._lbl_talkgroup, self._lbl_tg_name,
                    self._lbl_tg_group, self._lbl_freq_time,
                    self._lbl_units_hdr):
            lbl.hide()
        for lbl in self._unit_labels:
            lbl.hide()

        self._call_emergency = False
        self._call_encrypted = False

        if not s.connected:
            text, new_id = 'Connecting…', '#idle'
        elif s.paused:
            text, new_id = 'Paused',      '#idle-paused'
        else:
            text, new_id = 'Waiting for calls…', '#idle'

        if self._idle_id != new_id:
            self._lbl_idle.change_object_id(new_id)
            self._idle_id = new_id
        self._lbl_idle.set_text(text)
        self._lbl_idle.show()

    def _update_elapsed(self) -> None:
        if self.state.playing:
            self._lbl_elapsed.set_text(f'{self.state.elapsed:.1f}s')
        else:
            self._lbl_elapsed.set_text('—')

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self) -> None:
        surf = self._screen
        surf.fill(COLOR_BACKGROUND)

        # Header panel (slightly lighter than background)
        pygame.draw.rect(surf, COLOR_PANEL, (0, 0, self.W, HEADER_HEIGHT))

        # Structure lines
        pygame.draw.line(surf, COLOR_BORDER, (0,           CONTENT_Y), (self.W,      CONTENT_Y))
        pygame.draw.line(surf, COLOR_BORDER, (0,           BOTTOM_Y),  (self.W,      BOTTOM_Y))
        pygame.draw.line(surf, COLOR_BORDER, (SEPARATOR_X, CONTENT_Y), (SEPARATOR_X, BOTTOM_Y))

        # pygame-gui draws all labels and buttons
        self._mgr.draw_ui(surf)

        # Manual draws on top: progress bar and call-state badges
        self._draw_progress(surf)
        self._draw_badges(surf)

    def _draw_progress(self, surf) -> None:
        if not self.state.playing:
            return
        elapsed = self.state.elapsed
        filled  = int(PROG_W * (elapsed % 60) / 60)
        top     = PROG_CY - PROG_H // 2
        pygame.draw.rect(surf, COLOR_PANEL,  (PROG_X, top, PROG_W, PROG_H), border_radius=3)
        if filled > 0:
            pygame.draw.rect(surf, COLOR_BLUE, (PROG_X, top, filled, PROG_H), border_radius=3)
        pygame.draw.rect(surf, COLOR_BORDER, (PROG_X, top, PROG_W, PROG_H), 1, border_radius=3)

    def _draw_badges(self, surf) -> None:
        if not (self._call_emergency or self._call_encrypted):
            return
        bx = LEFT_X
        by = BADGES_AREA_Y
        if self._call_emergency:
            b = self._make_badge('★ EMERGENCY', COLOR_RED,    (230, 237, 243))
            surf.blit(b, (bx, by))
            bx += b.get_width() + 6
        if self._call_encrypted:
            b = self._make_badge('ENCRYPTED',   COLOR_PURPLE, COLOR_BACKGROUND)
            surf.blit(b, (bx, by))

    def _make_badge(self, text: str, bg, fg) -> pygame.Surface:
        txt = self._badge_font.render(text, True, fg)
        pad = 4
        s   = pygame.Surface(
            (txt.get_width() + pad * 2, txt.get_height() + pad), pygame.SRCALPHA)
        pygame.draw.rect(s, bg, s.get_rect(), border_radius=4)
        s.blit(txt, (pad, pad // 2))
        return s
