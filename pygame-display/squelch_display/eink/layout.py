"""
Layout constants for the 250×122 e-ink display.

All values are derived from W and H — change those two numbers and
every row height, divider position, and font size scales with them.
"""

W, H = 250, 122

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# ── Row heights — all derived from H ─────────────────────────────────────────
_ROW  = H // 7                          # base unit  ≈ 17 px
BAR_H = _ROW + 1                        # status bar ≈ 18 px
ROW_H = _ROW + 1                        # info / units / vol rows ≈ 18 px
TG_H  = H - BAR_H - 3 * ROW_H - 2      # talkgroup: remaining space ≈ 48 px

# ── Divider and row Y positions ───────────────────────────────────────────────
DIV1   = BAR_H
TG_Y   = DIV1 + 1
INFO_Y = TG_Y  + TG_H
UNIT_Y = INFO_Y + ROW_H
DIV2   = UNIT_Y + ROW_H + 1
VOL_Y  = DIV2 + 1

# ── Font sizes derived from row heights ───────────────────────────────────────
# These are the single source of truth — theme.json references them at startup.
F_BAR = max(10, BAR_H * 2 // 3)        # ≈ 12 pt  (status bar)
F_TG  = max(12, TG_H * 55 // 100)      # ≈ 26 pt  (talkgroup / clock)
F_ROW = max(10, ROW_H * 2 // 3)        # ≈ 12 pt  (info, units, vol)
