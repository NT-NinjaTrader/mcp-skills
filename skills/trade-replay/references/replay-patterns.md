# Replay patterns — common what-if library

These are the counterfactual scenarios users typically ask about. Each entry shows the script invocation and what the answer means.

## Table of contents

1. Fixed R target
2. ATR trailing stop
3. Breakeven pin after 1R
4. Time-based exit
5. Best/worst alternate
6. MFE vs realized (giveback)
7. Stop-tightening variant

All scenarios take the same input (trade + bars). The bars must span the entry time through the exit time, plus a buffer after the exit. A 1-minute interval is good for intraday. Adjust it to the trade's natural timeframe.

---

## 1. Fixed R target

**Question:** "What if I'd held for 2R?"

```bash
python3 scripts/whatif.py --scenario r_target --r-target 2.0 --file input.json
```

**Interpretation:** target_price = entry ± (r_target × planned_stop_points). If the bars touched that price, the scenario fills you. If not, it falls through to the last bar's close, and flags `triggered: false`.

**Common R values:** 1.5, 2.0, 3.0. Anything past 3R on a scalper's stop distance is usually off-thesis.

**Output matters when:** `vs_actual.delta_dollars` is positive. A positive value means this R target nets more than the actual exit.

---

## 2. ATR trailing stop

**Question:** "What if I'd used a 1×ATR trailing stop?"

```bash
python3 scripts/whatif.py --scenario atr_trail \
    --atr-points 8 --atr-multiple 1.0 --file input.json
```

**Setup:** pass the ATR value from `market-context/atr.py` for the symbol at the trade's timeframe. The initial stop is the trade's `planned_stop_points`. Once the trade makes a new high (long) or a new low (short), the stop trails at `atr × multiple` away.

**Common multiples:** 0.5 (tight, quick exit), 1.0 (standard), 1.5-2.0 (generous, let winners run).

**Gotcha:** ATR trail results are heavily sensitive to bar interval. A 1-min trail exits sooner than a 5-min trail on the same symbol. Use the bars the trade actually used. If you do not know them, default to 5-min as a compromise.

---

## 3. Breakeven pin after 1R

**Question:** "What if I'd moved my stop to breakeven after 1R?"

```bash
python3 scripts/whatif.py --scenario breakeven_after \
    --trigger-R 1.0 --file input.json
```

**Setup:** the stop stays at the initial value, until the bar's favorable extreme reaches `trigger_R × planned_stop_points`. Then the stop moves to entry. It moves only once. There is no further tightening.

**Interpretation:** the trade can walk back through entry before it hits the target. In that case, this scenario usually looks WORSE than the actual trade. That is the lesson. Breakeven pins introduce a new source of stop-out risk. Choppy price action can shake you out at $0, even when the eventual direction is right.

**Common trigger_R values:** 0.5 (aggressive), 1.0 (classic), 1.5 (patient).

---

## 4. Time-based exit

**Question:** "What if I'd held exactly 30 min and exited at market?"

```bash
python3 scripts/whatif.py --scenario time_exit --minutes 30 --file input.json
```

**Setup:** exit at the close of the first bar whose timestamp is >= `entry_time + --minutes`. No stop, no target — just the clock.

**Useful when:** the user trades a "sessions-and-opens" style. Many intraday setups have a characteristic holding period (e.g., first 30 min of NY cash open). The time-exit scenario shows the trade's return over a fixed time horizon. This is descriptive, not prescriptive.

---

## 5. Best/worst alternate — not a scripted scenario

There is no `--scenario best_case`, because "best" depends on the rule. Instead, run several scenarios and rank them by `vs_actual.delta_dollars`, descending. See the loop pattern in SKILL.md.

## 6. MFE vs realized (giveback) — via excursion.py

**Question:** "How much did I leave on the table?"

```bash
python3 scripts/excursion.py --file input.json
```

See `derived.giveback_from_mfe_pct` and `realized_vs_mfe_pct`. The dollar value of giveback is `mfe.dollars − realized.dollars`.

## 7. Stop-tightening variant — not scripted

There is no generic "tighten stop at time T" scenario. If the user asks, compute it by hand. Treat the new stop as a second initial stop. Then rerun with a modified `planned_stop_points`. Explain that the result is a hypothetical. Stop-tightening changes position sizing in the real world, and this script does not re-solve that.

---

## Composing multiple scenarios

Typical user ask: "run 2R target, 3R target, 1×ATR trail, and BE@1R — which would've won?"

Shell loop pattern:

```bash
for sc in "r_target 2.0" "r_target 3.0" "atr_trail 8 1.0" "breakeven_after 1.0"; do
  # parse scenario name + params, run whatif.py, collect delta_dollars
done
```

Or just run them sequentially in the skill's workflow and compare outputs side-by-side. Narrate the winner.

## Survivorship caveat

If a what-if implies a rule the user could adopt, state the caveat. A per-trade counterfactual shows one possible result for THIS trade, under a different rule. It does NOT show what the rule earns over ALL the user's trades. See `survivorship-caveat.md`.

If the user asks "should I use 2R targets going forward?", the counterfactual on one winning trade is a single data point. One trade cannot answer "going forward". Direct the user to a full backtest or a cross-sectional study.
