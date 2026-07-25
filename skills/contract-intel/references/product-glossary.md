# Product glossary — full / micro pairs, tick intuition, rollover conventions

Load this when:
- The user asks about full-vs-micro contrast ("is there a micro of ES?")
- The user asks about tick value or margin for an unfamiliar product
- You need to explain settlement (cash vs physical) or rollover behavior

## Full / micro pairs

Most micros trade 1/10th the notional of the full-size contract. Same tick size, same underlying index, same expiration cycle — just smaller. Use them for finer position sizing, practice, or to round out a full-size position.

Two rows break the 1/10th rule. The `Ratio` column states each pair's real ratio, and the `Micro $/point` column states the micro's own point value.

| Full | Micro | Underlying | Full margin ≈ | Full $/point | Ratio | Micro $/point |
|------|-------|------------|---------------|--------------|-------|---------------|
| ES   | MES   | S&P 500    | ~$13,200      | $50          | 1/10  | $5            |
| NQ   | MNQ   | NASDAQ 100 | ~$17,600      | $20          | 1/10  | $2            |
| YM   | MYM   | Dow Jones  | ~$9,900       | $5           | 1/10  | $0.50         |
| RTY  | M2K   | Russell 2k | ~$8,250       | $50          | 1/10  | $5            |
| CL   | MCL   | Crude oil  | ~$5,500       | $1,000       | 1/10  | $100          |
| GC   | MGC   | Gold       | ~$11,000      | $100         | 1/10  | $10           |
| SI   | SIL   | Silver     | ~$15,400      | $5,000       | 1/5   | $1,000        |
| NG   | MNG   | Natural gas| ~$3,300       | $10,000      | 1/4   | $2,500        |
| 6E   | M6E   | Euro FX    | ~$2,750       | $125,000     | 1/10  | $12,500       |

**The two exceptions:**

- `SIL` covers 1,000 troy ounces of silver against `SI`'s 5,000, so it
  is 1/5, not 1/10.
- `MNG` covers 2,500 MMBtu of natural gas against `NG`'s 10,000, so it
  is 1/4, not 1/10.

Margins drift with volatility — always prefer `market_snapshot` for the live initial-margin number. Rough values above are for LLM narrative and cross-checks, not sizing.

Fungibility: the `search_contracts` tool's optional `includeFamilySiblings` field returns the counterpart of a hit (if any). That is the authoritative source. This table is a fallback for when the tool is not called.

## Tick intuition

| Product | Tick size | Tick $ |
|---------|-----------|--------|
| ES, MES | 0.25      | $12.50 / $1.25 |
| NQ, MNQ | 0.25      | $5.00 / $0.50  |
| YM, MYM | 1.00      | $5.00 / $0.50  |
| RTY, M2K| 0.10      | $5.00 / $0.50  |
| CL, MCL | 0.01      | $10.00 / $1.00 |
| GC, MGC | 0.10      | $10.00 / $1.00 |
| ZB      | 1/32 (0.03125) | $31.25 |
| ZN      | 1/64 (0.015625) | $15.625 |
| ZC, ZW, ZS | 0.25   | $12.50 |

Bond tick fractions are notorious. ZB quotes like `129'16` mean `129 + 16/32 = 129.5`. Some feeds show the fractional part as decimal (`129.5`), others as the raw ticks (`129'16`). Match the convention of the `market_snapshot.lastPrice` field.

## Settlement types

**Cash-settled** — at expiration, the final value is paid in cash against an index reference. No physical product changes hands. Most equity-index futures (ES, NQ, YM, RTY and their micros) are cash-settled.

**Physical-delivery** — at expiration, the short must deliver the underlying asset (oil barrels, corn bushels, bond certificates) to the long. Roll well before expiry to avoid accidental delivery. CL, GC, NG, ZC, ZW, ZS, ZB, ZN are all physical. **Exceptions:** MCL (micro crude) and MNG (micro natural gas) settle financially, unlike their full-size CL and NG counterparts.

For a retail trader holding physicals close to expiry: **roll**. Most brokers will auto-liquidate before delivery anyway, but at a price and timing the broker chose, not you.

## Rollover conventions

**CME quarterlies** — ES, NQ, YM, RTY: March (H), June (M), September (U), December (Z). Rollover window starts ~8 business days before expiry, mostly finishes 2 days before. Liquidity shifts to the next quarter.

**Monthly energy** — CL, NG: monthly contracts (every month letter). Expire late in the month preceding the contract month (ugh): CLU6 expires in late August, not September. Always check `expirationDate` from the snapshot, never infer from the symbol.

**Metals** — GC, SI: primary months differ (GC is Feb/Apr/Jun/Aug/Dec, SI is Mar/May/Jul/Sep/Dec). Others exist but are not liquid.

**Grains** — ZC, ZW: H/K/N/U/Z (Mar/May/Jul/Sep/Dec) are the liquid months. ZS (soybeans) uses a different cycle: F/H/K/N/Q/U/X (Jan/ Mar/May/Jul/Aug/Sep/Nov) — it has no December contract. Avoid the off-months for each product.

Use `resolve.py` and `rollover.py` to avoid memorizing any of this — they read live OI from `market_snapshot` and make the call. This glossary is for narration context ("you're close to rollover" / "cash-settled so no delivery risk") not for routing decisions.

## Event contracts (Kalshi)

Kalshi event contracts ("will NFP print above 200k?") have a different shape than futures. They do not roll. Each market has a single resolution date. Detect a Kalshi entry by its resource URI (`tradovate://kalshi-events`), not by a `productType` value. Use the `kalshi-events` MCP resource, not `search_contracts`, for discovery.
