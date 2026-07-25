---
name: risk-coach
description: Advisory behavioral-context check on recent fill history. Flags revenge-trading (new entry soon after a losing exit). Plus consecutive-loss streaks, overtrading counts, size drift against the user's own recent median, and hour-of-day anti-edges. Does not evaluate whether a trade is good, right, or profitable — only surfaces behavioral context from recent activity. Never blocks. Always explains. The user decides. Hard limits live server-side, and update_risk_settings configures them. Use when the user asks "am I on tilt", "should I take this", "is this a good trade" (skill responds with behavioral context, not a yes/no recommendation), "is this a good setup", "worth taking", or "is this revenge". Also use when the user says "talk me out of this", or asks "is this my 4th trade today", "does this size feel right", "sanity check", or "check me". For retrospective rule-mining use trade-debrief. For descriptive streak/hold-time stats use trade-journal.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# risk-coach

## Purpose

Coach, not cop. Review a proposed or current trade against common-
sense risk hygiene and the user's own behavioral history. Flags,
explains, leaves the decision to the user.

## Environment routing

Demo (simulation) and live are two separate MCP servers. Account names are
unique to one server. Once the workflow resolves an account on a
server, every downstream call — `my_portfolio`, `market_snapshot`,
`place_order`, `create_alert`, history tools, etc. — must go through
that same server. Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `fill_history` — recent fills for pairing
  into round-trip trades.
- `performance_summary` — user's baseline win
  rate / profit factor / trades-per-day
- `my_portfolio` — correlated-exposure check.
  Prune with `fields=["positions[].symbol","positions[].netPos"]` — the
  detector only needs the symbol list + sign, not P&L or margin.
- `risk_settings` — daily loss limit context
  (display only — this skill does not modify it)
- `user_profile` — discover available account names when the account
  is unknown

## Skills consumed

- `trade-journal`'s `streaks.py` — produces the `recent_trades[]`
  input for `detect.py` (FIFO round-trip pairing)
- `pretrade-risk` output — size + R:R + budget flags
- `position-watchdog` output — if the user already has a position open

## Workflow

### 1. Identify the question

| User phrasing | Skill stance |
|---------------|--------------|
| "Am I on tilt?" | Run full checklist + all detectors |
| "Should I take this?" | Checklist + detectors with `proposed` trade |
| "Is this revenge?" | Run `detect.py`, surface `revenge_trade` flag |
| "Is this my Nth trade today?" | Read summary.trades_today from detect output |
| "Size feel right?" | Run `detect.py` with `proposed.qty`, surface `size_drift` |
| "Talk me out of this" | Full run + lean harder on negatives |

### 2. Gather recent trades

**Account resolution.** `<acct>` below must come from conversation
context or `user_profile().accounts[].name`. The MCP requires
`account=` and fails without it.

```
fill_history(
  account=<acct>,
  startDate="last 7 days",
  endDate="today",
)
```

(`startDate`/`endDate` accept `YYYY-MM-DD` or natural terms.)

Run `trade-journal`'s `streaks.py` on the `fill_history` result to get
round-trip pairs. Save the tool result to a file. Pass its path with
`--file`. Never re-type or inline a large JSON payload in the command.

```bash
python3 ../trade-journal/scripts/streaks.py --file fill_history.json \
    --value-per-point-map ES:50 MES:5 NQ:20 MNQ:2
```

Take the trades-list from that output (each has `pnl_usd`,
`entry_time`, `exit_time`, `symbol`, `qty`).

### 3. Run the detectors

```bash
python3 scripts/detect.py --file detect_input.json
```

Input shape:

```json
{
  "now_iso": "<current ISO>",
  "proposed": {"symbol": "ESU6", "qty": 4, "direction": "long"},
  "recent_trades": [... paired trades ...]
}
```

Output: list of flags + session summary. See
`references/antipatterns.md` for the 5 flags and how to narrate
each. All detectors return null silently when inputs are
insufficient — no flag means "nothing to say", not "all clear".

### 4. Load the checklist (when user asked "should I take this")

Read `references/checklist.yml` — 8 items ranging from
"thesis stated?" to "are we past 50% of daily loss budget?". Walk
through each, combining:
- `conversation` items — ask the user directly
- `pretrade-risk.output` items — already computed
- `detect.py` items — already in flags
- `my_portfolio` items — pull fresh

