---
name: position-watchdog
description: Reports the live health of open futures positions. Output covers open P&L in dollars and R, and distance to stop (ticks, dollars, % of the daily loss budget). It also covers R-achieved to target, time in trade, and margin utilization. It also lists guardrail flags (no stop attached, a stop moved against entry, correlated index exposure). It also gives informational what-if math — move stop, extend target, go breakeven. It also detects stop drift from order history. A trailed stop means less risk. A widened stop means more risk. Use when the user asks "how am I doing", "what's my P&L", "how much am I up", "am I up or down", "position health", "my positions", "where's my stop", or "how close to stop". Also use when the user asks "am I in trouble", "daily loss", "margin usage", "am I safe", "what if I move my stop to X", "what if I extend target", "should I go breakeven", or "has my stop been moved". For closed-position analysis use trade-replay. For exact order payloads to execute, use scale-manager.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# position-watchdog

## Purpose

Report the live health of the user's open futures positions.
Cover how much room they have before the stop trips and how far the target is.
Cover whether their plan drifted.
Also report whether their exposure is a single concentrated bet across correlated index products.
Never emit order payloads. That is `scale-manager`'s job.

## Safety gate

This skill reads only.
It calls no tool that changes an account, an order, or an alert.
It never calls `place_order`, `modify_order`, `close_position`, or `create_alert`.
Every number and every proposal here is text for the user to read.
The user approves any change, and a sibling skill composes it.

## Environment routing

Demo (simulation) and live are two separate MCP servers.
Account names are unique to one server.
Once a workflow resolves an account on a server, every downstream call must go through that same server.
This includes `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, history tools, etc.
Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `my_portfolio` — current positions, open P&L, used margin. Prune with `fields=["account.netLiq","account.dailyLoss","account.openPnL","positions[]","workingOrders[]"]`.
- `market_snapshot` — last price, tickSize, valuePerPoint for every symbol with an open position. Prune with `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize","snapshots[].valuePerPoint","snapshots[].bidPrice","snapshots[].askPrice"]`.
- `order_history` — order events for a symbol, used by stop-drift detection. Reports only the current stop price, not prior versions.
- `risk_settings` — daily loss limit, max netLiq.

## Workflow

### 1. Pull the state

Call these tools in any order (or in parallel):

- `my_portfolio` — current positions, open P&L, used margin, and working orders (the source of bracket stop/target prices). Prune with `fields=["account.netLiq","account.dailyLoss","account.openPnL","positions[]","workingOrders[]"]` — this skips balance/subscription detail the dashboard does not read.
- `market_snapshot` — last price, tickSize, valuePerPoint for every symbol with an open position. Prune with `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize","snapshots[].valuePerPoint","snapshots[].bidPrice","snapshots[].askPrice"]`.
- `risk_settings` — daily loss limit, max netLiq

Save each response to a temp file. The scripts take file paths.

### 2. Compute the dashboard

```bash
python3 scripts/health.py \
    --portfolio portfolio.json \
    --snapshot snapshot.json \
    --risk-settings risk.json
```

Output has two parts:

- `positions[]` — per-position health (distance to stop, R-multiple, per-position flags)
- `account_flags[]` — account-wide flags (correlated exposure, high margin utilization)

See `references/guardrails.md` for the flag taxonomy and triage templates.

### 3. Live what-if (on ask)

When the user asks "what if I moved my stop to X?" or "what if I went breakeven?", feed one position's JSON to `whatif_live.py`.
Save the relevant `positions[]` entry from `health.py`'s output to a file, and pass its path with `--file`.
Never re-type or inline a large JSON payload into the command (stdin still works as a fallback):

```bash
# Move stop to 7148
python3 scripts/whatif_live.py --file position.json --new-stop 7148

# Go breakeven
python3 scripts/whatif_live.py --file position.json --breakeven

# Extend target to 7170
python3 scripts/whatif_live.py --file position.json --new-target 7170
```

The script reports the new risk dollars and the new R-multiple, relative to the *original* risk as the denominator.
For breakeven, it also reports how much risk the move removes from the current stop position.

