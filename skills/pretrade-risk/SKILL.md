---
name: pretrade-risk
description: Sizes a proposed futures trade from risk-per-trade (% of netLiq), stop distance (ATR-based or explicit), and contract specs. Then proposes an OCO bracket (stop + target at R-multiple) for the chosen entry. Pending-qty-aware — it includes existing filled position and open Buy/Sell orders. Combined exposure then matches what the server's pre-trade risk check will evaluate. The estimate_order tool exposes that check. Flags exceeds_daily_loss_budget, exceeds_max_contracts, stop_too_wide_for_risk_budget. Use when the user asks to "size a trade", "how many contracts", "what's my risk on this trade", "buy ES", or "sell NQ", or similar bare-intent phrasings without a quantity. Also use when the user wants a bracket proposal. Never executes orders — produces proposals the user must approve. The final feasibility gate is the estimate_order MCP tool.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# pretrade-risk

## Purpose

This skill turns "I want to buy ES" into a sized, bracketed, risk-budgeted proposal. It uses two scripts and one reference. It never emits order payloads. It always leaves the place/modify decision to the user.

## Environment routing

Demo (simulation) and live are two separate MCP servers. Account names are unique to one server. Once the workflow resolves an account on a server, keep every downstream call on that same server. The rule covers `my_portfolio`, `market_snapshot`, `place_order`, `create_alert`, the history tools, and any other tool. Cross-routing fails or hits the wrong environment.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them. Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `my_portfolio` — netLiq, existing position, and pending order qty.
  Prune with `fields=["account.netLiq","positions[].symbol","positions[].netPos","workingOrders[].symbol","workingOrders[].action","workingOrders[].quantity"]`.
- `market_snapshot` — last price, tickSize, valuePerPoint for the
  symbol. Prune with
  `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize","snapshots[].valuePerPoint","snapshots[].initialMargin"]`.
- `risk_settings` — daily loss limit and max contracts per order.
- `estimate_order` — the server's read-only pre-trade feasibility
  gate. Run it in every workflow outcome. Never skip it.
- `describe` — call with `topic='place_order_examples'` to confirm
  the bracket sign convention before submission.

## Workflow

### 1. Resolve the symbol (if needed)

If the user gave a bare product code ("ES"), resolve it with the `contract-intel` skill first. This skill expects a specific contract symbol (like `ESU6`) downstream.

### 2. Gather inputs

Call these MCP tools in parallel where possible:

- `my_portfolio` → `account.netLiq`, existing
  position's `netPos`, sum of pending Buy+Sell orders for the symbol.
  Prune with `fields=["account.netLiq","positions[].symbol","positions[].netPos","workingOrders[].symbol","workingOrders[].action","workingOrders[].quantity"]`.
- `market_snapshot(symbols=[sym])` →
  `lastPrice` (for entry), `tickSize`, `valuePerPoint`.
  Prune with `fields=["snapshots[].symbol","snapshots[].lastPrice","snapshots[].tickSize","snapshots[].valuePerPoint","snapshots[].initialMargin"]`.
- `risk_settings(account=...)` →
  `dailyLossAutoLiq` (absolute value). `risk_settings` has no
  per-order contract-count cap — source that limit from
  `estimate_order`'s pre-trade validation instead.

Also run `market-context`'s `atr.py` on recent bars of the symbol to get the ATR in points. Default is Daily bars, 14-period ATR.

### 3. Size the trade

```bash
python3 scripts/size.py \
    --netliq 100000 \
    --risk-pct 1.0 \
    --atr 6.0 \
    --value-per-point 50 \
    --daily-loss-budget 500 \
    --max-contracts 10 \
    --existing-net-pos 0 \
    --existing-pending-qty 0
```

Output fields used downstream:
- `proposed_qty` → pass to `bracket.py --qty`
- `stop_distance_points` → pass to `bracket.py --stop-distance-points`
- `flags[]` → narrate to the user. See `references/risk-rules.md`

