---
name: trade-debrief
description: Educational review of past trading sessions. This skill combines timeline_report, performance_summary, fill_history, position_history, and market_history into a structured report. It then routes the report through 7 prompt templates. These are mistake identification, pattern extraction, trade scoring, correction rules, daily debrief, pattern clustering, and expectancy analysis. Every output cites the report fields directly and leads with the dollar impact. This skill describes the user's own past trading patterns. It labels any proposed change as a hypothesis, not advice. Use it for "debrief", "analyze trading", "what mistakes did I make", "what went wrong", "find patterns in trades", "score a trade", "review today's session", "coaching", "improvement rules", "what should I change", or "was that a good trade". For plain "how did I trade today" summaries, or for descriptive TCA, use trade-journal. For single-trade counterfactuals, use trade-replay.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# trade-debrief

## Purpose

Synthesize session data into a coaching-grade debrief with the bundled prompt library. Descriptive TCA lives in `trade-journal`. This skill is prescriptive. It surfaces mistakes and patterns, and proposes rules and measurable improvements.

## Environment routing

Demo (simulation) and live are two separate MCP servers. Account names are unique to one server. Once a workflow resolves an account on a server, every downstream call must go through that same server. This includes `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, history tools, etc. Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them. Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `timeline_report` — per-session event timeline
  (single tool post-consolidation: `account`, `date`, optional `endDate`
  for a range)
- `performance_summary` — arrays of `{name, value}` stat pairs under
  `extra.allTradeStats[]` / `extra.profitTradeStats[]` /
  `extra.lossTradeStats[]` (e.g. `{name: "Total P/L", value: "$765.00"}`),
  plus `extra.tradeLog[]` and `extra.hasTrades`
- `fill_history` — fill-level timestamps
- `position_history` — closed-position summaries
- `market_history` — bar OHLC for MFE/MAE
- `search_contracts` — contract metadata
  (`productName`, `tickSize`, `valuePerPoint`)
- `economic_calendar` — event context (via
  `event-watch` skill, not this one directly)
- `user_profile` — discover available account names when the account
  is unknown

## Skills consumed

- `trade-journal`'s `streaks.py` — FIFO round-trip pairing over
  `fill_history`, to produce the `trades[]` list. Reuse it. Do not
  duplicate it.
- `market-context` — session VWAP, ATR, and regime narrative per
  symbol, for the `market_context` block of each trade.

## Workflow

### 1. Classify the intent → pick the prompt

`references/prompt-selection.md` has the full routing table. Rough mapping:

| Intent | Prompt |
|--------|--------|
| Quick wrap of today | `07_daily_debrief` |
| "What mistakes" | `01_mistake_identification` |
| "Find patterns" | `02_pattern_extraction` |
| "Score my trades" | `03_trade_scoring` |
| "What rules" | `06_correction_rules` |
| Cross-day clustering | `08_pattern_clustering` |
| Edge / expectancy | `09_expectancy_analysis` |

### 2. Gather MCP inputs (in parallel)

**Account resolution.** All MCP calls below require `account=<name>`. If the account name is unknown, call `user_profile()` first. Its `accounts[].name` field lists every account on this MCP server.

```
timeline_report(account=..., date=<YYYY-MM-DD>, endDate=<YYYY-MM-DD>)
performance_summary(account=..., startDate=<YYYY-MM-DD>, endDate=<YYYY-MM-DD>)
fill_history(account=..., startDate=<YYYY-MM-DD>, endDate=<YYYY-MM-DD>)
position_history(account=..., startDate=<YYYY-MM-DD>, endDate=<YYYY-MM-DD>)
search_contracts(text=<each symbol>, includeFamilySiblings=false)
```

Date params are date-level. They use `YYYY-MM-DD` or a natural term like `"last week"`, never a timestamp.

Then for each trade, fetch a bar window around its lifetime:

```
market_history(symbol=<sym>, barType="Minute",
  barSize=1, from=<entry_ts - 1min>, to=<exit_ts + 1min>)
