"""
Layout for the 480×320 LCD display.

Section heights and column widths are defined as percentages of H/W.
Font sizes are defined as a percentage of their governing row height.
Colour constants (RGB tuples) are used for manual pygame drawing; the
matching hex values live in theme.json — keep both in sync.
"""

W, H = 480, 320


def pct(total, percent):
    return max(1, round(total * percent / 100))


MARGIN = 8

# ── Section heights as % of H ─────────────────────────────────────────────────
#   header + content + bottom = H
HEADER_HEIGHT     = pct(H, 12.5)   # ≈ 40 px
BOTTOM_BAR_HEIGHT = pct(H, 18.75)  # ≈ 60 px
CONTENT_HEIGHT    = H - HEADER_HEIGHT - BOTTOM_BAR_HEIGHT  # ≈ 220 px

# ── Column split as % of W ────────────────────────────────────────────────────
SEPARATOR_X = pct(W, 56.25)  # ≈ 270 px

# ── Derived Y positions ───────────────────────────────────────────────────────
CONTENT_Y = HEADER_HEIGHT
BOTTOM_Y  = H - BOTTOM_BAR_HEIGHT

# ── Font sizes as % of their governing row ────────────────────────────────────
HEADER_FONT_SIZE    = pct(HEADER_HEIGHT,     40)   # ≈ 16 pt
TALKGROUP_FONT_SIZE = pct(CONTENT_HEIGHT,    13)   # ≈ 28 pt
BODY_FONT_SIZE      = pct(HEADER_HEIGHT,     40)   # ≈ 16 pt
SMALL_FONT_SIZE     = pct(HEADER_HEIGHT,     35)   # ≈ 14 pt
BADGE_FONT_SIZE     = pct(HEADER_HEIGHT,     32)   # ≈ 13 pt
BUTTON_FONT_SIZE    = pct(BOTTOM_BAR_HEIGHT, 23)   # ≈ 14 pt
VOLUME_FONT_SIZE    = pct(BOTTOM_BAR_HEIGHT, 27)   # ≈ 16 pt

# ── Button layout (right side of bottom bar, all buttons grouped) ─────────────
#   All buttons stay together on the right; progress bar occupies the left gap.
#   skip(57) + 3 + pause(70) + 3 + vol_dn(34) + 3 + vol(36) + 3 + vol_up(34) = 243 px
BTN_H        = pct(BOTTOM_BAR_HEIGHT, 70)                   # ≈ 42 px
BTN_Y        = BOTTOM_Y + (BOTTOM_BAR_HEIGHT - BTN_H) // 2

BTN_SKIP_W   = 57
BTN_PAUSE_W  = 70
BTN_VOL_DN_W = 34
VOL_DISP_W   = 36
BTN_VOL_UP_W = 34

BTN_VOL_UP_X = W - MARGIN   - BTN_VOL_UP_W                  # 438
VOL_DISP_X   = BTN_VOL_UP_X - 3 - VOL_DISP_W               # 399
BTN_VOL_DN_X = VOL_DISP_X   - 3 - BTN_VOL_DN_W             # 362
BTN_PAUSE_X  = BTN_VOL_DN_X - 3 - BTN_PAUSE_W              # 289
BTN_SKIP_X   = BTN_PAUSE_X  - 3 - BTN_SKIP_W               # 229

# ── Progress bar (left gap in bottom bar) ─────────────────────────────────────
ELAPSED_W  = 46
ELAPSED_X  = BTN_SKIP_X - MARGIN - ELAPSED_W                # 175
PROG_X     = MARGIN                                          # 8
PROG_W     = ELAPSED_X - PROG_X - 4                         # ≈ 163 px
PROG_H     = pct(BOTTOM_BAR_HEIGHT, 23)                     # ≈ 14 px
PROG_CY    = BOTTOM_Y + BOTTOM_BAR_HEIGHT // 2              # vertical centre of bottom bar

# ── Header label rects (full-width header row) ────────────────────────────────
TITLE_X,    TITLE_W    = MARGIN,              140
STATUS_X,   STATUS_W   = TITLE_X + TITLE_W,  130
SYSNAME_X              = STATUS_X + STATUS_W  # past separator is fine in the header
SYSNAME_W              = W - SYSNAME_X - 110
HDR_INFO_X             = W - 108
HDR_INFO_W             = 108 - MARGIN

# ── Left column content ────────────────────────────────────────────────────────
LEFT_X       = MARGIN
LEFT_W_INNER = SEPARATOR_X - MARGIN * 2   # ≈ 254 px

TALKGROUP_H  = pct(CONTENT_HEIGHT, 20)    # ≈ 44 px  (hero talkgroup name)
ROW_H        = pct(CONTENT_HEIGHT, 10)    # ≈ 22 px  (tg-name / tg-group / freq-time)

TALKGROUP_Y   = CONTENT_Y + 4
TG_NAME_Y     = TALKGROUP_Y + TALKGROUP_H + 2
TG_GROUP_Y    = TG_NAME_Y   + ROW_H
FREQ_TIME_Y   = TG_GROUP_Y  + ROW_H
BADGES_AREA_Y = FREQ_TIME_Y + ROW_H

# ── Right column content ───────────────────────────────────────────────────────
RIGHT_X        = SEPARATOR_X + MARGIN + 1
RIGHT_W_INNER  = W - RIGHT_X - MARGIN

UNITS_HDR_H    = SMALL_FONT_SIZE + 4
UNITS_HDR_Y    = CONTENT_Y + 4
UNIT_ROW_H     = SMALL_FONT_SIZE + 6
UNIT_FIRST_Y   = UNITS_HDR_Y + UNITS_HDR_H + 3
MAX_UNIT_LABELS = 9

# ── Idle message (covers content area, left column) ───────────────────────────
IDLE_Y = CONTENT_Y + 16
IDLE_H = TALKGROUP_FONT_SIZE + 8

ELAPSED_Y = BOTTOM_Y
ELAPSED_H = BOTTOM_BAR_HEIGHT

# ── Colour palette (dark scanner theme) ──────────────────────────────────────
#   Hex equivalents live in theme.json — keep values in sync.
COLOR_BACKGROUND    = (13,  17,  23)    # #0d1117
COLOR_PANEL         = (22,  27,  34)    # #161b22
COLOR_BORDER        = (48,  54,  61)    # #30363d
COLOR_TEXT          = (230, 237, 243)   # #e6edf3
COLOR_DIM           = (110, 118, 129)   # #6e7681
COLOR_GREEN         = (63,  185,  80)   # #3fb950
COLOR_RED           = (248,  81,  73)   # #f85149
COLOR_ORANGE        = (240, 136,  62)   # #f0883e
COLOR_BLUE          = (31,  111, 235)   # #1f6feb
COLOR_CYAN          = (121, 192, 255)   # #79c0ff
COLOR_YELLOW        = (210, 153,  34)   # #d29922
COLOR_PURPLE        = (210, 168, 255)   # #d2a8ff
COLOR_BUTTON        = (36,   41,  47)   # #24292f
COLOR_BUTTON_HOVER  = (45,   51,  58)   # #2d333a
COLOR_BUTTON_ACTIVE = (56,  139, 253)   # #388bfd