**Always pass `--existing-pending-qty` when non-zero** so sizing matches the server-side pre-trade risk check that will evaluate the order. See `references/risk-rules.md` § pending-qty rule.

If `proposed_qty == 0` and flag is `stop_too_wide_for_risk_budget`: the contract is too large for the risk budget at this stop distance. Options are: use a micro (consult `contract-intel` for the fungible sibling), tighten the stop, or raise `--risk-pct` with explicit user intent. **A zero-qty answer does not skip step 5.** Run the feasibility gate on the alternative you propose. If you have no alternative, run the gate on a qty=1 probe of the requested contract. This way, the server's verdict backs the honest answer.

### 4. Propose a bracket

```bash
python3 scripts/bracket.py \
    --entry 7150 \
    --direction long \
    --stop-distance-points 9 \
    --r-multiple 2.0 \
    --tick-size 0.25 \
    --qty 4 \
    --value-per-point 50
```

`bracket.py` snaps prices to the tick grid. Output gives stop_price, target_price, and dollar-risk/payoff. A `payoff_risk_ratio < 1.5` is a yellow flag. You could tighten the target or widen the stop, for fewer but better trades.

**The user chooses the R-multiple.** The default in examples is 2.0 for illustration. Real invocations should use the target multiple the user actually wants. The skill does not recommend a specific R-multiple. It computes the bracket prices for whatever the user asks for.

#### 4a. Translating bracket.py output to `place_order` — SIGNED DELTAS, not absolute prices

`bracket.py` emits **absolute** `stop_price` and `target_price`. The `place_order` `brackets[]` field expects **signed deltas added to the entry working price** in contract-native points. Both legs compute `entryPrice + delta` server-side, with **no Buy/Sell sign-flip**. `describe(topic='place_order_examples')` confirms this.

**Convert before submitting:**

```
profit_target_offset = target_price - entry_price
stop_loss_offset     = stop_price   - entry_price
```

The signs follow the trade direction:

| Direction | `profitTarget` | `stopLoss` |
|---|---|---|
| **Long** (Buy entry) | **positive** (target above entry) | **negative** (stop below entry) |
| **Short** (Sell entry) | **negative** (target below entry — profit when short) | **positive** (stop above entry — loss when short) |

**Long example** — Buy LMT 7250, target 7458, stop 7074:

```
brackets: [{ "qty": 1, "profitTarget":  208, "stopLoss": -176 }]
```

**Short example** — Sell LMT 7250, target 7042, stop 7426:

```
brackets: [{ "qty": 1, "profitTarget": -208, "stopLoss":  176 }]
```

The `describe(topic='place_order_examples')` text says "positive profitTarget = better, negative stopLoss = worse". That framing is correct only for longs. For shorts the signs invert because "better" (target) is below entry and "worse" (stop) is above. Do not paraphrase "positive = better". Reason from the trade direction.

**Failure mode if you forget:** If you send absolute prices, both legs anchor at `entry + absolute`. An example is `profitTarget: 7458, stopLoss: 7074` on a long at 7250. The target then lands at ~14708, working but unreachable. The stop lands at ~14324, above entry on a long, so the server rejects it. The user ends up with a fill and **no stop loss**. Always convert.

The fill price can also differ from your limit. Better-side fills are common. The system applies the offsets to the actual fill, so the absolute bracket prices auto-anchor correctly without recomputation.

### 5. Final feasibility gate — never skip

Always end with `estimate_order`. The server's pre-trade risk check is the authoritative answer. It is read-only and never places an order, so there is no reason to omit it:

```
estimate_order(
    account=acct, symbol=sym, action=Buy|Sell,
    quantity=proposed_qty, orderType=Market
)
```

This step runs in **every** workflow outcome, and the answer must cite its verdict:

- **Sizing produced a qty** → gate that qty on the requested symbol.
- **Honest zero** (`proposed_qty == 0`) with a micro alternative →
  gate the alternative sizing (e.g. MES qty from the recomputed
  budget).
