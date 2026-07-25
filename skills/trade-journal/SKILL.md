---
name: trade-journal
description: Retrospective, descriptive analysis of closed trades — transaction-cost analysis (TCA), win/loss streaks, and hold-time distributions. It also covers P&L by symbol and by hour. On demand, it also computes per-fill slippage against arrival mid and interval VWAP. This skill is descriptive only. It reports "what happened today", not what to change. Use it when the user asks "how did I trade today", "how was my day", "what was my net P&L", or "session summary". Also use it when the user names TCA, slippage, post-mortem, or journal. Also use it for P&L breakdown, win rate, best/worst trade, hold times, or streaks. For prescriptive rule-mining and coaching, such as "what should I change" or "what mistakes", use trade-debrief. For a single-trade deep dive with counterfactuals, use trade-replay. For live open-position monitoring, use position-watchdog.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# trade-journal

## Purpose

Summarize what happened across closed trades. Three outputs:

1. **Overall + by-symbol + by-hour P&L** — cheap. It runs over fill
   history alone.
2. **Streaks + hold-time distribution** — from the same pass.
3. **Per-fill slippage vs arrival mid + interval VWAP** — on demand.
   One fill runs per invocation, because the script fetches bars
   around that fill.

This skill is descriptive only. For "what should I change", use `trade-debrief`.

## Environment routing

Demo (simulation) and live are two separate MCP servers. Account names are unique to one server. Once a workflow resolves an account on a server, every downstream call must go through that same server. This includes `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, history tools, etc. Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them. Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `fill_history` — per-fill times, prices, and quantities.
- `performance_summary` — pre-aggregated win rate, profit factor,
  and drawdown. Cross-check it against `streaks.py`'s output.
- `position_history` — P&L, quantity, and timestamps per closed
  position (aggregate view). No hold-time or MFE/MAE field — use
  `timeline_report`/`timeline_details` for those.
- `timeline_report` — existing timeline annotations. Also the source
  for per-trade `mae`/`mfe`/`hold_minutes`.
- `market_history` — arrival-window bars for slippage. Use this only
  when the user asks about slippage.
- `order_history` and `order_details` — to find `arrivalTimestamp`
  (order-submit time) for the slippage calculation.
- `user_profile` — discover available account names when the account
  is unknown.
- `describe` — call with `topic='response_format'` for the compact
  `format="columns"` output shape.

## Workflow

**Account resolution.** Every history call below requires `account=<name>`. If the account name is not in the conversation context, call `user_profile()` first. Its response's `accounts[].name` field lists every account on this MCP server. Pass that name as `account=` on every later call.

### 1. Day/week summary — "how did I trade today?"

```
fill_history(account=<acct>, startDate=<YYYY-MM-DD or "today">, endDate=<YYYY-MM-DD>)
```

`startDate`/`endDate` are date-level. They use `YYYY-MM-DD` or a natural term like `"today"` or `"this week"`, never a timestamp. `format="columns"` cuts multi-day responses by about 40-60% on result sets over 50 fills. See `describe(topic='response_format')`.

To get P&L in dollars, run `streaks.py` with a per-product value-per-point. Save the `fill_history` result to a file. Pass its path with `--file`. Never re-type or inline a large JSON payload in the command.

```bash
python3 scripts/streaks.py --file fill_history.json \
    --value-per-point-map ES:50 MES:5 NQ:20 MNQ:2 CL:1000
```

When the day is single-product, pass `--value-per-point <N>` instead.

Output fields consumed downstream:
- `overall.trades`, `overall.win_rate`, `overall.total_pnl_usd`
- `overall.avg_hold_minutes_winners` vs `avg_hold_minutes_losers` —
  if there is a material gap (for example, winners held twice as
  long), narrate it.
- `overall.longest_win_streak` / `longest_loss_streak` / `current_streak`
- `by_symbol` — per-product breakdown for mixed sessions
- `by_hour_utc` — time-of-day distribution

### 2. Single-fill slippage — "what was the slippage on that ES fill?"

Only run this when the user names a specific fill or a small set. It is expensive: one `market_history` call runs per fill.

Fetch bars around the fill. Two minutes before and two minutes after is enough. This window covers the arrival mid and the interval VWAP. The arrival mid comes from the bar that contains the order-submit time. The interval VWAP defaults to ±60s around the fill:

```
market_history(
  symbol=<sym>,
  barType="Minute",
  barSize=1,
  from=<fill_ts - 2min, ISO-8601>,
  to=<fill_ts + 2min, ISO-8601>
)
```

(One-minute bars are the finest time granularity. There is no 30-second bar. `from` requires `to`.)

Pair the bars with the fill, pulled from `fill_history` or `order_details`. Save the combined `{"fill": {...}, "bars": [...]}` object to a file.

```bash
python3 scripts/slippage.py --file fill_and_bars.json \
    --tick-size 0.25 \
    --vwap-window-seconds 60
