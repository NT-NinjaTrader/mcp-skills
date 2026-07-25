---
name: contract-intel
description: Symbol discovery, front-month resolution, rollover-imminence classification, and product-family awareness (full ↔ micro pairs like ES/MES) for futures contracts. Resolves bare product codes like "ES" or "NQ" to the actual tradeable front-month contract (e.g., ESU6) by open-interest rank across maturities. Classifies rollover status as not_imminent / approaching / imminent / rolled, with calendar-spread candidate flag when both legs are liquid. Use when the user asks "what symbol", "which contract to trade", "front month", "roll" or "rollover", "micro" or "full", or "calendar spread". Also use when the user gives a bare product code (ES, NQ, YM, CL, GC, etc.) without a maturity. Also handles product-family metadata via search_contracts includeFamilySiblings flag.
compatibility: This skill requires the NinjaTrader MCP server, connected through a client with MCP support.
---

# contract-intel

## Purpose

This skill turns a user's bare product code ("ES") into the actual
tradeable contract. It flags rollover risk. It surfaces the
full-vs-micro sibling when relevant. This skill does not resolve
symbols server-side, for two reasons. The per-maturity OI query costs
the same either place. Also, the skill gains more narrative
flexibility this way.

## Environment routing

This covers symbol and market data only, with no account binding. A
sibling skill's account resolution might already fix a session to
demo (simulation) or live. If so, stay on that same MCP server for consistency.

## MCP tools used

Tool names below are bare. The NinjaTrader MCP server provides them.
Your client adds its own prefix. See `AGENTS.md` at the repo root.

- `market_snapshot` — resolve the front-month contract and its
  rollover status from a bare product code. Prune with
  `fields=["snapshots[].symbol","snapshots[].expirationDate","snapshots[].totalVolume","snapshots[].openInterest","snapshots[].lastPrice"]`.
- `search_contracts` — look up the full/micro sibling for a product.
  Call it with `includeFamilySiblings=true`.

## Workflow

### 1. Front-month resolution

When the user says "buy ES" or asks "what's NQ doing?", resolve the
bare product code to a specific contract before any other tool call.
Save the tool result to a file. Pass its path with `--file`. Never
re-type or inline a large JSON payload in the command.

```bash
market_snapshot(
    product="ES",
    fields=["snapshots[].symbol","snapshots[].expirationDate","snapshots[].totalVolume","snapshots[].openInterest","snapshots[].lastPrice"]
)
# Save that response to market_snapshot.json, then:
python3 scripts/resolve.py --file market_snapshot.json
```

`market_snapshot` with `product` returns every non-expired maturity.
Prune the response to the five fields that the resolve and rollover
scripts read. `resolve.py` returns:

- `front_month` — the contract with the highest OI among the nearest
  two maturities. This handles mid-rollover, when the next maturity
  overtakes the nearest.
- `next_month` — the maturity immediately after front
- `oi_ratio` — front OI / next OI
- `rolled_already` — true if the second-nearest maturity has more OI
  than the nearest

Use `front_month.symbol` for any follow-up tool call (place_order,
market_history, etc.).

### 2. Rollover status

When the user asks "is ES about to roll?" or "should I switch
contracts?", run `rollover.py` on the same input:

```bash
market_snapshot(
    product="ES",
    fields=["snapshots[].symbol","snapshots[].expirationDate","snapshots[].totalVolume","snapshots[].openInterest","snapshots[].lastPrice"]
)
# Run rollover.py on the same saved response:
python3 scripts/rollover.py --file market_snapshot.json
```

Returns a `status` classification. The script applies these rules in
order, and the first match wins:

- `rolled` — next OI > front OI, at any day count. Trade the next
  contract.
- `imminent` — 5 days or fewer to expiry, at any open interest.
  Proximity overrides open interest here. Tell the user to roll the
  position or to close it before expiration.
- `not_imminent` — days > 15 AND the next month cannot absorb a roll.
  Either the next month holds no open interest, or the front holds more
  than 5x it. No action needed.