- **Honest zero, no alternative** → gate `quantity=1` of the requested
  contract anyway. The point is to surface the server's own block —
  e.g. a futures max-order-quantity of 0 or `MaxPosLimitReached` —
  instead of resting the answer on arithmetic alone.

If `feasible: false`, report the reason to the user. Do not propose workarounds automatically. The server said no.

**`MaxPosLimitReached` is dynamic, per-contract, and includes pending working orders.** Two distinct sources fire under the same name. Source (a) is the account's contract whitelist: it excludes the contract or the product. Source (b) is the per-product hypothetical post-fill position (`hypoLong` / `hypoShort` / `hypoExposed`). It exceeds the limit once the count includes in-flight working orders. The user might have recent in-flight churn, such as just-cancelled bracket legs or just-modified working orders. In that case, the hypothetical count can run temporarily high. After the working-order state settles, a single retry is legitimate. If the rejection persists, it is a real account-config gate. Defer to the user to adjust it through Account Settings. Never silently work around it.

### 6. Alert-proposal hook (optional)

Once the user approves the bracket, emit complementary alert expressions for the user to submit via `alerts-composer`. See `references/risk-rules.md`, section Alert-proposal hook, for templates. Typical examples are a breakeven-trip alert and a target-approach alert.

## Output idioms

Lead with the qty and dollar risk. Include the R:R ratio. Mention ATR for context. Example narration:

> "4 ES long at 7150 with a 12-point stop (~1.5×ATR of 8): $2,400 at
> risk, 360% of your daily $500 budget — the trade is too big for
> one day's loss budget. Options: drop to 1 contract (risk $600),
> tighten stop to 6 points (risk $1,200, still 240% of budget), or
> raise daily budget explicitly before proceeding."

Or when everything fits:

> "4 ES long at 7150, stop 7141, target 7168. $1,800 risk (1.8% of
> netLiq), $3,600 payoff at 2R target. estimate_order confirms
> feasible."

Or the honest zero — still grounded in the server's verdict:

> "Zero ES contracts: 1% of your $9,900 netLiq is a $99 risk budget,
> and a 10-point ES stop risks $500 per contract. estimate_order
> confirms the account can't take the trade (futures max order qty
> is 0). MES with the same stop risks $50 per contract — 1 contract
> fits the budget if you want the micro."

## Disambiguation

- vs `contract-intel`: contract-intel resolves "ES" → "ESU6". This
  skill sizes a trade on the resolved symbol. Always run contract-intel
  first when the user gave a bare code.
- vs `scale-manager`: pretrade-risk sizes the **initial entry**.
  Scaling in/out of an existing position (adding on a breakout, taking
  partial at target) is scale-manager's job.
- vs `position-watchdog`: pretrade-risk runs **before** the position
  is live. Once filled, position-watchdog monitors health.
- vs `risk-coach`: this skill computes the numbers (qty, stop, target).
  risk-coach judges whether the plan is behaviorally sound ("are you
  trading on tilt?", "is this your third trade this hour?"). This is
  a different, higher-level check.

## Explicit non-goals

- **Never executes orders.** Output is informational. The user makes
  the call. `place_order` is a separate step the user triggers.
- **Never overrides server risk limits.** If `estimate_order` rejects,
  the user has to change something. Raising hidden limits is not a
  fix.
- **Not a strategy.** Sizing + bracketing is one piece of a complete
  trade plan. Direction/entry-trigger/exit-timing are the user's.

## Resource layout

- `scripts/size.py` — position-sizing math, pending-qty-aware, with
  guardrail flags
- `scripts/bracket.py` — bracket proposal (stop + target) with
  tick-grid snapping and risk/payoff dollar math
- `references/risk-rules.md` — guardrail taxonomy, the pending-qty
  rule, default parameters, alert-proposal hook templates, and
  explicit non-goals. Load it when you narrate a guardrail flag or
  draft an alert-proposal hook.
