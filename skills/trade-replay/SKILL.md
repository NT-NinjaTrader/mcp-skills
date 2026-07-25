---
name: trade-replay
description: A deep dive on ONE closed trade. It reconstructs the trade's MFE (maximum favorable excursion) and MAE (maximum adverse excursion) across its lifetime, from bar OHLC. Then it runs alternate-exit counterfactuals against the same bars. The counterfactual scenarios are a fixed R target, an N-times-ATR trailing stop, a breakeven-after-X-R pin, and a time-based exit. Outputs include the exit timestamp, price, and reason. They also include the P&L in points, dollars, and R, and the delta vs the actual exit. Use it when the user asks "replay that trade", or asks for "MFE", "MAE", or "excursion" on a specific trade. Also use it for "what if I had held for X", "what if I'd used a trailing stop", "what if I'd moved my stop to breakeven", "how far did it go", "could have had", or "should have held". This is NOT backtesting. It runs no rule simulation across market history. Counterfactuals use only the user's actual fills. For many-trades summaries, use trade-journal. For session-level rule-mining, use trade-debrief.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# trade-replay

## Purpose

Answer deep questions about ONE closed trade, or a small set of
them. Where did the trade peak? How close did MAE come to the stop?
What do four alternate exit rules return, on the same bar window?

## Environment routing

Demo (simulation) and live are two separate MCP servers.
Account names are unique to one server.
Once a workflow resolves an account on a server, every downstream call must go through that same server.
This includes `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, history tools, etc.
Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `position_history` — closed-position pairs
  with entry/exit prices and times
- `fill_history` — fill-level timestamps for
  trades not fully covered by `position_history`
- `market_history` — bar OHLC across the trade
  lifetime + a short lookback after for counterfactual runs
- `search_contracts` — `tickSize`,
  `valuePerPoint` for the trade

## Skills consumed

- `market-context`'s `atr.py` — ATR for `atr_trail` scenarios
- `trade-journal`'s `streaks.py` — if the user references a trade
  that is not in `position_history`'s aggregation, use this to pair
  fills into trades

## Workflow

### 1. Identify the trade

The user names a trade by date/time/symbol or picks from a recent
list. Resolve via `position_history`:

```
position_history(
  account=<acct>,
  startDate=<YYYY-MM-DD>,
  endDate=<YYYY-MM-DD>
)
```

(`startDate` and `endDate` are date-level. They use `YYYY-MM-DD` or
a natural term like `"yesterday"`, never a timestamp.)

Take `avgBuyPrice` / `avgSellPrice` (or `buyPrice` / `sellPrice`),
`boughtTimestamp` / `soldTimestamp`, `pairedQty`, `symbol` — derive
direction from the sign of `netPos`. Fetch contract specs via
`search_contracts` for `tickSize` + `valuePerPoint`.

The caller must also know `planned_stop_points` — the stop distance
the user chose at trade entry. **This value denominates the
R-multiple outputs and `adverse_used_pct_of_stop`. A wrong guess
silently mis-scales every counterfactual.** Source options, in order
of preference:

1. Conversation context — the user told you when they opened the
   trade.
2. `pretrade-risk`'s recorded output (if the trade went through
   that skill).
3. **Ask the user.** If neither (1) nor (2) gives a value, request
   it explicitly before falling back. Never default silently.
4. Last-resort default (e.g., 1×ATR), only after the user declines
   to give one.
   Flag every output with "reconstructed stop — R-values are approximate", so the user reads them as such.

**Descriptive asks do not block on the stop value.**
For purely descriptive questions, such as "how far did it go my way / against me?" or MFE/MAE, run the replay immediately, without
`planned_stop_points`.
`excursion.py` handles its absence and emits null R-fields.
Report excursion in points and dollars.
Note "no stop distance on record — R-multiples omitted".
Offer to recompute in R,
if the user supplies the stop.
Only R-denominated outputs and
stop-referencing counterfactuals, such as `breakeven_after`,
`atr_trail`, and R-targets, need a value up front.

### 2. Fetch bars covering the trade + a lookback

```
market_history(
  symbol=<sym>,
  barType="Minute",
  barSize=1,
  from=<entry_time - 1min, ISO-8601>,
  to=<exit_time + 15min, ISO-8601>  # buffer for what-ifs that might exit later
)
```

(`from` requires `to`.
If you pass only one, it errors.)

The 15-min post-exit buffer lets counterfactuals explore "what if I'd held longer",
so the bar scan does not run out of data.

### 3. Compute excursion + derived metrics

Save the trade-with-bars payload to a file.
Pass its path with `--file`.
Never re-type or inline a large JSON payload in the command.

```bash
python3 scripts/excursion.py --file trade_with_bars.json
```

Output fields:
- `realized.{points,dollars,R}` — actual trade P&L
- `mfe.{points,dollars,R,at_timestamp,at_price}` — peak favorable
- `mae.{points,dollars,R,at_timestamp,at_price}` — peak adverse
- `derived.giveback_from_mfe_pct` — (mfe − realized) / mfe × 100
- `derived.realized_vs_mfe_pct` — realized / mfe × 100
- `derived.adverse_used_pct_of_stop` — mae / planned_stop × 100
- `derived.hold_minutes`

### 4. Run counterfactual(s)

Choose a scenario based on user intent. See
`references/replay-patterns.md` for the catalog:

| User phrasing | Script invocation |
|---------------|-------------------|
| "What if 2R target?" | `whatif.py --scenario r_target --r-target 2.0` |
| "What if a 1×ATR trail?" | `whatif.py --scenario atr_trail --atr-points <atr> --atr-multiple 1.0` |
| "What if breakeven after 1R?" | `whatif.py --scenario breakeven_after --trigger-R 1.0` |
| "What if I'd held 30 min?" | `whatif.py --scenario time_exit --minutes 30` |

Each run produces:
- `exit.{triggered,time,price,reason}` — whether the scenario fired
  and where
- `realized.{points,dollars,R}` — simulated P&L
- `vs_actual.{delta_points,delta_dollars,delta_R}` — vs the user's
  actual exit, when the trade input includes `actual_exit_price`

### 5. Multiple scenarios — sequential compare

For "which rule would have won?" questions, run each scenario in
sequence. Rank the results by `vs_actual.delta_dollars`. There is no
`batch.py` script. Just call `whatif.py` N times in the workflow:

```bash
for spec in \
    "r_target --r-target 2.0" \
    "r_target --r-target 3.0" \
    "atr_trail --atr-points 8 --atr-multiple 1.0" \
    "breakeven_after --trigger-R 1.0"; do
  python3 scripts/whatif.py --file trade_with_bars.json --scenario $spec
