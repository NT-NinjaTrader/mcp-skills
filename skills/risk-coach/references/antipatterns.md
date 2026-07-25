# Anti-patterns — detected by `scripts/detect.py`

Five behavioral patterns the skill watches for. Each maps to one
detector in `detect.py`. The table tells you what triggers it, what
severity means, and how to narrate the flag.

## Table of contents

1. revenge_trade
2. losing_streak
3. overtrade_count
4. size_drift
5. hour_edge

## Severity

| Level | Meaning | Skill stance |
|-------|---------|--------------|
| `low` | Worth mentioning, not acting on | One sentence aside |
| `med` | Consider pausing or reducing | Explicit suggestion, user decides |
| `high` | Strong case for stopping now | Foreground the flag. Suggest concrete action (pause, halve size, flatten) |

**This skill never blocks. It explains.** Hard limits live in
`update_risk_settings.dailyLossLimit` server-side.

---

## 1. revenge_trade

**Detector:** last closed trade was a loss AND time since close is
under `--revenge-window-min` (default 5).

**Why it matters:** entering a new trade soon after a loss is a
well-documented emotional pattern — a one-more-shot reflex, not a
reasoned setup.

**Compute the real number before you narrate one.** Pull the user's
own trades from `trade-debrief` (or `performance_summary`). Compare
their win rate on trades entered within the revenge window against
their overall win rate. Cite "your last N", per this skill's own
citation rule (see SKILL.md). Never assert a fixed industry rate.

**Narrate:**
> "You're 4 min after that -\$225 NQ loss. Your last 8 trades in this
> window won 25% vs your 55% overall rate. Options:
> (a) Wait 30 min, (b) Take half the size you planned, (c) Proceed
> eyes-open."

**Severity selection:**
- `high` — always. The pattern is well-established behaviorally, even
  before you have a user-specific number to cite.

---

## 2. losing_streak

**Detector:** last N trades were all losses. N >= `--streak-min`
(default 3).

**Why it matters:** 3+ consecutive losses at any size signals an
edge mismatch with current conditions. Either the market regime
shifted, the setup does not work today, or the trader is off-rhythm.
Continuing at full size compounds the damage.

**Narrate:**
> "Last 3 trades: -\$150, -\$100, -\$225. Total -\$475. Either the
> setup isn't clean today or the market shifted. Consider: pause
> 30 min, halve size, or step away until tomorrow."

**Severity:**
- `high` — the streak itself is the signal.

---

## 3. overtrade_count

**Detector:** today's trade count >= `--overtrade-threshold`
(default 5).

**Why it matters:** most retail futures traders have their best
sessions on 1-3 trades. Beyond 5 trades, selection quality drops.
The trader takes setups they would not take at trade 1.

**Narrate:**
> "5 trades today already. Pull up `performance_summary` — your
> trades-per-day median is 2.1; days with 5+ trades are your worst
> profit-factor quartile."

**Severity:**
- `med` when count is in `[threshold, threshold*1.5)`
- `high` when count is `>= threshold * 1.5` (e.g., 8+ on default 5)

**Tuning:** user's own baseline is better than a hardcoded threshold.
If `performance_summary` shows the user's median trades-per-day, use
`ceil(median * 2)` as the threshold.

---

## 4. size_drift

**Detector:** `proposed.qty >= median(recent qty) * factor` (default
factor 2.0).

**Why it matters:** doubling up after a loss streak is the classic
recipe for a big red day. Size-drift captures the mechanical-but-
emotional move of "I'll make it back in one."

**Narrate:**
> "Proposed 6 contracts. Your recent median is 2 — that's 3× normal.
> If the thesis is that strong, document it. If it's because of
> today's P&L, that's revenge in a larger jersey."

**Severity:**
- `med` when multiple in `[factor, factor*1.5)` — e.g., 2× for the
  default 2.0 threshold.
- `high` when multiple is `>= factor*1.5` — e.g., 3× on default.

**Edge case:** if `len(recent) < 3`, detector returns null — too
little baseline.

---

## 5. hour_edge

**Detector:** win rate at current UTC hour across `recent_trades` is
below `--hour-edge-cutoff` (default 0.40), with enough samples
(`--hour-edge-min-samples`, default 5).

**Why it matters:** many traders have strong hour-of-day edges
(e.g., NY open, London open) and anti-edges (lunch, overnight).
A trade outside edge hours does not mean it loses. It means the
statistical context is less favorable.

**Narrate:**
> "Win rate at UTC 18:00 across your last 12 trades: 33% (4W/8L).
> Baseline is 52%. Could be a rough hour for your setups."

**Severity:**
- `med` — always. Single-hour stats are too noisy for `high`.

**Edge case:** if samples < `min_samples`, detector returns null
(silent). This skill does NOT flag low-confidence hour stats.

---

## Patterns NOT captured today

- **Averaging into a loser** (buying more as a long position moves
  against you). This would need position-state history per fill. The
  MCP `fill_history` gives fills, but correlating them to position
  state in flight is a bigger job. Delegate to `scale-manager`'s
  `scale_in` call + check `R_after < 0` as a proxy signal.
- **Ignoring your stop** (manually moving it further away as price
  approaches). A detector here needs order-modification history. The
  MCP gives `order_history`, but this skill does not correlate that
  history to bracket-leg stop-price changes. Use `position-watchdog`'s
  `stop_drift.py` instead — it detects stop drift on a live position.
  When the user asks about stop drift, route them to that skill.
- **Time-off-the-bell FOMO** (first 5 min of session). Heuristic:
  detect if the user's first-5-min trades underperform. Needs
  calendar awareness + baseline.
- **Fighting a trend** (opening a short in `market-context.market_structure
  = trend_up`). This requires market-context integration per trade.
  This is easy to add. SKILL.md calls it out as "check context first".

When any of these come up in conversation, narrate without a
scripted detector — the coach-not-cop posture supports prose-only
signals.