```

Output fields:
- `arrival_mid` — midpoint at submit time
- `slippage_vs_mid` (price units) + `slippage_ticks`
- `interval_vwap` + `slippage_vs_vwap`

Sign convention: **positive = adverse**. See `references/tca-definitions.md`.

### 3. Position-level recap — MFE/MAE

When the user asks "how far in the money did that trade go?", pull `timeline_report`'s `trades[].mae`/`mfe`/`hold_minutes`, or `timeline_details`'s `summary.mae`/`mfe`/`hold_minutes` for one trade. `position_history` carries P&L, quantity, and timestamps for the closed position, but no MFE/MAE/hold-time field. No script runs for the aggregate view. If the user wants a bar-level replay, hand off to `trade-replay`.

## Cost posture

- `streaks.py` runs over `fill_history` alone. This is cheap and
  always safe.
- `slippage.py` requires a per-fill `market_history` fetch.
  **On-demand only.** Never batch across a day's fill list.

## Output idioms

- Day summary: "12 trades today, 7 winners (58% win rate), net +$1,420.
  Winners held avg 18 min, losers avg 8 min — you're cutting losers
  faster than winners, which is the right shape. Current streak: -2
  (last two NQ trades lost). ES contributed +$1,610; NQ -$190."
- Per-fill slippage: "ES buy at 7102.50 was 2.5 ticks adverse vs
  arrival mid (7101.875), 0.4 pts above 60s VWAP (7102.14). Fills on
  the ask are normal in a rising tape — not a venue issue."
- Pattern callout: "Your losing trades cluster 18:00–20:00 UTC
  (14–16 ET) — the post-lunch drift window. 0 wins, 3 losses there
  today."

## Disambiguation

- vs `trade-debrief`: journal reports descriptive TCA facts. Debrief
  proposes prescriptive coaching prompts and rule mining.
- vs `trade-replay`: journal summarizes many trades. Replay goes deep
  on one trade, with MFE/MAE and counterfactual exits.
- vs `position-watchdog`: journal is retrospective, on closed trades.
  Watchdog is live, on open positions.
- vs MCP `performance_summary`: it pre-aggregates P&L, win rate, and
  profit factor across an account's history, with different
  bucketing. Prefer it for multi-month views. Use `streaks.py` for
  same-day or same-week granularity, with an hour-of-day breakdown.

## Explicit non-goals

- **No judgment.** Journal reports facts. Whether a pattern is good
  or bad belongs in `trade-debrief` or `risk-coach`.
- **No slippage batch runs.** Per-fill only, per user ask.
- **No multi-leg strategy attribution.** Brackets / OCOs appear as
  independent open-close pairs. See `timeline_report` for strategy-
  level aggregation.
- **No forecasting.** Hold-time distributions are historical only.

## Resource layout

- `scripts/streaks.py` — FIFO round-trip pairing + overall/by-symbol/
  by-hour stats from `fill_history`. Input via `--file` or stdin.
- `scripts/slippage.py` — per-fill slippage vs arrival mid + interval
  VWAP. Input via `--file` or stdin.
- `scripts/fixtures/` — synthetic samples:
  - `fills_day_synthetic.json` — 8 fills across ES + NQ for streaks
  - `slippage_fill_synthetic.json` — 1 fill + 4 bars for slippage
- `references/tca-definitions.md` — slippage sign convention, round-
  trip pairing rules, P&L math, streak semantics, known gaps. Load
  it when you narrate a slippage sign or a round-trip pairing.