done
```

### 6. Narrate — with survivorship caveat if prescriptive

When the user's question implies a rule they might adopt ("should I
start using 2R targets?"), include the survivorship caveat from
`references/survivorship-caveat.md`:

> "One-trade counterfactual. For a rule-level evaluation across your
> book, route through `trade-debrief`."

For descriptive-only asks ("how far did it go?"), skip the caveat.

## Output idioms

**MFE + giveback:**

> "Long 4 ES @ 7150, exited 7164 (+\$2,800 / 1.75R). MFE +22.5 pts
> (+\$4,500 / 2.8R) at 14:02 — left \$1,700 on the table. MAE only
> 1 pt (used 12% of your 8-pt stop). Held 47 min."

**Single what-if:**

> "With a 2R target (7166), you'd have exited at 13:52 for +\$3,200
> — \$400 better than your actual \$2,800. One-trade counterfactual,
> not a rule endorsement."

**Multi-scenario compare:**

> "Ranked by $ vs your actual \$2,800:
>   1. time_exit 30min (exit 14:02 @ 7168.75): +\$3,750 (+\$950)
>   2. r_target 2.0 (exit 13:52 @ 7166): +\$3,200 (+\$400)
>   3. atr_trail 1×ATR (exit 14:07 @ 7164.50): +\$2,900 (+\$100)
>   4. r_target 3.0 (never hit, fell through): +\$2,250 (−\$550)
>   5. breakeven_after 1R (armed, fell through): +\$2,250 (−\$550)
>
> Patient rules (time_exit, r_target 2.0) beat your actual exit by
> \$400-950. Tighter rules (atr_trail) roughly matched. Breakeven
> pin was tied with the hopeful 3R target at the bottom — classic
> wait-too-long pattern. Still just one trade — run across N trades
> in `trade-debrief` if you're serious about a rule change."

## Disambiguation

- **vs `trade-journal`**: journal is many-trades descriptive —
  streaks, hold times, slippage.
  Replay is a one-trade deep dive.
  For "how far did trade #3 go today?", use replay.
  For "how did I trade today?", use journal.
- **vs `trade-debrief`**: debrief synthesizes mistake, pattern, and
  rule mining across a whole session, with the trade-debrief prompt
  library. Replay gives numeric counterfactuals on one trade. Use
  debrief when the user asks for prescriptive rules.
- **vs `position-watchdog`**: watchdog's what-if runs on the
  currently OPEN position (live). Replay covers closed trades. Do
  not use replay on an open position. The bars are not all there
  yet.

## Explicit non-goals

- **Not backtesting.** No rule simulation across market history. Only
  counterfactuals on the user's actual fills with real bar data in
  the trade's window.
- **Not a rule endorsement engine.** One-trade deltas are not rule
  claims. The survivorship caveat is mandatory for prescriptive asks.
- **Not live.** Replay is for CLOSED trades only.
- **No stop-tightening-at-time-T scenario.**
  For "what if I had tightened the stop 5 min in", the skill does not script this.
  It needs a rerun with a modified `planned_stop_points`.
  Explain this to the user.

## Resource layout

- `scripts/excursion.py` — MFE/MAE + derived metrics for one trade.
  Same math family as `trade-debrief/scripts/compute_derived.py`.
  Keep them in sync when the math evolves. Returns `realized`, `mfe`,
  `mae`, and a `derived` sub-object.
- `scripts/whatif.py` — counterfactual exit simulator. Four scenarios:
  `r_target`, `atr_trail`, `breakeven_after`, `time_exit`. Input is
  one trade plus bars. Output is the hypothetical exit, the realized
  stats, and the delta vs actual.
- `scripts/fixtures/es_long_trade.json` — one ES long trade (4 @ 7150
  → 7164 in 47 min) with 11 1-min bars covering entry through 15min
  post-exit. The skill uses it to smoke-test all four scenarios.
- `references/replay-patterns.md` — the 7-entry what-if library with
  script invocations, common parameter values, and interpretation
  notes. Load it when you choose a what-if scenario.
- `references/survivorship-caveat.md` — mandatory framing for rule-
  shaped what-ifs. When NOT to cite it and what to route the user to
  instead (`trade-journal`, `trade-debrief`).
