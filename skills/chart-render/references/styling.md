# Styling conventions

The defaults match the skill's built-in palette. Load this file only
when the user asks to customize. Most invocations can use the
defaults.

## Palette

Used across all three scripts:

| Purpose | Hex | Where |
|---------|-----|-------|
| Bullish candle | `#1f7a1f` (deep green) | `candles.py` UP_COLOR |
| Bearish candle | `#b11e1e` (deep red) | `candles.py` DOWN_COLOR |
| Candle wick | `#333333` | `candles.py` WICK_COLOR |
| VWAP line | `#1e5fb5` (blue) | `candles.py` VWAP_COLOR, `equity_curve.py` LINE_COLOR |
| Buy marker | `#0a5d0a` (darker green) | `candles.py` BUY_MARKER |
| Sell marker | `#8b0000` (darker red) | `candles.py` SELL_MARKER |
| Profile bar | `#4a7fb8` (steel blue) | `profile_chart.py` PROFILE_COLOR |
| POC / drawdown | `#b11e1e` | `profile_chart.py` POC_COLOR, `equity_curve.py` DD_COLOR |
| Zero / reference line | `#888888` | `equity_curve.py` ZERO_LINE_COLOR |
| Level labels | `#444444` | `candles.py` horizontal-level annotation |

These colors work for accessibility. They read on both light and
dark backgrounds. Do not use pure red or green. They vibrate against
each other on some displays.

## Sizing

Default figure sizes per script:

| Script | width × height | DPI | Rationale |
|--------|---------------|-----|-----------|
| `candles.py` | 14 × 6 | 140 | Wide for many bars; keeps the time axis readable |
| `profile_chart.py` | 8 × 10 | 140 | Tall for price range; narrow for volume magnitudes |
| `equity_curve.py` | 12 × 5 | 140 | Wide for time; modest height (P&L is 1D signal) |

Override these with `--width`, `--height`, and `--dpi`. The minimum
useful DPI for transcript display is 100. 140 is crisp, but not huge.

## Typography

Matplotlib defaults are fine. This skill ships no custom fonts, and
no script sets a font family. Every chart renders in the Matplotlib
default font. A brand font is not available today. The scripts expose
no font flag, so a reader cannot change the font from the command
line.

## Axes

- **Top and right spines hidden**, on all charts. This matches
  modern editorial style, and it reduces visual noise.
- **Y-axis grid** on candles and equity curves. **X-axis grid** on
  profile — volume magnitude is the quantitative axis there.
- **Grid alpha 0.25, linewidth 0.5** — visible but not dominant.
- **Title left-aligned** for consistency with newsroom charts.

## Annotations

- Price levels on `candles.py` render as dashed/dotted horizontal
  lines WITH a right-aligned label "stop 7141.0" offset 4px right
  of the last bar.
- POC on `profile_chart.py` is a SOLID red line with a bold label.
  VAH and VAL show as dashed lines, the same color as the bars
  (de-emphasized).
- Fill markers show as upward triangles for Buy, and downward
  triangles for Sell. White edges make them stand off the candle
  bodies.

## When to override

- **Longer charts (full session, 100+ bars)**: bump width to 18-20.
- **Screenshot-into-slide**: bump DPI to 200+.
- **Dark-mode embed**: invert the palette. Matplotlib does not ship
  a semantic dark mode. Edit the constants at the top of each script
  instead — a local one-line edit. Do not ship a config file for
  this.

## What this skill does NOT render

- **Interactive charts** — static PNG is deliberate. It travels
  through transcripts, and needs no JS runtime.
- **Footprint / delta-per-price** — possible, but it adds
  complexity. This skill does not render it today. A stopgap is to
  combine `market-context`'s `delta.py` output with `candles.py`'s
  marker overlay.
- **Multi-pane** (price + volume + indicator) — this needs a
  subplot layout. It is not available today. Chart one thing well.
- **Equity with trades overlay on same axes** — trades have one
  y-axis (price), equity has another ($ cumulative). This skill
  keeps them separate on purpose.
