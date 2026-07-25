# Scale patterns — when and how

Named recipes for the most common scaling decisions.
Each pattern names the conditions to check, the action to propose, and the fields `scale_math.py` / `ladder.py` produce to support it.

## Table of contents

1. Scale out at 1R (classic partial)
2. Runner: scale out half, move stop to breakeven
3. Pyramid-into-trend (add on new high)
4. Ladder entry — mean-reversion
5. Ladder entry — breakout retest
6. Scale out before a known event
7. Full exit on reversal signal

---

## 1. Scale out at 1R (classic partial)

**Intent:** take profit once the trade reaches 1 full R of favorable excursion.
This preserves a runner for the trend.

**Check:**
- `R_before ≥ 1.0` at the current mark
- Enough qty to split (≥ 2)

**Action:** `scale_math.py --action partial_exit --pct 0.5` (or an explicit `scale_out`).
If qty is 1, the pattern does not apply. Consider a wider target instead.

**Output narration:**
> "Long 4 ES @ 7150, mark 7168 (2R). Take 2 off now, locks in $1,800.
> Remaining 2 with stop at 7141, risk $900, free to run to target."

---

## 2. Runner: scale out half, move stop to breakeven

**Intent:** after a 1R partial, move the stop on the remainder to entry.
This converts the remaining position to free-roll risk.

**Check:**
- The trade just completed pattern #1
- Remaining `qty ≥ 1`

**Action sequence:**
1. `partial_exit --pct 0.5`, then resize BOTH remaining bracket legs to the post-exit quantity (see "Converting output to MCP payloads" below).
2. Emit a modify_order on the now-resized bracket stop leg, with new `stopPrice = basis`.
3. Update risk: dollar risk becomes 0 on the remainder.

**Output narration:**
> "Scaled out 2, booked $1,800. Moving stop on remaining 2 to 7150
> (entry) — free-roll from here. Target 7175 for another $2,500."

---

## 3. Pyramid-into-trend (add on new high)

**Intent:** add qty when price breaks to a new session high (long) or low (short).
Keep the stop on the ORIGINAL position. Add a tighter stop on the added qty.

**Check:**
- Trend context (from `market-context`: `trend_up` for long)
- Current mark breaks the prior HoD or a new swing high
- The existing position already sits at ≥ 0.5R favorable
- The daily/weekly risk budget has room

**Action:** `scale_math.py --action scale_in` with `action_qty` equal to or less than the initial qty (the "add half" rule of thumb).

**Key risk-math note:** a scale-in RAISES the dollar-risk-at-stop.
The combined position now holds more qty at a higher basis with the same stop.
`scale_math.py` reports `dollar_risk_after_action`, so the user sees this clearly before they approve.

**Mitigation options:**
1. Move the stop up at the same time (tighten to trail the swing low)
2. Use a separate "add leg" with its own tighter stop (two trades)
3. Accept the higher risk explicitly

**Output narration:**
> "Long 4 ES @ 7150, mark 7168 (+2R). Breaking to new HoD. Add 2 @
> 7168? New basis 7156, risk moves from \$1,800 to \$4,500 at stop
> 7141 — consider tightening stop to 7155 (new basis − 1pt) to keep
> risk around \$900."

---

## 4. Ladder entry — mean-reversion

**Intent:** expect price to pull back into a zone.
Split the total qty across the zone so the average fill beats a single-price limit.

**Check:**
- The trade thesis is reversion (against the recent move)
- The zone width is known (e.g., 1×ATR)
- Total qty ≥ 2

**Action:** `ladder.py --mode even --band-points <atr×1.0> --legs 3 --weighting back`. This is back-loaded, so more size fills at the worst price (deepest into the zone).
Alternative: `--weighting equal`.

**Output narration:**
> "3-leg ladder 7148 / 7145 / 7142 (6pt = 0.75×ATR). Qty 1 / 1 / 1.
> If only the first leg fills, basis 7148 (smallest position). If all
> fill, avg basis 7145 — 3pt better than a single limit at 7148, but
> you're fully sized in a deeper pullback."

