# Alert-DSL pattern library

Ready-to-paste expression templates for common user intents.
`scripts/validate.py` validates every one of them.

Replace `<SYM>` with an exact contract symbol (`ESU6`, `BTC/USD`),
`<ACCT>` with an account name (`DEMO-ACCOUNT-1`), `<LVL>` with a price, and
`<N>` with a dollar amount.

## 1. Price cross (up)

Intent: "Alert when ES trades above 7200."

```
lastPrice(<SYM>) > <LVL>
```

- Equivalent to `trigger=CrossesAbove` in the simple mode of
  `create_alert` (Mode A). Prefer Mode A unless you need more.

## 2. Price cross (down)

```
lastPrice(<SYM>) < <LVL>
```

## 3. Breakout bracket

Intent: "Tell me if ES breaks out of the 7180–7220 range."

```
lastPrice(<SYM>) > 7220 OR lastPrice(<SYM>) < 7180
```

- Pattern: two one-sided crosses joined with `OR`. **No outer parens** —
  parens don't wrap logic in this DSL.

## 4. Stop heads-up

Intent: "Warn me 3 ticks before my ES stop at 7145." (tick = 0.25)

```
lastPrice(<SYM>) < 7145.75
```

- Trigger 3 ticks above the stop → heads-up before actual hit. Single
  compare is enough.

## 5. Target approach

Intent: "Ping me when ES gets near my target 7200, say within 2 pts."

```
lastPrice(<SYM>) > 7198
```

## 6. Breakeven-trip alert

Intent: "Tell me when a long ES position is back in the green."

```
posOpenPLUsd(<SYM>) > 0
```

- The position is implicitly on the caller's account.

## 7. Hard P&L floor on a position

```
posOpenPLUsd(<SYM>) < -<N>
```

- Sized to a pre-chosen dollar risk (e.g., `< -300`).

## 8. Hard P&L floor on account

Intent: "Alert if today's P&L goes below $-500 across everything."

```
dollarTotalPL(<ACCT>) < -500
```

- `dollarTotalPL` = realized + unrealized. Use `dollarOpenPL` if you
  want unrealized only.

## 9. Day-loss budget about to hit

Intent: "Warn me at 80% of my $500 daily loss limit."

```
dollarTotalPL(<ACCT>) < -400
```

- Hardcode the threshold; DSL can't read `dailyLossLimit` programmatically.

## 10. Margin blow-up heads-up

Intent: "Alert if margin usage crosses 90% of netLiq."

```
totalUsedMargin(<ACCT>) > netLiq(<ACCT>) * 0.9
```

- Arithmetic on the RHS — valid per the grammar.

## 11. Gap-from-settle

Intent: "Alert if ES gaps more than 0.5% off settlement."

```
lastPrice(<SYM>) > settlementPrice(<SYM>) * 1.005 OR lastPrice(<SYM>) < settlementPrice(<SYM>) * 0.995
```

## 12. Session break (break of session high/low)

```
lastPrice(<SYM>) > highPrice(<SYM>) OR lastPrice(<SYM>) < lowPrice(<SYM>)
```

- `highPrice`/`lowPrice` are session high/low so far. Once session
  updates, the alert keeps moving with it.

## 13. Relative strength divergence

Intent: "ES green but NQ red."

```
percentChange(ESU6) > 0 AND percentChange(NQU6) < 0
```

## 14. Spread watch

Intent: "Alert if ES and NQ diverge by more than 50 points."

```
lastPrice(ESU6) - lastPrice(NQU6) > 50 OR lastPrice(NQU6) - lastPrice(ESU6) > 50
```

## 15. FX rate cross

```
currentRate(EUR) > 1.10
```

## 16. Reaction-window bracket (event-watch hook)

Intent: "Wide bracket for a CPI release — size the offset to the
measured reaction, not a fixed number."

```
lastPrice(<SYM>) > <ENTRY + REACTION_SIZE> OR lastPrice(<SYM>) < <ENTRY - REACTION_SIZE>
```

- `REACTION_SIZE` comes from `reaction_size.py`'s `mean_abs_move` output (see `event-watch/SKILL.md` § Alert-proposal handoff) — never a hardcoded constant.
- These values are a snapshot at alert-creation time. To track the level through the whole session instead, use the session-break pattern (#12).

## 17. Position-flat confirmation

Intent: "Ping me if ES position hits zero."

```
netPos(<SYM>) = 0
```

## 18. Position-direction switch

Intent: "Alert if ES flips from long to short."

```
netPos(<SYM>) < 0
```

---

## Composing your own

Rules:
- Each compare = two arithmetic expressions + one `compareOp`.
- Arithmetic may use `+ - * /` and parens.
- Multiple compares join with `AND OR XOR` — **flat**, no parens.
- Subjects have NO quotes.
- Function names must come from `dsl-functions.md`.

If the intent requires:
- A multi-bar indicator (ATR, RSI, moving average) → snapshot the
  value NOW, emit a fixed-price bracket at `entry ± snapshot`.
- A time-of-day condition → submit with `validUntil` instead.
- A cross-account aggregation → not expressible. Say so.