**This script is informational.** It never emits `modify_order` payloads.
If the user decides they actually want to move the stop, hand off to `scale-manager`.

### 4. Stop-drift detection (on ask)

When the user asks "has my stop been moved?", or you want to check before you narrate, pull the symbol's order history and run:

```bash
python3 scripts/stop_drift.py \
    --orders order_history.json \
    --symbol ESU6 \
    --original-stop 7145 \
    --entry-price 7150 --direction long \
    --tick-size 0.25 --value-per-point 50 --net-pos 4
```

`order_history` reports only the current stop price, not its prior versions.
Pass the stop price you know from bracket placement as `--original-stop`.
Without it, the script reports the current stop only and skips the drift comparison.

Output classifies drift as `toward_entry` (trailing, less risk), `away_from_entry` (widening, more risk — a behavioral red flag), or `unchanged`.
With `--value-per-point` and `--net-pos`, the output includes the exact dollar amount of risk added or removed.

### 5. Alert-proposal hook (on ask)

**This skill never calls `create_alert`.**
Emit the alert expression as a string, then hand off to `alerts-composer`.
That skill composes the alert, and the user approves the submission there.

When the user wants an alert on a current position, propose an expression that uses the position's own levels.
Examples:

- Stop is 7148 → propose `lastPrice(ESU6) < 7148.75` (3 ticks before the stop — a heads-up before the trip)
- Position has no stop → propose `posOpenPLUsd(ESU6) < -300` (a hard PnL floor)

**Subjects must stay unquoted.** The DSL parser rejects `lastPrice("ESU6")`.
The subject regex `[\$@]?[\w\s\-\+/|]+` excludes double-quotes: the server's rule parser accepts only unquoted subject strings.
Submission via `create_alert` fails with `errorText`, not silently.
`alerts-composer/scripts/validate.py` catches it offline, so always run the proposed expression through `validate.py` before you hand it off.

Emit the expression as a string. Never call `create_alert` from this skill.

## Output idioms

Use `references/guardrails.md` narrative templates. Lead with dollars, then follow with R-multiples and ticks.
A typical "how am I doing?" reply:

> "Long 4 ES at 7150, mark 7158 (+$1,650, +4.1R). Stop 7148 is 41 ticks
> below — $2,050 at risk, 410% of daily budget — consider trimming or
> tightening if the trade isn't moving.  
> Also long 1 NQ at 18250 without a stop attached ⚠ — the market can
> gap through any price. Want a stop?  
> Account-level: ES + NQ long is one index-beta bet; combined 1% ES
> move ≈ $2,240 swing."

## Disambiguation

- vs `risk-coach`: watchdog reports **live numbers**; coach judges **plan quality** ("are you tilting?", "is this idea well-shaped?"). These are different scopes.
- vs `scale-manager`: watchdog's what-if is **informational** ("risk becomes Y"); scale-manager converts intent into exact `modify_order`/`place_order` payloads.
- vs `trade-replay`: watchdog covers **live open positions**; replay covers **closed positions** with bar-level MFE/MAE.
- vs `pretrade-risk`: pretrade-risk sizes a new entry; watchdog runs *after* the position is live.

## Not computed: live MFE/MAE

This skill does not report MFE or MAE for a live position.
It also does not compare either one against a historical median.
Excursion math needs a `market_history` bar window per position, which costs one extra tool call per symbol.
The dashboard stays fast instead.
`trade-replay` covers the same excursion math for closed trades.
A future enhancement adds `health.py --market-history PATH` per position, for users who explicitly want live excursion data.
Until then, `open_pl_dollars` is the available live P&L signal.

## Resource layout

- `scripts/health.py` — distance/R/margin/flags dashboard (portfolio, snapshot, and risk-settings inputs required; fast, no market_history)
- `scripts/whatif_live.py` — informational alternate-exit math for one position (input: position dict; arg: one of --new-stop/--new-target/--breakeven)
- `scripts/stop_drift.py` — diffs the current bracket stop against a caller-known original, from order history
- `references/guardrails.md` — flag taxonomy with triage templates — load when you narrate flags or explain what a flag means
