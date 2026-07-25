---
name: scale-manager
description: Scales into or out of an existing futures position. Actions include add to winner (pyramid), take partial at 1R, and move stop to breakeven. Actions also include trail stop, close on reversal, and ladder an entry across a price band. Computes weighted cost basis, before/after dollar risk, R-multiples, and P&L impact. Proposes the exact modify_order / place_order / close_position payloads for the user to approve. Never executes. Use when the user asks to "scale out", "scale in", "take partial", "add to winner", "pyramid", "trim", "add more", "move stop to breakeven", "trail stop", "ladder entry", "split the order", or "close half". For INITIAL entry sizing use pretrade-risk; for live-position monitoring use position-watchdog.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# scale-manager

## Purpose

Turn "take partial off here" / "add on this break" / "trail the stop" into correct math and approved order payloads.
This skill is a sibling to `pretrade-risk` (which handles the initial entry) and `position-watchdog` (which monitors a live position).
This skill owns all in-flight position adjustments.

## Environment routing

Demo (simulation) and live are two separate MCP servers.
Account names are unique to one server.
Once a workflow resolves an account on a server, every downstream call must go through that same server.
This includes `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, history tools, etc.
Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `my_portfolio` — current `netPos`, `netPrice`, and working orders (the source of bracket stop/target prices). Prune with `fields=["positions[].symbol","positions[].netPos","positions[].netPrice","workingOrders[]"]`.
- `order_details` — event/fill history for one known `orderId`.
- `market_snapshot` — `lastPrice`, `tickSize`, `valuePerPoint`. Prune with `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize","snapshots[].valuePerPoint"]`.
- `estimate_order` — final feasibility gate for scale-ins (the server's pre-trade risk check)
- `risk_settings` — daily-loss budget, for the cross-check in Step 4
- Final execution paths (user approves): `modify_order`, `place_order`, `close_position`

## Skills consumed

- `market-context` — ATR for band spacing, regime for pyramid-eligibility
- `pretrade-risk` — pending-qty rule for scale-ins (included-in-estimate)

## Workflow

### 1. Classify the intent

| User phrasing | Action |
|---------------|--------|
| "take partial", "trim 50%", "half off" | `scale_math.py --action partial_exit --pct 0.5` |
| "scale out", "close 2 of 4" | `scale_math.py --action scale_out` |
| "add to winner", "pyramid", "add more" | `scale_math.py --action scale_in` |
| "move stop to breakeven" | modify_order on bracket stop leg |
| "trail stop to X" | modify_order on bracket stop leg |
| "ladder into 3 at 7148–7142" | `ladder.py --mode even` |

The full pattern library, with preconditions and narrations, lives in `references/scale-patterns.md`.

### 2. Gather current state

```
my_portfolio           # netPos, netPrice, workingOrders[] (bracket stop/target prices)
market_snapshot(...)   # lastPrice, tickSize, valuePerPoint
```

If `netPos == 0` and the action is scale_in/out, defer to `pretrade-risk`. This is an initial entry, not a scale.

### 3. Compute the scale math

Save the script's JSON input to a file and pass its path with `--file`.
Never re-type or inline a large JSON payload into the command.

**For scale-in / scale-out / partial-exit:**

```bash
python3 scripts/scale_math.py --file position_state.json --action <scale_in|scale_out|partial_exit>
```

The caller maps input fields from the MCP response's camelCase into the script's own JSON contract.
Fields: `direction`, `current_qty`, `current_basis`, `stop_price`, `current_mark` (from `lastPrice`), `value_per_point` (from `valuePerPoint`), `tick_size` (from `tickSize`), plus `action_qty` and `action_price` (or `--pct` for partial_exit).

Output fields:
- `basis_after` — new weighted cost basis (scale_in only; scale_out leaves the basis unchanged on the remainder)
- `dollar_risk_before_action` / `dollar_risk_after_action` — critical for scale-in. A scale-in typically RAISES dollar risk, because the combined qty × (new_basis − stop) exceeds the original risk.
- `R_before` / `R_after` at the current mark
- `realized_dollars` — money booked on a scale_out (0 for scale_in)

**For ladder entry:**

```bash
python3 scripts/ladder.py --file anchor_state.json --mode <even|atr|custom> --legs N ...
```

Returns per-leg price + qty + weight, combined weighted basis, and best/worst-case fill scenarios.

### 4. Surface the dollar and R impact to the user

Three must-haves in the narration:
1. **Dollar realized** (for exits) or **dollar risk change** (for adds).
2. **R before vs after** — did the trade get easier or harder to manage?
3. **Compliance with the daily-loss budget** (cross-check against `risk_settings.dailyLossAutoLiq` for scale-ins that expand risk).

### 5. Build the MCP payload (for user approval)

**Never call `modify_order`, `place_order`, or `close_position` from this skill.**
This step writes payload text only.
Show the plan and the exact payloads, then wait for user approval.
The user submits every call in this step.
So every block below describes the user's approved sequence, not an action this skill takes.

See `references/scale-patterns.md` § "Converting output to MCP payloads".

**Scale out — `close_position` always closes the full position, with no `quantity` parameter.**
A partial exit needs a separate market order for the offset quantity.
It also needs a resize of BOTH remaining bracket legs to match — never the target leg alone.
The server does not link the exit order and the two bracket legs together.
A stop that keeps the ORIGINAL quantity over-protects the smaller remaining position.
Worse, a same-quantity stop can flip the trade to the opposite side if it fills.
Example: close 2 of a long 4, and leave a same-quantity Sell Stop for 4.
If that stop triggers, the trader now holds a short 2, not a flat position.
A same-quantity target carries the mirror risk — a full fill flips the position too.

```
place_order(action=<opposing side>, orderType=Market, quantity=<off_qty>, symbol=<sym>, timeInForce=<Day|GTC|IOC|FOK|GTD>)
```

The user waits for the exit fill to confirm.
The user then pulls `my_portfolio` again, and checks the new `netPos` against `remaining_qty`.
The plan needs both leg IDs from `workingOrders[]` (see the "Stop move" step below for the filter).
When the server sets `bracket.parentId` or `bracket.ocoId`, use it to confirm the pair.

```
modify_order(orderId=<bracket_stop_leg_id>, quantity=<remaining_qty>)
modify_order(orderId=<bracket_target_leg_id>, quantity=<remaining_qty>)
```

`remaining_qty` is the current `quantity` on either leg minus `off_qty`.

**If a resize call fails, or the caller skips it, the position now carries a mis-sized leg.**
Do not treat the scale as done in that case.
Tell the user which leg still carries the ORIGINAL quantity.
Propose the resize again first, before any other change to the position.

**Scale in — the `place_order` payload for the add:**

```
place_order(
  action=<Buy|Sell>,                       # same side as current direction
  orderType=<Market|Limit>,
  quantity=<add_qty>,
  price=<add_price>,                       # for Limit
  symbol=<sym>,
  timeInForce=<Day|GTC|IOC|FOK|GTD>,
)
```

For limit scale-ins, consider the pending-qty rule.
The server-side `pre-trade risk check` includes all open, filled, and pending qty when it rates the order.
If you chain multiple scale-ins as limits, the SECOND order's feasibility check includes the FIRST's pending qty.
See `pretrade-risk/references/risk-rules.md` for details.

**Stop move (breakeven / trail):**

```
modify_order(orderId=<bracket_stop_leg_id>, stopPrice=<new>)
```

Find the stop leg id in `my_portfolio`'s `workingOrders[]` — filter by `symbol`, an opposing `action`, and `orderType: Stop|StopLimit`.
Find the target leg the same way, with `orderType: Limit` and `price` set instead of `stopPrice`.
When `bracket.parentId` or `bracket.ocoId` is present, use it to confirm the two legs share one entry.
The scale-out resize above needs both leg IDs — reuse this same filter for that step.

**`modify_order.stopPrice` is an absolute price**, in contract-native units — the same convention as `scale_math.py`'s output.
This is **asymmetric** with `place_order.brackets[].stopLoss`, which is a signed delta from entry (see `pretrade-risk/SKILL.md` §4a).
Pass the new absolute stop price straight through. Do **not** convert it to an offset.

**No server-side pre-flight exists for `modify_order`** — `estimate_order` covers new orders only; it takes no `orderId` parameter.
So validate the proposed stop yourself, before you show the payload:

- **Long position:** the new stop must sit below the current mark. It must also stay on the safe side of any breakeven cross. A breakeven move that lands at or just past entry is fine. A trail that crosses through the current mark flattens the market position.
- **Short position:** mirror this — the new stop must sit above the current mark.

Wrong-side stops trigger immediately on submission with no warning.

**Ladder entry — one order per leg:**

After approval, the user runs one pre-flight and one order per leg:

```
for leg in legs:
  # Pre-flight each leg — the server's pre-trade risk check counts
  # already-pending working orders from prior legs in this loop.
  estimate_order(
    account=acct, symbol=sym, action=..., quantity=leg.qty,
    orderType=Limit, price=leg.price
  )
  place_order(
    action=..., orderType=Limit, quantity=leg.qty, price=leg.price,
    timeInForce=<Day|GTC|IOC|FOK|GTD>,
  )
```

Each placed leg becomes pending qty for the next leg's pre-trade check.
See `pretrade-risk/references/risk-rules.md` § pending-qty rule.
**A scale-in with its own bracket follows the offset rule from `pretrade-risk/SKILL.md` §4a** — `place_order.brackets[].profitTarget` and `.stopLoss` carry a sign. They are deltas, not absolute prices.

### 6. Final feasibility check

For any scale-in that expands qty (a single add **or each ladder leg**), end with `estimate_order` on the proposed payload.
It surfaces the authoritative pre-trade risk check result.
If `feasible: false`, report the reason and do not submit.

**`estimate_order` does NOT cover `modify_order`.**
The LLM must sanity-check stop-move proposals against the side-of-current-mark rule in Step 5's "Stop move" subsection. There is no server-side dry-run for modifies.

### 7. Emit the plan and payloads; wait for user approval

This restates the gate at the top of Step 5.
Never call `modify_order`, `place_order`, or `close_position` from this skill.
Always show the plan and the exact payloads, then stop.
The user submits the approved calls.

## Output idioms

**Classic partial at 1R:**

> "Long 4 ES @ 7150, mark 7168 (2R). Propose: close 2 at market —
> realizes \$1,800, leaves 2 at the same stop price 7141 (\$900 at risk).
> After the fill confirms, resize BOTH remaining legs to quantity 2:
> `place_order(action=\"Sell\", orderType=\"Market\", quantity=2, symbol=\"ESU6\")`,
> then `modify_order(orderId=<stop_leg>, quantity=2)` and
> `modify_order(orderId=<target_leg>, quantity=2)`. Approve?"

**Pyramid with risk flag:**

> "Add 2 ES @ 7168 → new basis 7156, dollar risk at stop 7141 jumps
> from \$1,800 to \$4,500 (2.5× current). Options:
> (a) Approve as-is (accepts higher risk).
> (b) Tighten stop to 7155 simultaneously → risk stays \$300.
> (c) Treat as a separate trade with its own tighter stop.
> `estimate_order` says feasible with margin headroom."

**Ladder entry:**

> "3-leg ladder 7148 / 7145 / 7142 (6pt band, ≈0.75×ATR). Qty 1/1/1.
> If only the top leg fills, basis \$7148 (1 contract, lightly
> sized). If all fill, avg basis \$7145 across 3 contracts. Combined
> risk at stop 7140 = \$450 (anchor only) to \$750 (all fill).
> Payloads: 3× `place_order(orderType=Limit, quantity=1, price=...)`."

## Design constraints

- **Never executes.** Produces plans and payloads. Even after the user approves, the user triggers the MCP call, not the skill.
- **Dollar-risk-aware.** Scale-ins typically grow dollar risk. Always surface the before/after delta so the user decides eyes-open.
- **Tick-snapped.** `ladder.py` snaps leg prices to the symbol's tick grid. `place_order` rejects bad prices anyway, but the snap keeps the output clean.
- **Server-authoritative.** `estimate_order` is the last gate on scale-ins. If it says no, the skill reports that and stops.

## Disambiguation

- **vs `pretrade-risk`**: pretrade handles the initial entry (netPos = 0). scale-manager handles netPos ≠ 0 adjustments. Always check `netPos` first and route accordingly.
- **vs `position-watchdog`**: watchdog reports health (P&L, R, distance to stop, flags) informationally. scale-manager produces executable plans. Watchdog can PROPOSE a scale via its alert hook; scale-manager validates and composes the payload.
- **vs `close_position` MCP directly**: `close_position` always closes the full position — it takes no `quantity` parameter. For a literal "close half the ES position", route through this skill's partial-exit pattern (Step 5) instead. Use `close_position` directly only when the user wants the whole position flat.

## Explicit non-goals

- **No execution.** The MCP order tools stay in the user's approval loop.
- **No indicator-driven triggers.** This skill proposes a scale when the user asks. It does not watch the market and auto-propose. (Alert-based monitoring is `alerts-composer` + `position-watchdog`.)
- **No cross-account rebalancing.** Scales apply to ONE symbol on ONE account.
- **No pyramid recursion.** The math supports nested scale-ins, but the narrations cover only one add at a time. Ask the user explicitly before you compound them.

## Resource layout

- `scripts/scale_math.py` — scale-in / scale-out / partial-exit math. Stdin JSON for position state and action params. Actions: `--action scale_in|scale_out|partial_exit`.
- `scripts/ladder.py` — ladder entry splits. Modes: `even`, `atr`, `custom`. Weighting: `equal`, `front`, `back`, `custom`. Integer-quantity allocation uses the largest-remainder method, so the total exactly matches the input `total_qty`.
- `references/scale-patterns.md` — 7 named patterns: partial at 1R, runner, pyramid, and ladder mean-reversion. It also covers ladder breakout retest, pre-event scale-out, and full exit on reversal. The file also has preconditions, narrations, and the MCP-payload translation table. Load it when you pick a pattern or build the MCP payload.
