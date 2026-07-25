# Regime caveat

**Historical correlation is not future correlation.**

Correlation is a statistic over a past window.
When you use it to size a hedge, you bet that the future window will look similar.
That assumption fails often, and exactly when you need the hedge most.

## The stability assumption

The hedge math in `hedge_sizing.py` says: "if ES moves 1%, NQ is expected to move β%."
That is a conditional expectation from a past regression.
Two things break it:

1. **Regime shifts.** ES/NQ β can swing 0.8 → 1.5 across cycles.
   The number you computed last Thursday may not apply today.
2. **Tail events.** In a crash, every correlation goes to 1 (or to
   -1 for flight-to-quality). Hedges sized for 0.87 correlation
   fail when realized is 0.99.

## How to frame hedge output

When you report a hedge proposal, always include the live correlation, not just β.
This way, the user sees the basis for it.
Mention the stationarity assumption once, briefly, and not repeatedly.

**Good:**
> "4 ES long, 1 NQ short covers 82% of your exposure (β 2.59, r
> 0.99 over last 16 sessions). Assumes the correlation holds — if
> ES and NQ decouple, the hedge won't protect you."

**Not good:**
> "Hedge is 1 NQ." (missing live stats + assumption)
> "This is guaranteed to protect you." (overclaim)
> "Historical correlation is not future correlation historical
> correlation is not future correlation..." (too repetitive; kills
> signal)

## When to flag regime shift explicitly

`correlation.py` emits `rolling.regime` as `tightening`, `loosening`,
or `stable`. Translate:

- **`tightening`**: current rolling r > mean + 1σ. The pair couples harder than usual. Hedges will work better short-term but may revert. Mention this.
- **`loosening`**: current rolling r < mean - 1σ. The pair decouples. A hedge sized on the historical mean will under-cover. **Mention this prominently.**
- **`stable`**: within 1σ of the mean. No special framing needed.

## When the user asks a rule question

"Should I always hedge ES with NQ?" is a rule question.
A single correlation run does not support a rule. Route to:

- `trade-journal` for multi-period observation.
- External backtest for proper rule validation.
- Explicit explanation: "I can compute the hedge for this
  position right now. Making it a standing rule needs broader
  evidence."

## What counts as enough history

A correlation computed over <20 bars has wide confidence intervals.
`correlation.py` requires ≥3 aligned bars, the bare minimum to compute r.
That is enough for the script to run, but not enough to trust.

Rough guidance:
- **20–50 samples**: exploratory; use with caution
- **50–200 samples**: reasonable for a pair with a stable history
- **200+ samples**: a good statistical basis, but it spans multiple regimes — check rolling

## Tail-risk awareness

The user may want to hedge a position to survive a specific worst-case scenario (e.g., "I want to be flat if the Fed surprises").
In that case, correlation-based hedging is the wrong tool.
That is a scenario-specific event hedge. Consider:

- Full-position exit instead of hedging
- A direct bet on the scenario (e.g., buying puts if the hedge vehicle
  supports options, which futures MCP does not)
- A bigger hedge with the understanding that β is unreliable in tails

Tell the user plainly when the tool does not fit.
Do not force a correlation-based answer when the situation is fundamentally one of event risk.
