# TCA definitions & conventions

## Slippage sign convention

**Positive slippage means adverse execution** — worse than the benchmark:

| Side | Benchmark | Adverse = |
|------|-----------|-----------|
| Buy  | arrival mid | paid above mid (fill_price > mid) |
| Sell | arrival mid | received below mid (fill_price < mid) |

`slippage.py`'s formula:

```
sign = +1 for Buy, -1 for Sell
slippage = sign × (fill_price − benchmark)
```

Negative slippage means price improvement — favorable execution.

## Benchmarks

### Arrival mid

Midpoint of bid/ask at the bar that contains the **order submit time** (`arrivalTimestamp` in the fill payload). When bid/ask has no quote, fall back to the bar's close.

- This shows what the market offered before the order queued or
  routed to the exchange. It is a decision-quality benchmark.
- It does not measure the venue's execution quality. It measures
  only the round-trip from submit to fill.

### Interval VWAP (volume-weighted average price)

Volume-weighted typical price `(H+L+C)/3`, across bars whose timestamp falls within `[fill − window, fill + window]`. The default half-width is 60s in `slippage.py`. Tune it with `--vwap-window-seconds`.

- This approximates "what the crowd paid" in the same window.
- It gives a better signal when the arrival mid is unavailable, for
  example on a market order with no explicit queue time.

**The script reports ticks via `slippage_ticks = slippage_vs_mid / tick_size`.** For example, a buy of ES fills 0.75 above the arrival mid. The result is 3 ticks adverse.

## Round-trip pairing (streaks.py)

FIFO per symbol:
- Each new fill either **opens** a new position fragment or
  **closes** the oldest opposing fragment.
- An open matches the same side as an existing fragment, or it is
  the first fill on that symbol.
- A close matches the opposite side of the oldest open fragment.
- A close that is smaller than the front-of-queue open partially
  consumes it. A larger close produces one completed trade. It
  leaves the remainder to close the next fragment, or to open a new
  fragment in the opposite direction.
- **One completed trade comes from each full close of an open
  fragment.**
  Partial-exit fills produce multiple smaller completed trades, one
  per close.

**Consequence:** the `trades` count is not fills/2 when a trader pyramids a position or partially scales out. See `scale-manager` for scaling-specific analytics.

## P&L math

```
pnl_points = exit_price − entry_price          (long)
           = entry_price − exit_price          (short)
pnl_usd    = pnl_points × value_per_point × qty
```

`value_per_point` comes from `--value-per-point` for a uniform value, or `--value-per-point-map` for a per-product-root value (for example, `ES:50 MES:5 NQ:20`). The product root is the symbol without its trailing digits and month letter. For example, `ESZ6` becomes `ES`, and `MNQZ6` becomes `MNQ`.

`fill_history` has no commission or fee field. `pnl_usd` is gross P&L — it does not deduct commissions.

## Streak semantics

- **Winning streak** — consecutive trades with `pnl_usd > 0`.
- **Losing streak** — consecutive trades with `pnl_usd < 0`.
- **Flat trades**, where `pnl_usd == 0`, break both streaks.
- `current_streak` is the signed run-length at the tail: `+N` for a
  winning streak, `-N` for a losing streak, or `0` when the last
  trade was flat.

## By-hour bucketing

Trades bucket by **entry-time hour in UTC** (`%H` of the first open fill for each trade). The key uses two-digit padding (`"14"`, not `14`), so its JSON sort order matches chronological order.

Why UTC: fills come back in UTC per MCP convention. If the user asks, convert to local ET in the narration. The bucket key itself stays in UTC, for stability across DST transitions.

## Known gaps

- **Rollover and calendar-spread pairings.**
  The script does not recognize them. A Buy ESU6 and a Sell ESZ6 do
  not cancel each other. If pre-rollover activity confuses the
  reported P&L, the user must filter it out.
- **Multi-leg strategies**, such as OCO and brackets, appear as
  independent open/close pairs. Strategy-level P&L is out of scope
  here. `timeline_report` and `performance_summary` on the MCP
  already aggregate that way.
- **Currency conversion.**
  The script does not handle it. All dollar figures assume the
  account's base currency. For mixed-currency products, the user
  must spot-check the figures.
