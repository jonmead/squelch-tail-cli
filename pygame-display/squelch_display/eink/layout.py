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
BAR_H = pct(H, 15)   # status bar           ≈ 18 px
ROW_H = pct(H, 15)   # info / units / vol   ≈ 18 px  (each)
TG_H  = H - BAR_H - 3 * ROW_H - 2   # talkgroup: whatever remains ≈ 48 px

# ── Y positions (computed, do not edit) ──────────────────────────────────────
DIV1   = BAR_H
TG_Y   = DIV1 + 1
INFO_Y = TG_Y  + TG_H
UNIT_Y = INFO_Y + ROW_H
DIV2   = UNIT_Y + ROW_H + 1
VOL_Y  = DIV2 + 1

# ── Font sizes as % of their row height ──────────────────────────────────────
F_BAR = pct(BAR_H, 70)   # status bar font   ≈ 12 pt
F_TG  = pct(TG_H,  55)   # talkgroup font    ≈ 26 pt
F_ROW = pct(ROW_H, 70)   # info/units/vol    ≈ 12 pt
