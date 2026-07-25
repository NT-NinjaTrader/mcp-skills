# Risk rules — guardrails, sizing conventions, and the pending-qty rule

Load this when:
- Narrating a guardrail flag from `size.py`
- Explaining why the sized qty is lower than the user expected
- Deciding how to fold risk from existing + pending qty into a new proposal

## Default parameters

- **Risk per trade**: 1% of netLiq
- **Stop distance**: 1.5 × ATR(14) on the timeframe you trade
- **Target R-multiple**: 2.0 (target payoff = 2 × stop distance)
- **Min viable qty**: 1 contract. Below that, `size.py` emits qty=0 with
  flag `stop_too_wide_for_risk_budget` — the stop is too wide relative
  to equity, or the product is too big (e.g., full ES on a small account
  where MES is more appropriate).

These numbers are a starting point. A user who specifies a different risk percent or a tighter stop should override via CLI.

## The pending-qty rule

**Server-side risk systems include pending orders** (`filled + openBuy + openSell`) when evaluating exposure. A user filled 2 ES long and has a working Buy Limit 2. For pre-trade risk checks, the server treats that user as effectively long 4. Sizing that ignores pending qty lets the user stack past their limits in two separate invocations:

    "size ES"    → 4 contracts (no awareness of existing 2 pending)
    actual exposure after fill: 6 contracts → past the limit

**Always pass `--existing-net-pos` and `--existing-pending-qty`** to `size.py` when they are non-zero. The source values come from `my_portfolio`:

- `existing-net-pos`: the signed `netPos` on the position for this symbol
- `existing-pending-qty`: sum of working-order quantities on the
  same symbol — count both open Buy and Sell orders regardless of
  direction, since each adds to the exposure the server will evaluate

`size.py` returns `combined_qty_after_fill` which reflects `|existing_net_pos| + existing_pending_qty + proposed_qty`. Compare that against `--max-contracts` to decide whether the proposal is within a known cap. The caller supplies the `--max-contracts` value. `risk_settings` has no per-order or per-position contract-count field. `estimate_order`'s pre-trade validation is the authoritative source for any hard cap the server enforces.

## Guardrail flags from `size.py`

### `stop_too_wide_for_risk_budget`

**Meaning:** The stop distance in dollars exceeds the user's risk budget even for a single contract.

**Fix options:**
- Widen the risk budget: `--risk-pct 2.0`
- Tighten the stop: explicit `--stop-distance-points N` with a smaller N
- Use a smaller contract: micros (MES instead of ES, MNQ instead of
  NQ). The `contract-intel` skill's `product-glossary.md` has the
  full-to-micro pairs.

### `exceeds_daily_loss_budget`

**Meaning:** The trade's risk, if the stop trips, would consume more than 100% of the daily loss limit. One losing trade, budget blown.

**Why it matters:** Prop firms and risk policies usually have hard caps. A single trade that exceeds the cap triggers liquidate-only mode.

**Fix options:**
- Tighten the stop
- Cut the qty manually (trade smaller than the standard formula gives)
- Skip the trade

Do not override without explicit user intent.

### `exceeds_max_contracts`

**Meaning:** `combined_qty_after_fill` exceeds the `--max-contracts` value the caller supplied. `risk_settings` has no per-order or per-position contract-count field — treat `estimate_order`'s pre-trade validation as the authoritative cap.

**Fix options:**
- Close or cancel some of the existing pending orders first
- Propose a smaller qty manually
- Request a higher limit (out of scope for this skill)

### `pending_qty_awareness` (informational, not a hard flag)

Surfaces when `--existing-pending-qty > 0`. Not a bug — just a reminder that the combined size includes in-flight orders. Mention in narration so the user knows the skill saw them.

## Other checks the skill does NOT perform

These live in other skills or on the server:

- **Margin feasibility** — `estimate_order` is the final gate. Always
  call it after sizing to catch cases where the account does not have
  enough buying power even for a position the risk budget accepts.
- **Correlated exposure across symbols** — `position-watchdog` flags
  `correlated_long_exposure` when the user is long multiple index
  products. Repeat that check if the proposed trade adds to a
  correlated set.
- **Behavioral patterns** (revenge trading, size doubling after a
  losing streak) — `risk-coach` territory. pretrade-risk is mechanical
  math. Behavioral pattern-matching happens in a separate skill.
- **Rollover proximity** — `contract-intel` classifies rollover
  imminence. When `rollover.py` reports `imminent`, mention it in
  narration. Do not auto-reject. The user may have a good reason
  to trade the expiring contract.

## Alert-proposal hook

After sizing and bracketing, propose complementary alert expressions and hand to `alerts-composer` for submission. Good defaults:

- **Breakeven trip**: `lastPrice(ESU6) > {entry} AND posOpenPLUsd(ESU6) > 0`
  — heads-up when the position reaches breakeven
- **Target approach**: `lastPrice(ESU6) > {target - 3*tick}` — a few
  ticks before the target so the user can decide whether to take off
  early or let it fill
- **Stop approach**: `lastPrice(ESU6) < {stop + 3*tick}` — a few ticks
  before the stop, so there is time to react (or accept the fill)

The DSL subject carries no quotes. Write `lastPrice(ESU6)`, never `lastPrice("ESU6")` — `alerts-composer`'s `validate.py` rejects the quoted form. Substitute the contract you sized for `ESU6`.

Emit the expressions as strings only. This skill never submits. The user decides whether to call `alerts-composer` on the proposal.

## Final step — feasibility gate

Sizing + bracketing happens on the client. The final "can this actually execute on this account?" check belongs to `estimate_order`:

    estimate_order(
        account=acct, symbol=sym, action=Buy, quantity=qty,
        orderType=Market
    )

`estimate_order` returns `feasible: false` with a reason when the server's pre-trade risk check rejects the order. The server evaluates that check and enforces the result. That response is the authoritative answer — the skill is advisory, the server has final say.
