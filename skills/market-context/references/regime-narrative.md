# Regime narrative templates

Use these patterns to translate numeric output from `vwap.py`, `profile.py`, and `atr.py` into short, opinionated sentences. The goal is clarity for the trader who reads the response, not exhaustive detail.

Rules:

- When there is a position context, lead with dollar or point terms first and R-multiples second.
- Round to the product's native tick precision. Do not report VWAP as `7151.4328`. Report `7151.50` instead (snapped to the nearest tick).
- State regime as a fact, not a forecast. "Trading above VWAP" is fine, but "headed higher" is not.
- Never invent a comparison. If no prior baseline is available, say so.

## Volatility regime

From `atr.py` output.

| Condition | Narrative |
|---|---|
| `realized_vol_annualized_pct` > 1.5 × its long-run median | "volatility expansion — realized vol {X}% vs historical {Y}%" |
| `realized_vol_annualized_pct` < 0.7 × its long-run median | "volatility contraction — realized vol {X}% vs historical {Y}%" |
| Within ±30% of median | "volatility in a normal range ({X}% realized)" |

If no historical median is available, state the raw value. Add an honest disclaimer, for example "no session baseline supplied — reporting raw".

## Price vs VWAP

From `vwap.py`'s `price_z_score` and the current close.

| `price_z_score` | Narrative |
|---|---|
| z > 1.5 | "trading {Z}σ above session VWAP — extended upside" |
| 0.5 < z ≤ 1.5 | "holding above VWAP at {Z}σ" |
| -0.5 ≤ z ≤ 0.5 | "hugging VWAP — neutral session" |
| -1.5 ≤ z < -0.5 | "trading below VWAP at {Z}σ" |
| z < -1.5 | "trading {Z}σ below session VWAP — extended downside" |

## Market profile

From `profile.py`.

- If the latest close is inside the Value Area (between VAL and VAH):
  "inside value (VAL {val}, POC {poc}, VAH {vah}) — balanced session so far"
- If above VAH by more than one tick:
  "trading above value — VAH {vah}, last {last}, session POC at {poc}"
- If below VAL by more than one tick:
  "trading below value — VAL {val}, last {last}, session POC at {poc}"

## Cross-symbol relative strength

From `cross_symbol.py`.

- Highlight the pair with the largest `|spread_pct|`:
  "{A} outperforming {B} by {spread} pts today" (positive spread) or
  "{A} lagging {B} by {|spread|} pts today" (negative spread)
- When that is the notable observation, mention one or two major pairs even when spreads stay tight.
  Example: "ES/NQ tracking within 0.1 pts, correlated session".
- **Never** promote an intra-day relative-strength number to a claim about correlation. That belongs in the `correlation-hedge` skill.

## What not to say

- Do not say "Breakout". That is a pattern claim, not a regime measurement.
- Do not say "Momentum" without a time window. It is vague.
- Do not say "Bullish" or "bearish". These are predictions that masquerade as facts.
- Do not report a percent move without a stated time window.

Prefer observations that you can check against the numbers, for example: "closed {X}pts above its 5-minute open", "lost {X}% from session high of {Y}", or "returned to VWAP after a {Z}σ excursion".
