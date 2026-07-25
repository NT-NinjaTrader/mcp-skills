# Report schema — field provenance

The prompts assume a trade-report schema. This document reproduces
that schema's fields. This skill assembles an approximation of that
shape from the MCP tools available today. This file documents which
fields come from where, and which are intentionally `null` (never
fabricated).

## Top-level shape

```yaml
schema_version: 1
source: tradovate-mcp+mcp-skills
account_id: DEMO-ACCOUNT-1
trade_date: "2026-04-20"
contracts:                      # contract metadata, keyed by symbol
  ESZ6: {...}
summary: {...}                  # session aggregate
trades:                         # per-trade blocks
  - {...}
raw_timeline_report:            # passthrough of timeline_report
```

## Per-trade block

```yaml
trade_id: T-001                 # from caller — MCP has no trade_id field
contract_id: ESZ6               # MCP: fill.symbol
direction: long | short         # derived: sign of sum of signed fill qty
qty: 2                          # MCP: fill.quantity
entry:
  time: ISO                     # MCP: fill.timestamp (first entry fill)
  price: 7100.0                 # MCP: fill.price (avg across entry fills)
exit:
  time: ISO                     # MCP: fill.timestamp (last exit fill)
  price: 7105.25                # MCP: fill.price (avg across exit fills)
  realized_R: 1.31              # DERIVED: realized_points / planned_stop
  realized_points: 5.25         # DERIVED: (exit - entry) × signof(direction)
  realized_pnl_dollars: 525.0   # DERIVED: realized_points × vpp × qty
planned_stop_points: 4.0        # caller-provided (typically from bracket proposal)
mfe_points: 10.0                # DERIVED: peak favorable excursion, bar scan
mfe_dollars: 1000.0             # DERIVED: mfe_points × vpp × qty
mfe_R: 2.5                      # DERIVED: mfe_points / planned_stop
mae_points: 0.5                 # DERIVED: peak adverse excursion
mae_dollars: 50.0
mae_R: 0.125
derived:
  giveback_from_mfe_pct: 47.5   # DERIVED: (mfe - realized) / mfe × 100
  realized_vs_mfe_pct: 52.5     # DERIVED: realized / mfe × 100
  scale_out_count: null         # NOT RECONSTRUCTABLE from MCP — leave null
  stop_modified_count: null     # NOT RECONSTRUCTABLE from MCP — leave null
timeline: null                  # minute-by-minute volume features — NULL today
market_context:
  market_structure: trend_up    # from `market-context` skill output, optional
  market_volatility: elevated
  session_vwap: 7105.25
  atr_points: 8.1
contract_meta:                  # from MCP: search_contracts / market_snapshot
  product_name: E-Mini S&P 500
  contract_name: ESZ6
  tick_size: 0.25
  value_per_point: 50.0
  dollar_per_tick: 12.50
  is_micro: false
```

## Summary block

```yaml
summary:
  trades_count: 2              # total trade count
  winners: 2                   # count where realized_dollars > 0 (among pnl-known)
  losers: 0                    # count where realized_dollars < 0 (among pnl-known)
  win_rate: 1.0                # winners / (trades_count - trades_missing_pnl)
  total_pnl_dollars: 765.0     # sum — NULL when any trade has missing vpp
  trades_missing_pnl: 0        # count of trades whose realized_dollars is null
  mcp_reported:                # derived from performance_summary's {name, value} stat arrays
    net_pnl: 765.0             # extra.allTradeStats[] entry named "Total P/L"
    gross_profit: 780.0        # extra.allTradeStats[] entry named "Gross Profit"
    win_rate_pct: 100.0        # extra.allTradeStats[] entry named "% Profitable Trades"
    max_drawdown: 0.0          # extra.lossTradeStats[] entry named "Max Drawdown"
```

- If `trades_missing_pnl` is greater than 0, `total_pnl_dollars` is
  `null`, not a partial sum. A partial sum could give a prompt the
  wrong numbers. The caller must supply `value_per_point` for every
  symbol, in the `contracts` map.
- If `mcp_reported.net_pnl` disagrees with `total_pnl_dollars` by a
  material amount, surface the discrepancy in the debrief. Do not
  silently pick one value. Most often, this is a
  commission-inclusion difference.

## Data-quality safeguards in `compute_derived.py`

So that the prompts do not cite misleading facts, certain fields
become `null` when their inputs are insufficient:

| Missing input | Nulled output |
|---------------|---------------|
| `value_per_point` | `realized_dollars`, `mfe_dollars`, `mae_dollars` (points and R still computed) |
| `entry_time` | `mfe_points`, `mae_points`, and their dollar + R derivatives (prevents pre-trade bars from inflating the scan) |
| empty `bars` list | `mfe_points`, `mae_points`, and their derivatives |
| `planned_stop_points` missing/zero | `realized_R`, `mfe_R`, `mae_R` |
| `mfe_points == 0` (trade never went in favor) | `giveback_from_mfe_pct`, `realized_vs_mfe_pct` |

This is intentional. The prompt contract says "only use facts
present in the report". A null field simply drops out of citation.
It never appears as a misleading zero.

## Fields that are null today

These fields belong to the assembled report schema, but the MCP tools
cannot reach them:

- **`timeline[n].participation_rate_vs_session`** — a volume feature
  per minute. This needs tick-volume bar fetches and a session
  baseline. The MCP tools have no tick-resolution bar source, so
  this stays out of reach.
- **`timeline[n].poc_shift`** — market-profile POC migration. This is
  possible via `market-context`'s `profile.py`, but a per-minute
  cadence is expensive.
- **`derived.scale_out_count` / `derived.stop_modified_count`** —
  order action counts per trade. This needs a correlation of
  `order_history` and `fill_history` with bracket-leg
  classification. This skill does not count scale-out or stop-move
  actions. The `scale-manager` skill covers scale-out analytics.
- **`intent`** (planned entry/stop/target from the trade plan) — no
  MCP tool captures this today. It needs user input at trade-plan
  time.

**Guidance for prompts:** when a field is `null`, the prompt's
"fact-only with citations" rule means the analysis must not cite
it. Prompts 01/02/03/06/07 are resilient to nulls. They cite only
populated fields. Prompts 08/09 (clustering, expectancy) benefit
from populated `timeline[]` entries, but they still produce useful
output without them.

## How `assemble_report.py` ingests MCP data

The script accepts pre-joined input. The caller (the skill's workflow)
must fetch and pre-shape:

1. **Trades list** — run `trade-journal`'s `streaks.py` FIFO
   round-tripper over `fill_history` for the paired trades. Then run
   `compute_derived.py` with bar windows from `market_history`.
2. **Contracts map** — from `search_contracts` or `market_snapshot`,
   per touched symbol.
3. **Performance summary** — pass the `performance_summary` response
   directly. The script derives `net_pnl`, `gross_profit`,
   `win_rate_pct`, and `max_drawdown` by looking up specific stat
   names inside `extra.allTradeStats[]` and `extra.lossTradeStats[]` —
   `performance_summary` has no flat fields by these names.
4. **Market context** — optional; from `market-context` per symbol.

The script performs no MCP calls itself. This keeps it
deterministic, and runnable against fixtures for tests.
