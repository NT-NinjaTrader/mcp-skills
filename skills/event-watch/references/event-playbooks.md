# Event playbooks

Per-event narrative context.
When the user asks "why did ES move?" or "is CPI coming up?", consult the relevant entry.
It covers what drives the reaction, which products move most, and typical magnitudes.

**Magnitudes below are heuristics**, not forecasts.
Use `reaction_size.py` against the last 6–12 releases of the same event for a live estimate.

---

## US CPI / Core CPI

- **Release**: 08:30 ET, monthly (~10th–15th)
- **Primary movers**: equity indexes, bonds, USD
- **Typical ES 5-min reaction (2025-2026 sample)**: ±10–20 points;
  ±30+ on surprise beats/misses
- **Narrative**: hotter-than-consensus CPI → bonds sell off (yields up)
  → equity multiples compress → ES down. Cooler → reverse.
- **Watch**: core vs headline divergence; shelter and services
  components drive Fed commentary.

## US PCE / Core PCE

- **Release**: 08:30 or 10:00 ET, last Thu/Fri of month
- **Primary movers**: same as CPI but smaller magnitude
- **Why smaller**: PCE is the Fed's preferred measure. It arrives two weeks after CPI, when less information asymmetry remains.

## Nonfarm Payrolls (NFP)

- **Release**: 08:30 ET, first Friday of each month
- **Primary movers**: equity indexes, bonds, USD, gold
- **Typical ES 5-min reaction**: ±15–25 points; highest-vol release
  along with CPI and FOMC.
- **Narrative**: hot NFP + low unemployment → Fed hawkish → bonds sell
  off → ES can go either way (growth positive vs rate-hike negative).
  "Good news is bad news" in tightening cycles.
- **Sub-components**: average hourly earnings (wage inflation),
  participation rate.

## FOMC Rate Decision + Statement

- **Release**: 14:00 ET statement; 14:30 ET press conference
- **Schedule**: 8 meetings/year; projections every other meeting
- **Primary movers**: everything (indexes, bonds, metals, USD, crypto)
- **Typical ES move**: ±20–40 points across the 60-min window; Chair
  press conference frequently bigger than the statement itself.
- **Narrative**: language scrutiny over rate path ("continued"
  vs "further", "patient" vs "data-dependent"). SEP dot plot is the
  big one when released.
- **Alert idiom**: bracket ±30 points on pre-announcement lastPrice,
  since direction is unknown.

## US PPI (Producer Price Index)

- **Release**: 08:30 ET, day before CPI typically
- **Magnitude**: usually smaller than CPI; same direction when both surprise
- **Watch**: core PPI ex-food/energy is most quoted.

## ISM Manufacturing / Services PMI

- **Release**: 10:00 ET, 1st business day (mfg) / 3rd (services) of month
- **Magnitude**: ±5–10 ES points; bigger if below 50 (contraction)
- **Narrative**: since 2023, services PMI leads manufacturing as the dominant US indicator.

## Retail Sales

- **Release**: 08:30 ET, mid-month
- **Magnitude**: ±5–15 ES points
- **Narrative**: consumer health → GDP nowcast revisions.

## Initial Jobless Claims

- **Release**: 08:30 ET every Thursday
- **Magnitude**: usually modest (±5 ES points) unless a 4-week avg
  crosses a threshold or a major deviation from trend.

## EIA Crude Oil Inventories

- **Release**: 10:30 ET, Wednesdays (delayed to Thu on holiday weeks)
- **Primary movers**: CL, RB, HO (energy complex)
- **Typical CL 5-min reaction**: ±0.50 – $1.50/barrel
- **Narrative**: draw (inventory down) → bullish crude; build → bearish.
  Product inventories (gasoline, distillate) often matter more in
  summer/winter respectively.

## EIA Natural Gas Storage

- **Release**: 10:30 ET, Thursdays
- **Primary movers**: NG
- **Typical NG move**: ±$0.05–0.20/MMBtu

## OPEC+ Meetings

- **Schedule**: scheduled meetings + surprise calls
- **Primary movers**: CL (full complex)
- **Magnitude**: highly asymmetric — on surprise cuts, CL can move
  3–5% in a single session.

## Earnings (equity index context)

- **Schedule**: quarterly seasons (mid-Jan, mid-Apr, mid-Jul, mid-Oct)
- **Primary movers**: NQ > ES (tech-weighted); individual names
- **Watch mega-cap names after close**: AAPL, MSFT, NVDA, GOOGL, AMZN,
  META. NQ gap-moves overnight are common.
- **This skill**: surface earnings calendar from `earnings_calendar`;
  reaction-size math less useful than single-name option-implied moves
  (not available via this MCP).

## ECB Rate Decision

- **Release**: 08:15 ET (press conf ~08:45)
- **Primary movers**: 6E, German bonds
- **Magnitude on 6E**: ±50–100 pips

## Bank of Japan Meetings

- **Release**: ~22:00 ET evening before
- **Primary movers**: 6J
- **Historical**: can be outsized on YCC / intervention surprises.

---

## How to use this file

1. When the user asks about a specific event (CPI / FOMC / EIA / etc.), open this file.
   Surface the relevant entry as context.
2. Use `reaction_size.py` on the last 6–12 historical releases of the same event for an **empirical** magnitude, not the heuristic ranges here.
3. Translate points to dollars via `valuePerPoint × netPos` from `my_portfolio`.
4. If the user holds a position exposed to a known-risk event, propose a reaction-sized alert via `alerts-composer`:
   - **Breach bracket**: `lastPrice(ESU6) > ENTRY + 2σ OR lastPrice(ESU6) < ENTRY - 2σ`
   - σ ≈ historical `mean_abs_move` from `reaction_size.py`.