---

## 5. Ladder entry — breakout retest

**Intent:** expect a retest of a broken level.
Use front-loaded weighting, so the initial tag gets most of the size.

**Check:**
- Momentum context (breakout confirmed)
- The retest zone has clear boundaries

**Action:** `ladder.py --mode custom --prices <level>,<level-1×atr> --weighting custom --weights 0.67,0.33` (or similar).

---

## 6. Scale out before a known event

**Intent:** reduce exposure before CPI, FOMC, NFP, or EIA.
This is not risk-avoidance dogma. It simply sizes the position correctly for higher volatility.

**Check:**
- `event-watch` surfaces an imminent high-importance event
- The current position sits in the event's product group

**Action:** `scale_math.py --action partial_exit --pct 0.5`, OR a full scale_out if the position does not survive the event's volatility.

**Output narration:**
> "CPI in 18 min. You're long 4 ES — recent CPI releases have moved
> ES by double-digit points within minutes. Options: (a) scale to 2
> (risk halved), (b) flatten and redeploy after, (c) hold with stops
> at 1.5× normal."

---

## 7. Full exit on reversal signal

**Intent:** the trade thesis no longer holds. Exit completely. Do not average.

**Check:**
- Structure broke: `market-context.regime` flipped (trend_up → trend_down), OR the session VWAP broke against the position

**Action:** `scale_math.py --action scale_out` with `action_qty = current_qty`. Document why (state the signal you observed).

---

## Converting output to MCP payloads

`scale_math.py` and `ladder.py` produce math, not order payloads.
Translate to MCP like this:

**Scale out** (`close_position` always closes the full position — it takes no `quantity` parameter):
- A partial exit needs the exit order, plus a resize of both bracket legs.
- Emit `place_order(orderType=Market, quantity=off_qty, action=opposing_side)` for the offset quantity.
- Wait for the fill to confirm, then resize BOTH remaining legs to the same `remaining_qty` (`current_quantity - off_qty`).
- `modify_order(orderId=<stop_leg_id>, quantity=<remaining_qty>)` and `modify_order(orderId=<target_leg_id>, quantity=<remaining_qty>)`.
- A same-quantity stop left at the ORIGINAL size over-protects the remainder. It can also flip the position if it fills.
- A same-quantity target carries the mirror risk: a full fill flips the position too. See "If a resize fails or the caller skips it" below for the failure path.

**Scale in** (add to the position):
- `place_order(action=same_side, orderType=Limit|Market, quantity=add_qty, price=add_price)`
- The server-side pre-trade risk check **includes pending qty**. If working orders for the symbol already exist, pass the total-intended state through.
- Let the server re-check it (see the `pretrade-risk` skill's pending-qty rule).

**Ladder entry**: one `place_order` per leg (all as limit orders at each leg's price).

**Stop-move** (breakeven trip, trail): `modify_order(orderId=<bracket_stop_leg_id>, stopPrice=<new>)`.

Always print the exact MCP payloads for the user to approve.
Never call the MCP directly from this skill.

### If a resize fails or the caller skips it

Nothing on the server links the exit order to the two bracket legs.
If either resize call fails, or the caller skips it, the position carries a mis-sized leg.
Do not treat the scale as done.
Tell the user which leg still carries the ORIGINAL quantity.
Propose the resize again first, before any other change to the position.

## When a pattern does not apply

If the check fails, explain WHY and offer a nearby alternative:

- Qty=1 → "Can't scale a single contract. Options: raise target by 1R, or move stop to breakeven at +1R to guarantee non-loss."
- R < 1 on a partial proposal → "You're at +0.4R — partial here locks in \$X but sacrifices the trade's R-expectancy. Let it get to 1R or tighten stop to breakeven first."
- Basis below the new proposed stop (shorts/longs inverted) → refuse with an error; something is wrong in the inputs.