### 5. Narrate

Combine checklist findings + detector flags into one short
narrative. Lead with the HIGH severity flags. Suggest concrete
actions: pause, halve size, skip this one, proceed with eyes
open. **Never tell the user to stop.** Hard limits are server-side.
The user configures them through `update_risk_settings`. The user's
account already enforces its configured limits.

## Tone and degree of freedom

- **Coach, not cop.** "Here's what the data says" — not "you shouldn't".
- **High freedom on narration.** Judgment, not arithmetic — let
  Claude compose the prose.
- **Low freedom on detectors.** `detect.py` uses fixed thresholds
  (tunable via flags) so the signal is consistent. False negatives
  matter more than false positives here — better to miss a borderline
  flag than to cry wolf.

## Output idioms

**Multi-flag session (common when user asks on a red day):**

> "Three signals I'd want you to see before pulling the trigger:
>
> 1. **Revenge window** — you're 4 min after a -\$225 loss. Strong
>    stats against taking the next one.
> 2. **Losing streak** — last 3 all red (-\$475 total). Either the
>    regime shifted or the setups aren't clean today.
> 3. **Size drift** — proposed 6 vs recent median 2 — 3× normal.
>
> Options: (a) Step away 30 min, (b) Cut to 2 contracts and keep
> your stop at normal distance, (c) Skip today, document what the
> last 3 had in common.
>
> Your daily P&L is -\$295 — 59% of the \$500 budget. One more
> -1R trade at 6 contracts (\$900 risk) would blow the limit."

**Clean session:**

> "No flags. Last 3 trades 2W/1L (+\$220 net), proposed size matches
> your median, 10 min since last close. Your UTC-15 hour has 54%
> win rate over 21 samples — within range. Thesis check: what's the
> setup?"

**Single-flag (subtle):**

> "One thing: UTC 18:00 hour has been rough for you — 33% win rate
> on 12 trades. Nothing structural about that, could be noise, but
> worth being a touch tighter than usual today."

## Disambiguation

- **vs `pretrade-risk`**: pretrade sizes the trade (numbers). Coach
  judges whether the sized plan is right for this user, right now
  (behavior). Run pretrade first. Pipe its output into coach.
- **vs `position-watchdog`**: watchdog reports live P&L/R/distance.
  Coach asks whether to keep trading at all. If the watchdog flags
  a red streak and the user asks "should I add?", route to coach.
- **vs `trade-debrief`**: debrief is retrospective, whole-session,
  LLM-prompt-driven rule mining. Coach is in-the-moment, deterministic
  detector-driven, pre-trade advisory. Different temporal surface.
- **vs `scale-manager`**: scale-manager does the math on an adjustment
  the user wants to make. Coach asks whether making the adjustment
  right now is wise. For a pyramid-into-a-red-day proposal, run
  both — coach flags the behavior, scale-manager computes the risk.

## Explicit non-goals

- **No blocking.** Advisory only. `update_risk_settings` is available
  for self-imposed hard limits.
- **No prediction.** "Will this trade win?" is not a question this
  skill answers. Flags are historical pattern matches, not forecasts.
- **No pattern-detection on hypothetical trades.** If the user has not
  actually proposed a trade (no `proposed` in the input), `size_drift`
  returns null. Do not invent a proposal.
- **No cross-user baselines.** User's own history is the reference.
  Do not cite "most traders" — cite "your last N".

## Resource layout

- `scripts/detect.py` — 5 behavioral detectors (revenge_trade,
  losing_streak, overtrade_count, size_drift, hour_edge). Stdin JSON:
  `now_iso`, optional `proposed`, `recent_trades[]`. Thresholds all
  tunable via CLI flags. Returns flags[] + session summary.
- `scripts/fixtures/session_synthetic.json` — 7-trade 2-day sample
  designed to trigger 3 flags (revenge + streak + size_drift) while
  keeping overtrade and hour_edge silent.
- `references/checklist.yml` — 8-item pre-trade checklist with
  source mapping (conversation vs pretrade-risk vs detect output
  vs my_portfolio). Load it when the user asks "should I take this".
- `references/antipatterns.md` — the 5 detectors explained with
  narration templates, severity rules, and the patterns that are
  intentionally NOT captured (averaging into a loser, stop-drift,
  first-5-min FOMO, trend-fighting). Load it when you narrate a
  detector flag.
