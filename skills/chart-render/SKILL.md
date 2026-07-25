---
name: chart-render
description: This skill renders three static PNG charts, with Matplotlib. Candlestick charts, with VWAP, fill-marker, and price-level overlays. Horizontal volume-profile histograms, with POC, VAH, and VAL lines. Cumulative-P&L equity curves, with optional drawdown shading. Chart data comes from market_history bars, fill_history fills, market-context analytics, and trade-journal round-trip trades. Use it when the user asks to "chart", "plot", "draw", "visualize", or "render". Also use it when the user wants a picture of the bars, fills, equity, or profile. Also use it for a qualified "show", such as "show the chart", "show me the bars", or "show my equity curve". A bare "show me my positions" is NOT a chart request. Route it to position-watchdog or my_portfolio. It produces PNG output at a specified path. It is never interactive. This skill requires matplotlib (install with `pip install matplotlib`).
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# chart-render

## Purpose

Pattern questions ("is this a breakout?", "what did the profile look
like?", "am I up for the week?") get visual answers. Three static
PNG renderings: candles, volume profile, equity curve. Data in JSON
on stdin, path on --output, PNG on disk.

## Environment routing

Symbol/market data only — no account binding.
A sibling skill's account resolution might already pin the session to demo (simulation) or live.
If so, stay on that same MCP server.

## Dependencies

- Python 3.10+
- `matplotlib` (install: `pip install matplotlib`) — the only
  external dependency in the skill. Each script detects its absence
  and errors cleanly (exit code 3), with install instructions.
- Each script declares `matplotlib` in a PEP 723 metadata block, so
  `uv run <script>` installs the dependency for you.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `market_history` — bars for candles, profile
  histogram
- `fill_history` — fills for marker overlay on
  candles, or round-trips for the equity curve

## Skills consumed

- `market-context` for VWAP series, POC/VAH/VAL, ATR bands (ATR bands
  not yet rendered — see "Non-goals")
- `trade-journal`'s `streaks.py` for paired trades to feed the
  equity curve

## Workflow

### 1. Classify the ask → pick a renderer

| User phrasing | Script |
|---------------|--------|
| "chart ES 1-min today", "show the bars", "candles with VWAP" | `candles.py` |
| "volume profile", "where's the POC", "value area" | `profile_chart.py` |
| "equity curve", "P&L for the week", "am I up this month" | `equity_curve.py` |

### 2. Gather inputs

**Candles:**

```
market_history(
  symbol=..., barType="Minute", barSize=1|5,
  from=<ISO-8601>, to=<ISO-8601>
)
```

`from` requires `to`. If you pass only one, it errors. For a
"last N bars" intent, pass `count=` instead of a time range. The two
are mutually exclusive.

Optionally also:
- `market-context`'s `vwap.py` output for the VWAP series
- `fill_history` filtered to the window for fill markers
- `pretrade-risk` or `position-watchdog` output for stop/target lines

**Profile:**

`market-context`'s `profile.py` — reshape to:

```json
{"profile": [{"price": ..., "volume": ...}, ...],
 "poc": ..., "vah": ..., "val": ...}
```

**`profile.py` output is already in absolute prices.** The
`bar.open + offset × tickSize` reconstruction happens inside the
script. Pass POC / VAH / VAL straight through. Do **not** apply the
tick-offset conversion again. Otherwise, every horizontal line
renders shifted by `value × tickSize` away from where it should sit
on the chart, with no error to flag the mistake.

**Equity curve:**

```
fill_history(account=..., startDate=<YYYY-MM-DD>, endDate=<YYYY-MM-DD>)
```

(`startDate`/`endDate` are date-level; natural terms like `"this week"`
also work.)

Pipe through `trade-journal/scripts/streaks.py` to get round-trip
trades with `pnl_usd`.

### 3. Render

Save the source JSON to a file.
Pass its path with `--file`.
Never re-type or inline a large JSON payload in the command.

Run each script with `uv run`.
`uv run` reads the PEP 723 metadata block in the script and installs matplotlib for you.

```bash
uv run scripts/candles.py --file market_history.json --output /tmp/chart.png
uv run scripts/profile_chart.py --file profile.json --output /tmp/profile.png
uv run scripts/equity_curve.py --file trades.json --output /tmp/equity.png \
    --shade-drawdown
```

If `uv` is not available, use `python3` instead. Install matplotlib first.

**Output path:** pick `/tmp/<session_id>_<name>.png` by default. The
rendered image travels via the transcript, so the file itself is
ephemeral.

### 4. Display inline + narrate

Use the Read tool on the output PNG path. It returns the image
inline in the transcript. Pair it with 2-3 sentences of narrative
that name what the picture shows.

## Input shapes

### `candles.py`

```json
{
  "symbol": "ESU6",
  "title":  "ES 5m, 2026-04-20 13:30-14:30 UTC",
  "bars":   [{"timestamp": ISO, "open": ..., "high": ..., "low": ..., "close": ...}, ...],
  "vwap":   [{"timestamp": ISO, "value": ...}, ...],
  "fills":  [{"timestamp": ISO, "price": ..., "action": "Buy"|"Sell", "quantity": ...}, ...],
  "levels": [{"label": "stop", "price": 7141.0, "style": "dashed"}, ...]
}
```

All of `vwap`, `fills`, `levels` are optional. `bars` required.
`fill_history`'s real field is `quantity`, not `qty` — this reshape
target keeps that name. `candles.py`'s fill markers do not read the
field at all; it renders only `timestamp`, `price`, and `action`.

### `profile_chart.py`

```json
{
  "symbol": "ESU6",
  "title":  "ES profile, 2026-04-20 session",
  "profile": [{"price": ..., "volume": ...}, ...],
  "poc":  7158.0,
  "vah":  7165.0,
  "val":  7148.0,
  "price_range": [7140, 7175]
}
```

POC / VAH / VAL all optional.

### `equity_curve.py`

```json
{
  "title": "Equity curve, 2026-04-15 - 2026-04-20",
  "trades": [{"exit_time": ISO, "pnl_usd": ...}, ...]
}
```

Trades must be sorted oldest-first by exit_time.

## Sizing and styling

The defaults are deliberately readable. When the user does not ask
for a specific size or style, use them. See `references/styling.md`
for palette, DPI guidance, and override patterns. Load it only when
the user asks for customization.

## Output idioms

After you render the chart, narrate what the picture shows:

> "Chart saved to /tmp/es_20260420.png. Here's what stands out: VWAP
> acted as resistance on the 13:45 bar — the candle's wick tested
> 7109 (your target neighborhood) but closed back inside. That's
> where you got out — a reasonable exit given the VWAP rejection."

> "Profile for today's session. POC printed at 7103 with 3,420
> contracts — a tight value area (7100–7106). Price tested above VAH
> twice and rejected both times. Current 7102 is mid-value — no
> directional bias from the profile alone."

> "Equity curve shows +\$725 net over 9 trades, max drawdown \$280
> on Apr 17 afternoon (shaded). Streak pattern: 4 green days, no
> back-to-back red days — runs are short."

## Disambiguation

- **vs `market-context`**: market-context produces numbers and text
  narrative. Chart-render visualizes those numbers as PNG. Pair them
  for rich answers.
- **vs `trade-replay`**: this skill draws pictures only. `trade-replay`
  covers the numbers for ONE trade — MFE/MAE and counterfactual exits,
  as text. When the user wants to SEE that trade, render its bars via
  `candles.py`, with the entry/exit markers and stop/target levels.
- **vs `position-watchdog`**: watchdog gives the numeric state of a
  live position. Chart-render visualizes its history — especially
  useful when watchdog flags something unusual.

## Explicit non-goals

- **No interactive charts.** Static PNG is deliberate. It travels
  through transcripts, and needs no JS runtime.
- **No footprint / delta-per-price.** Significant rendering cost and
  niche audience. Stopgap: combine `market-context`'s `delta.py`
  output with the `fills` overlay on a candle chart.
- **No multi-pane layouts** (candles + volume subplot, candles +
  indicator). Chart one thing well. Stack two separate PNGs if
  needed.
- **No live charts.** Snapshots only. For continuous monitoring,
  use the Tradovate NinjaTrader frontend directly.
- **No ATR-band rendering** today. `market-context` produces ATR as
  a number, but ATR bands on candles need a per-bar ATR fetch, which
  inflates the input schema. This can be added when a user asks.
- **No destructive operations.** PNG writes go to the path supplied.
  The script never deletes or overwrites user files without an
  explicit path.

## Resource layout

- `scripts/candles.py` — candlestick rendering with optional VWAP,
  fills, and horizontal price levels. Width 14, height 6, DPI 140
  by default.
- `scripts/profile_chart.py` — horizontal volume histogram with POC
  (solid red), VAH/VAL (dashed), and optional price-range clip.
  Tall aspect (8 × 10), to read price vertically.
- `scripts/equity_curve.py` — cumulative-P&L line chart with
  --shade-drawdown option. Marker on each trade close.
- `references/styling.md` — palette hexes, sizing rationale, axis
  conventions, non-rendered items. Load it only to customize the
  output.