```

(`from` and `to` are full ISO-8601 timestamps. `from` requires `to`.)

Keep per-trade bar fetches bounded. Unless the user asks for per-minute pattern analysis, do not fetch 1-min bars for a full day (expensive).

### 3. Pair fills into trades

Run `trade-journal`'s `streaks.py` over the fill list. Use its output round-trips as the trade list. Attach each trade's corresponding bar window to it.

### 4. Compute derived metrics

Save the trades-with-bars payload to a file. Pass its path with `--file`. Never re-type or inline a large JSON payload in the command.

```bash
python3 scripts/compute_derived.py --file trades_with_bars.json
```

Per trade, it produces `realized_points/dollars/R`, `mfe_points/dollars/R`, `mae_points/dollars/R`, `giveback_from_mfe_pct`, and `realized_vs_mfe_pct`.

Some fields are always null: `scale_out_count`, `stop_modified_count`, and minute-by-minute timeline volume features. The MCP cannot source them. See `references/report-schema.md` for the full provenance map.

### 5. Assemble the report YAML

```bash
python3 scripts/assemble_report.py --file combined_input.json
```

It takes `account_id`, `trade_date`, `timeline_report`, `performance_summary`, `trades` (post-`compute_derived`), a `contracts` map, and an optional `market_context` map. It emits the YAML shape that the prompts expect. See `references/report-schema.md` for details.

### 6. Run the prompt (internally — Claude IS the LLM)

1. Read the chosen prompt file (e.g., `references/prompts/07_daily_debrief.md`).
2. Append the assembled YAML below the prompt's final `## Trade Timeline
   Report` header.
3. Follow the prompt's STRICT RULES. These require fact-only content,
   YAML-path citations, and the mode-specific output structure.
4. When a rule says "cite exact YAML path", cite only fields that
   have a value, not fields that are null. `references/report-schema.md`
   lists which fields are null today.

**Do not** route this through an external LLM API. Claude Code IS the LLM. Just read the prompt and apply its constraints.

### 7. Echo a summary + point at the raw report

End with a 1-line pointer: "Full assembled report YAML available on request; source tools: `timeline_report`, `performance_summary`, `fill_history`, `market_history`, `search_contracts`." This gives the user transparency about where the numbers came from.

## Output constraints (from the prompt library)

- **Fact-only with citations.** Every claim references a YAML path.
  No speculation.
- **Dollar-first, R-second.** Lead with "$875 left on the table",
  then "0.7R giveback" for context.
- **Hypotheses, labeled explicitly.** If a claim needs data the
  report does not have yet, mark it "hypothesis" and state the
  evidence it needs.
- **No invented indicators.** Only use fields present in the
  assembled report. Volume and POC features are null today. Do not
  cite them.

## Output idioms

Prompt 07 example (daily_debrief), roughly 200 words:

> **Performance Summary**
> Net +$765 / +1.2R across 2 trades on the E-Mini S&P 500 and
> E-Mini NASDAQ-100 (`summary.total_pnl_dollars = 765.00`). Win rate
> 100% (2 of 2), but MFE capture lagged on both.
>
> **Primary Pattern**
> Systematic MFE giveback. ES gave back 47.5% from peak
> (`trades[0].derived.giveback_from_mfe_pct = 47.5`); NQ gave back 40%
> (`trades[1].derived.giveback_from_mfe_pct = 40.0`). Combined $600
> left on the table from peak.
>
> **Top 3 Improvements**
> 1. **Rule:** `IF mfe_R >= 2.0 THEN scale_out_50pct`
>    - **Evidence:** `trades[0].mfe_R = 2.5`; exit at 1.3R (realized
>      = $525, peak = $1,000, giveback = $475)
>    - **Expected impact:** +$475 / +1.2R improvement on ES
> 2. **Rule:** `IF mfe_R >= 0.5 AND time_in_trade > 10min THEN move_stop_to_breakeven`
>    - **Trades affected:** both
> 3. (Hypothesis; needs scale-out action data not yet in report.)

## Disambiguation

- **vs `trade-journal`**: journal reports descriptive TCA and
  streaks — what happened. Debrief mines prescriptive rules — what
  to change.
- **vs `trade-replay`**: replay does one trade's deep dive, with
  counterfactual exits. Debrief synthesizes cross-trade patterns at
  the session level.
- **vs `risk-coach`**: coach handles live behavior, such as tilt,
  revenge trading, and overtrading. Debrief handles retrospective
  mechanics, such as giveback, scale discipline, and stop hygiene.
- **vs `market-context`**: debrief consumes it as input for the
  `market_context` block of each trade. It is not a substitute for
  debrief.

## Explicit non-goals

- **No external LLM round-trip.** Claude Code IS the LLM.
- **No modification of the bundled prompts.** This skill uses them
  verbatim.
- **No fabricated fields.** `timeline[n].participation_rate_vs_session`,
  `poc_shift`, `scale_out_count`, and `stop_modified_count` are null
  today. Do not guess their values.
- **No daily auto-push.** This is a reactive skill. It runs only
  when the user asks.

## Resource layout

- `scripts/compute_derived.py` — per-trade MFE/MAE + giveback metrics
  from bar scans. Shared pattern with `trade-replay`.
- `scripts/assemble_report.py` — combines compute-derived trades +
  contracts + performance summary + market context → the assembled
  report YAML.
- `scripts/fixtures/trades_with_bars_synthetic.json` — 2-trade
  multi-symbol fixture (ES long winner, NQ short winner with
  significant MFE giveback) for smoke tests.
- `references/prompts/` — 7 prompt template files:
  `01_mistake_identification.md`, `02_pattern_extraction.md`,
  `03_trade_scoring.md`, `06_correction_rules.md`, `07_daily_debrief.md`,
  `08_pattern_clustering.md`, `09_expectancy_analysis.md`. Load only
  the one file that matches the chosen prompt.
- `references/prompt-selection.md` — intent-to-prompt routing +
  combinations + how-to-run inside Claude Code. Load it when you
  classify the intent and choose a prompt.
- `references/report-schema.md` — field provenance map (MCP-sourced
  vs derived vs null-today), per-trade block reference, summary
  block reference. Load it when you check which fields the chosen
  prompt needs.
