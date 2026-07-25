# Guardrail flag taxonomy

Each flag that `health.py` or `stop_drift.py` can emit, what it means, and how to triage it. Use these when you narrate a health dashboard. The flag key stays stable for tools; the narrative below is for the user.

## Per-position flags

### `no_stop_attached`

**Meaning:** The position has a non-zero `netPos` but no working stop order exists for its symbol.

**Why it matters:** An unprotected position carries unlimited downside risk. Market gaps, news, and flash crashes give no guardrail.

**Triage prompt:**
- "No stop attached on {symbol}. Current open P&L {open_pl}, last price {last}. Do you want to place a stop?"
- If the user has a risk budget, volunteer a range: "A stop at entry minus 1×ATR would be {price}, risking {risk_dollars} ({pct}% of your daily budget)."

### `no_bracket_attached`

**Meaning:** The position has no stop and no target attached. This is more severe than `no_stop_attached` — it also means no profit-taking plan.

**Triage prompt:** Use the same prompt as above, and also suggest a target at an R-multiple of the proposed stop.

### `ambiguous_protection: stop` / `ambiguous_protection: target`

**Meaning:** More than one working order matches the stop (or target) shape for this symbol. `health.py` cannot pick the right one. This happens when two or more opposing-action orders share the same shape. None of them carries `bracket` metadata to link it to a specific entry.

**Why it matters:** The dashboard cannot report a `stop_price` or `distance_to_stop_*` field without a confirmed order. A guess could report the wrong risk number to the user.

**Triage prompt:**
- "I see more than one candidate stop order on {symbol} and can't tell which one protects this position. Can you confirm the order ID?"
- Point the user at `my_portfolio`'s `workingOrders[]` for the raw list.

### Stop moved against entry

`health.py` cannot flag this from a single snapshot. It has no record of the stop's original placement. Use `stop_drift.py` with `--original-stop` for this instead. It reports `current_risk_dollars` against `original_risk_dollars`, so you can state the ratio directly.

**Why it matters:** A stop moved against the entry is the most common behavioral loss-maker. The original plan said X; emotion says "just give it a little more room." Each re-move compounds the risk.

**Triage prompt:**
- "Your stop on {symbol} has been moved from {original_stop} to {current_stop} — current risk {current_risk} vs original {original_risk}. That's {ratio}× the original plan."
- Do not block. Surface the fact and let the user decide.

## Per-account flags

### `correlated_long_exposure: {products}`

**Meaning:** The account is long more than one equity-index futures product at once. This includes any subset of ES, MES, NQ, MNQ, YM, MYM, RTY, M2K.

**Why it matters:** These products correlate 0.8–0.95+ intra-day. Long ES + long NQ + long RTY is essentially one large long-beta position, not three diversified trades. Daily P&L volatility is roughly additive, not diversified.

**Triage prompt:**
- "You're long {products} simultaneously — effectively one large index-beta bet. Consider whether the combined position size is what you intend."
- Optional: trigger the `correlation-hedge` skill to quantify the combined exposure in dollars-per-1%-ES-move.

### `correlated_short_exposure: {products}`

This mirrors the flag above, for shorts.

### `high_margin_utilization: {pct}%`

**Meaning:** Total used margin exceeds 80% of the account's max historical net liquidation.

**Why it matters:** This is close to auto-liquidation thresholds. A normal intraday swing could trip a liquidation.

**Triage prompt:**
- "Margin utilization is {pct}% of your max netLiq. Small price moves against you could trip auto-liquidation."
- Do not lecture. State the number and move on.

## Order-history drift outputs

These come from `stop_drift.py`, not `health.py`, but they live in the same narrative vocabulary.

### `drift_direction = "toward_entry"`

The stop moved closer to entry. It trails the position or locks in profit. This is neutral to positive. Say: "You trailed the stop from {original_stop} to {current_stop}, locking in {risk_removed_dollars}."

### `drift_direction = "away_from_entry"`

The stop moved farther from entry — this widens the risk. State the risk ratio: `current_risk_dollars` divided by `original_risk_dollars`. Say: "You widened the stop from {original_stop} to {current_stop} — adding {risk_added_dollars}, {ratio}× the original risk."

### `drift_direction = "unchanged"`

The stop stayed at its original level — nothing to report unless the user asked specifically about drift. If they did, say: "Stop is still at its original level of {stop}."

## Flags intentionally not included

- **P&L-based trips** (e.g., "hit -0.5R"). This is reactive: by the time the skill flags it, the user already lost. `distance_to_stop_pct_of_daily_budget` expresses the same idea proactively.
- **Time-in-trade warnings** ("holding too long"). Position duration is personal — a 3-hour scalp looks bad for one user and normal for another. `health.py` has no entry-timestamp field on positions, so it cannot report this at all. Leave interpretation to `risk-coach` if the user wants it from another source.
- **Behavioral patterns** (revenge trading, Monday overtrading). This is not this skill's job. `risk-coach` owns those detectors.

## When to surface flags

- Volunteer flags on the first health-dashboard call of a session.
- On follow-up questions about a specific position, only re-surface flags if they changed since the last report.
- Never echo the same flag twice in a row in the same conversation turn. Repetition annoys the user.