- `imminent` — 5 to 15 days out AND next OI is 50% of front OI or more.
  Rollover happens now. Execution runs thinner than usual.
- `approaching` — every other case. Prefer the front contract. Watch
  for rollover in a few days.

Also emits a ready-to-narrate `narrative` string and a
`calendar_spread_candidate` flag. This flag is true when both legs
have liquidity. The OI ratio is then between 0.3 and 3, during
approaching or imminent status.

### 3. Product family (micro / full)

When the user asks "is there a micro of ES?" or "ES vs MES?" —
call `search_contracts` with the `includeFamilySiblings` field. That
field adds each hit's full/micro counterpart to the result:

```
search_contracts(text="ES", includeFamilySiblings=true)
```

Each result's `familySibling` field (when present) gives the
counterpart's product name, description, isMicro flag, and
valuePerPoint. Narrate the contrast directly. No script needed.

The product family might not appear in the search results. If so,
load `references/product-glossary.md` for the common-pairs table and
margin intuition.

### 4. Event contracts (Kalshi)

When the user asks about Kalshi markets — read the `kalshi-events`
MCP resource, not `search_contracts`. Read it by its URI, through
whatever resource-read action your client provides:

```
tradovate://kalshi-events
```

Event contracts resolve to a single date (no rollover) and live in the
separate `tradovate://kalshi-events` resource. Detect a Kalshi entry by
that resource URI, not by a `productType` value. See
`references/product-glossary.md` § Event contracts for more.

## Output idioms

Always quote the **exact** contract symbol — never invent. `ESU6`,
not `ES` or `@ES`. Pulled from `market_snapshot.symbol` or
`search_contracts.symbol`.

When narrating rollover:

- Not imminent: "Liquidity is in {symbol} ({oi_fmt} OI, {days} days).
  No rollover action needed right now."
- Approaching: "{front} is still the front contract, but {next} is
  picking up. Expect rollover in the next few sessions."
- Imminent: "{front} vs {next} — rollover window. Liquidity is split;
  execution may be thinner than usual. Consider rolling now."
- Rolled: "{front} has already lost liquidity to {next}. Trade {next}."

When narrating full vs micro:

- "The micro of ES is MES — 1/10th the notional ($5/point vs $50/point
  for ES), same tick size. Use it for finer sizing or to round out
  your full-size exposure."

## Disambiguation

- vs `correlation-hedge`: contract-intel handles **same-underlying
  alternatives** (ESU6 vs MES, ES front vs next month). Cross-underlying
  pairs like ES/NQ — how correlated, how to hedge one with another —
  live in `correlation-hedge`.
- vs `pretrade-risk`: this skill resolves the symbol. Pretrade-risk
  sizes the trade on that symbol. Always run resolve first.
- vs `search_contracts` directly: if the user already named a specific
  contract (ESU6, not "ES"), skip this skill. Go straight to the
  target tool. This skill is for **disambiguation** from bare product
  codes.

## Known gotchas

- Contract symbols are exact. `ESU6` trades. `ES` does not. Never
  accept a bare code from the LLM as a tradeable symbol without
  running it through `resolve.py` first.
- Monthly contracts (CL, NG) expire the month **before** the contract
  month (CLU6 expires late August, not September). Never infer from the
  symbol. Always use `market_snapshot.expirationDate`.
- `rolled_already` in `resolve.py` differs from `status = "rolled"`
  in `rollover.py`. The first is a fact about the two nearest
  maturities. The second is a classification that also weighs OI
  ratio and days.

## Resource layout

- `scripts/resolve.py` — bare product code → front-month resolution
  (input: `market_snapshot(product=...)` response)
- `scripts/rollover.py` — rollover-status classification + narrative
  (same input)
- `scripts/fixtures/` — three synthetic ES snapshots covering
  not_imminent, imminent, and rolled states for regression testing
- `references/product-glossary.md` — full/micro pairs, tick intuition,
  settlement types, rollover conventions. Load it when you narrate a
  cross-product contrast, or when `market_snapshot` does not provide
  the needed context
