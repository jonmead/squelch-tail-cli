"""
Layout for the 250×122 e-ink display.

Row heights are defined as percentages of H.
Font sizes are defined as a percentage of their row height.
Everything else is derived from those two sets of numbers.
"""

W, H = 250, 122

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

def pct(total, percent):
    return max(1, round(total * percent / 100))


# ── Row heights as % of H ─────────────────────────────────────────────────────
#   Must add up to ≤ 100% (remainder goes to talkgroup row)
STATUS_BAR_HEIGHT = pct(H, 16)   # ≈ 20 px
ROW_HEIGHT        = pct(H, 16)   # info / units / vol rows  ≈ 20 px  (each)
TALKGROUP_HEIGHT  = H - STATUS_BAR_HEIGHT - 3 * ROW_HEIGHT - 2   # whatever remains ≈ 44 px

# ── Y positions (computed, do not edit) ──────────────────────────────────────
TOP_DIVIDER_Y    = STATUS_BAR_HEIGHT
TALKGROUP_Y      = TOP_DIVIDER_Y + 1
SYSTEM_INFO_Y    = TALKGROUP_Y   + TALKGROUP_HEIGHT
UNITS_Y          = SYSTEM_INFO_Y + ROW_HEIGHT
BOTTOM_DIVIDER_Y = UNITS_Y       + ROW_HEIGHT + 1
VOLUME_Y         = BOTTOM_DIVIDER_Y + 1

# ── Font sizes as % of their row height ──────────────────────────────────────
STATUS_FONT_SIZE    = pct(STATUS_BAR_HEIGHT, 70)   # ≈ 12 pt
TALKGROUP_FONT_SIZE = pct(TALKGROUP_HEIGHT,  55)   # ≈ 24 pt
ROW_FONT_SIZE       = pct(ROW_HEIGHT,        70)   # ≈ 12 pt
