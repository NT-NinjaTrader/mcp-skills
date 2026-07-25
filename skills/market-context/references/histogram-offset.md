# Histogram price-offset convention

**Every histogram level's `price` field is a tick offset from the bar's `open`, not an absolute price.**

## Why this matters

The `market_history` tool returns bars.
Each bar may carry a `histogram` array when you call the tool with `volumeProfile: true`.
Each histogram level has three integer fields:

```json
{ "price": -3, "bid": 120, "offer": 85 }
```

`price` here is **not** the actual traded price.
It is the number of ticks above or below the bar's `open`.
A reader who treats `price` as an absolute dollar value gets answers off by orders of magnitude.
Worse, the profile can look plausible but stay wrong.

## The reconstruction

Given:

- `bar.open` — the bar's opening price (absolute, e.g., `7150.00` for ES)
- `histogram[i].price` — the tick-offset integer (e.g., `-3`, `0`, `+7`)
- `tickSize` — the minimum price increment for the contract (e.g., `0.25` for ES, `1.00` for YM)

The actual price for level `i` is:

```python
actual_price = bar.open + histogram[i].price * tickSize
```

The combined volume at that price level is `bid + offer`.
`bid` counts contracts that traded against the bid.
`offer` counts contracts that traded against the offer.

## Why the offset encoding exists

Tick offsets shrink market-data payloads by a lot.
Most bars fit in ±15 ticks. A signed 16-bit integer per level is enough.
Absolute prices would need floats or scaled integers, and would make the bar much bigger.

The base price for every offset in a bar is that bar's own `open`.
Each bar therefore carries its own reference point.

## Obtain the tick size

`tickSize` is **not** in the `market_history` response. Obtain it from:

- `market_snapshot` — returns `tickSize` in each snapshot entry
- `search_contracts` — returns `tickSize` on each contract entry

Common values for reference, if a lookup isn't available:

| Product | tickSize |
|---|---|
| ES, MES | 0.25 |
| NQ, MNQ | 0.25 |
| RTY, M2K | 0.10 |
| YM, MYM | 1.00 |
| CL, MCL | 0.01 |
| GC, MGC | 0.10 |
| ZB | 1/32 = 0.03125 |
| ZN | 1/64 ≈ 0.015625 |

The table is an escape hatch. Prefer a live lookup.

## Failure modes to avoid

- **Do not skip the tick-size multiplication**. If you treat the offset as an integer price, the profile shifts to tiny numbers (±15, typically).
- **Do not reuse a stale `tickSize`**. A contract can change, for example a rollover from ES to a contract with a different tick size. Cache a fresh value for each symbol when that happens.
- **Do not treat `bid + offer` as one-sided flow**. The sum is the total volume at the level. Delta analysis uses `offer - bid` (aggressive-buyer imbalance) instead.
