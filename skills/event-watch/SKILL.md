---
name: event-watch
description: Covers a high-volatility economic event calendar — FOMC, CPI, NFP, EIA, and OPEC. Also covers earnings-season awareness and session-boundary context — globex open, NY cash open, settlement, and EIA release windows. Reports upcoming events and filters them by the user's current positions. Explains a move after it happens (for example, "ES +24pts in 8min matches the hot CPI print"). Computes historical reaction-size magnitudes from prior releases. Proposes reaction-window bracket alerts via alerts-composer. It is strictly reactive, with no timer-based push. Use when the user asks "what's coming up", "economic calendar", "why did it move", "NY cash open", or "session open". Also use when the user names a specific event — CPI, FOMC, NFP, EIA, OPEC, or earnings.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# event-watch

## Purpose

Give the user volatility-event context on demand. Three things:

1. Pre-event awareness on ask ("what's on the calendar tomorrow?")
2. Historical reaction-size context ("how much does ES usually move on CPI?")
3. Post-event attribution on ask ("why did it just spike?")

It also recognizes session boundaries: NY cash open, EIA release window, FOMC press conference.
Those drive volatility even without an explicit event.

## Environment routing

Calendars and event data only — no account binding.
A sibling skill's account resolution might already pin the session to demo (simulation) or live.
If so, stay on that same MCP server.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `economic_calendar` — upcoming releases with `date`, `eventName`, `importance` (1–5), `actual`, `consensus`, `prior`. These field names come from an external, unversioned passthrough API. Verify them against a live call — the MCP server's own schema does not guarantee them.
- `earnings_calendar` — equity-index context
- `market_history` — bar windows around past releases for reaction-size math
- `my_portfolio` — dollar exposure in current positions. Prune with `fields=["positions[].symbol","positions[].netPos","positions[].openPnL"]`.
- `market_snapshot` — gives the current price when you propose bracket alerts. Prune with `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize"]`.

**Explicitly not allowed:** third-party commercial calendar sites (investing.com, forexfactory, tradingeconomics) — TOS-restricted and redundant with data the server already exposes.

## Design constraint — strictly reactive

Phrase outputs as "you asked near X", never "X is about to happen" (that would imply a timer this skill does not have).
Proactive pushes belong on the MCP's SSE channel, not in a skill.

## Grounding rules — the calendar is the tool output, nothing else

Every event you report must appear in the `economic_calendar` payload
(after `importance_filter.py`). These rules are absolute:

- **Never add an event from memory**, even one that "should" happen this week. If it is not in the tool output, it does not go in the answer.
- **Never invent numbers.** Do not add any consensus, prior, actual, or rate level that is not in the payload. If a field does not appear in the payload, leave it out. Never estimate it.
- **Day placement is mechanical.** Place each event on the day its own `date` timestamp shows. When you convert time zones, convert each event and re-bucket its day from the converted time. Never group events by the day the market "usually" releases them.
- **Disclose partial data.** Say so if you only see or page through part of the payload. The list may be incomplete. An honest gap beats a filled one.

## Workflow

### 1. Pre-event on ask — "what's coming up?" / "what's on the calendar?"

```
economic_calendar(fromDate=<today ISO-8601>, toDate=<today+3d ISO-8601>)
my_portfolio(fields=["positions[].symbol","positions[].netPos","positions[].openPnL"])
```

Call `my_portfolio` once for each account name you already know from an earlier tool call in this session.
The tool requires an `account` argument — a call without one fails.
If you do not know an account name yet, ask the user for one before you call `my_portfolio`.
Never pass a guessed account name, like `Sim101`. The server rejects it.

**Expect an oversized result.** A multi-day calendar window often exceeds the inline tool-result cap.
When that happens, your client saves the JSON to a file and returns the path instead of the payload.
That file is the input to `importance_filter.py` — pass the saved path with `--file`.
Do not explore the file with ad-hoc `jq` queries or reassemble the calendar yourself.
The filter script is the only sanctioned reader.
Never re-type or inline a large JSON payload into the command.

```bash
python3 scripts/importance_filter.py --file <saved-tool-result-path> \
    --products ES MNQ CL --min-importance 3
```

If the response has `hasMore: true`, page with `offset` and run the filter over each page before you answer.
Otherwise, say the list covers only the first page.

`importance_filter.py` drops:
- events with `importance < --min-importance` (default 3)
- events whose name does not match a product-group keyword for the user's products (see the script's canonical map)

Output fields: `kept`, `dropped_by_importance`, `dropped_by_relevance`, `events[]` (each with `matched_product_groups`).

### 2. Reaction-size context — "how much does ES usually move on CPI?"

Gather the last N releases from `economic_calendar`.
Use a `fromDate` far enough back for about 6 releases of the same type.
CPI is monthly, so that is about 180 days.
Then, for each release, fetch a bar window around the release time via `market_history`:

```
market_history(
  symbol="ESU6",
  barType="Minute",
  barSize=5,
  from=<release - 5min, ISO-8601>,
  to=<release + 30min, ISO-8601>
)
```

Structure each release + its bars into the input format:

```json
{"events": [
  {"timestamp": "2026-01-15T13:30:00Z", "bars": [...]},
  {"timestamp": "2026-02-13T13:30:00Z", "bars": [...]},
  ...
]}
```

Save that as `events.json` and run `reaction_size.py`:

```bash
python3 scripts/reaction_size.py --file events.json --offset-minutes 5
```

Output fields:
- `samples` — events that had enough bar data
- `mean_abs_move` — avg |close(t+offset) − close(t0)|
- `mean_max_move_up` / `mean_max_move_down` — directional max
- `range_mean` / `range_max` / `range_stdev` — window range stats

All values are in raw points. Multiply by `valuePerPoint` × `|netPos|` for the dollar exposure.

**Input fixture for shape reference:** `scripts/fixtures/cpi_reactions_synthetic.json`.

### 3. Post-event attribution on ask — "why did it spike?"

Two inputs: recent price action (from `market-context` or `market_history`) + the nearest release from `economic_calendar`.
Narrate the causal link where the timestamps line up.
If no release falls within 10min, do not invent one — say "no scheduled release near the spike; could be headline-driven."

### 4. Session-boundary on ask

When the user's question falls near a high-vol boundary (NY cash open, EIA release, FOMC statement, etc.), surface the context:

> "You asked 3 min before NY cash open — expect a vol spike and
> spread-widening in the first 10 min."

The boundary table lives in `references/session-schedules.md` — load that file and pick the nearest boundary.

### 5. Alert-proposal handoff

When the user holds a position exposed to a known-risk event, propose a reaction-window bracket alert.
Then hand it to the user to submit via `alerts-composer`:

```
Propose: lastPrice(ESU6) > <entry + reaction_size> OR lastPrice(ESU6) < <entry - reaction_size>
```

Use `mean_abs_move` from `reaction_size.py` as the per-side magnitude, or bump it by 1.5× for a "meaningful surprise" threshold.
Pass this expression to `alerts-composer` — this skill does not submit alerts.

**Subjects must be unquoted.** The DSL parser rejects `lastPrice("ESU6")`.
The subject regex `[\$@]?[\w\s\-\+/|]+` excludes double-quotes: the server's rule parser accepts only unquoted subject strings.
`alerts-composer/scripts/validate.py` catches this offline before submission.

## Output idioms

- Pre-event: "CPI in 18 min (08:30 ET, consensus 0.3% m/m, prior 0.2%).
  Recent CPI releases moved ES by double-digit points within
  minutes. You're long 2 ES — run `reaction_size.py` for today's
  actual reaction range before you size a hedge or a stop. Options:
  flatten, hedge with MES short, or widen stops to 1.5× normal."
- Reaction-size report: "Recent CPI releases moved ES by
  double-digit points in the first 5 minutes, with occasional larger
  outliers. Run `reaction_size.py` over the last N releases for the
  exact average, max, and spread before you size a bracket."
- Post-event: "ES +24pts in 8min is consistent with the hotter-than-
  expected CPI (0.5% vs 0.3% consensus) released at 08:30 ET."
- Session-boundary: "NY cash open in 3 min. Expect wider spreads and
  a vol burst in the first 10 min."

## Disambiguation

- vs `market-context`: market-context is **intra-day analytics on one symbol** (VWAP, ATR, profile). event-watch is **cross-event history** ("how does ES usually move on CPI?") + calendar surfacing.
- vs `position-watchdog`: watchdog monitors one live position. If a known-risk event threatens that position, narrate with event-watch and propose a reaction-window alert.
- vs `pretrade-risk`: pretrade-risk sizes an entry. If the entry sits near a known event, flag the event-derived volatility. Do not hard-gate the trade — the user decides.
- vs `alerts-composer`: event-watch **proposes** an alert expression; alerts-composer **constructs + submits** it. One-way handoff.

## Explicit non-goals

- **No proactive warnings.** This skill has no timer. If the user does not ask, the skill does not act.
- **No third-party calendar scraping.** Only the internal `economic_calendar` / `earnings_calendar` tools.
- **No price prediction.** Reaction-size reports are historical magnitudes, not directional forecasts.
- **Not a strategy.** Whether to hedge, flatten, or hold through an event is the user's decision. This skill shows magnitude and precedent.

## Resource layout

- `scripts/importance_filter.py` — filters the `economic_calendar` payload by min importance + product-group relevance. Input via stdin.
- `scripts/reaction_size.py` — historical reaction-size math for a list of {event, bars} pairs. Input via stdin.
- `scripts/fixtures/` — synthetic samples for smoke-testing:
  - `econ_calendar_synthetic.json` — 8-event calendar for the filter
  - `cpi_reactions_synthetic.json` — 3 CPI releases with 5-min bars
- `references/session-schedules.md` — US futures market hours + a high-vol boundary table (08:30, 09:30, 10:00, 10:30, 14:00, 14:30, 16:00 ET). Load it when a question falls near a session boundary.
- `references/event-playbooks.md` — per-event narrative context (FOMC, CPI, NFP, PCE, PPI, ISM, EIA, OPEC, ECB, BOJ, earnings). Load it when you narrate the story behind one named event.
