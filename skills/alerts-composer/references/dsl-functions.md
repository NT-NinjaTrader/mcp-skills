# Alert DSL — function catalog

**Ground truth.** Do not invent functions outside this list.
This list mirrors every function the server accepts in an alert
expression today, across the account, contract, position, and currency
entities.

Total: **37 numeric functions, 0 boolean functions.**

## Account (14) — subject is account name

| Function | Meaning | Example |
|----------|---------|---------|
| `cashAmount` | Cash balance | `cashAmount(DEMO-ACCOUNT-1) < 1000` |
| `dollarOpenPL` | Unrealized P&L, USD | `dollarOpenPL(DEMO-ACCOUNT-1) < -500` |
| `dollarTotalPL` | Realized + unrealized P&L, USD | `dollarTotalPL(DEMO-ACCOUNT-1) > 1000` |
| `netLiq` | Net liquidation value | `netLiq(DEMO-ACCOUNT-1) < 8000` |
| `initialMargin` | Initial margin req (account level, contract currency) | `initialMargin(DEMO-ACCOUNT-1) > 5000` |
| `maintenanceMargin` | Maintenance margin req | `maintenanceMargin(DEMO-ACCOUNT-1) > 4500` |
| `dayMargin` | Day trading margin requirement | `dayMargin(DEMO-ACCOUNT-1) > 4000` |
| `totalUsedMargin` | All margin currently committed | `totalUsedMargin(DEMO-ACCOUNT-1) > 6000` |
| `positionMargin` | Margin attributable to open positions | `positionMargin(DEMO-ACCOUNT-1) > 5000` |
| `dailyLossLimit` | Configured daily-loss cap | reference value — rarely the trigger itself |
| `weekLoss` | Week-to-date realized loss | `weekLoss(DEMO-ACCOUNT-1) > 1500` |
| `weeklyLossLimit` | Configured weekly-loss cap | reference value |
| `futuresOnlyNetLiq` | NetLiq excluding non-futures positions | `futuresOnlyNetLiq(DEMO-ACCOUNT-1) < 8000` |
| `openCollateralReq` | Collateral required for open orders | `openCollateralReq(DEMO-ACCOUNT-1) > 2000` |

**Subject format:** the exact account name from `my_portfolio.account.name`.
Do not assume any prefix pattern.

## Contract (9) — subject is contract name

| Function | Meaning | Example |
|----------|---------|---------|
| `lastPrice` | Last trade print | `lastPrice(ESU6) > 7200` |
| `change` | Abs change vs prior session close | `change(ESU6) > 50` |
| `percentChange` | Percent change vs prior session close | `percentChange(ESU6) < -2` |
| `bidPrice` | Current best bid | `bidPrice(ESU6) < 7195` |
| `offerPrice` | Current best ask | `offerPrice(ESU6) > 7205` |
| `openPrice` | Session open | `lastPrice(ESU6) < openPrice(ESU6)` |
| `highPrice` | Session high | `lastPrice(ESU6) >= highPrice(ESU6)` |
| `lowPrice` | Session low | `lastPrice(ESU6) <= lowPrice(ESU6)` |
| `settlementPrice` | Prior session settlement | `lastPrice(ESU6) > settlementPrice(ESU6) * 1.01` |

**Subject format:** exact contract symbol — use the `symbol` field from
`market_snapshot` or `search_contracts` results. Examples: `ESU6`,
`BTC/USD`, `CLU6`. Do NOT pass bare product codes like `ES` — the
alert will fail to resolve.

## Position (13) — subject is contract name

The alert context looks up the position on the caller's default trading account (by convention).
Quantity functions are in contracts; USD-suffixed functions are in dollars.

| Function | Meaning | Example |
|----------|---------|---------|
| `netPos` | Signed net quantity (long > 0, short < 0) | `netPos(ESU6) > 0` |
| `bought` | Cumulative buy qty | reference |
| `sold` | Cumulative sell qty | reference |
| `longPos` | Long-side qty | reference |
| `shortPos` | Short-side qty | reference |
| `posInitMargin` | Position's initial margin (contract ccy) | reference |
| `posMaintMargin` | Position's maintenance margin | reference |
| `posInitMarginUsd` | Initial margin in USD | `posInitMarginUsd(ESU6) > 10000` |
| `posMaintMarginUsd` | Maintenance margin in USD | reference |
| `posOpenPL` | Open P&L in contract points | reference |
| `posOpenPLUsd` | **Open P&L in USD** — most common trigger | `posOpenPLUsd(ESU6) < -300` |
| `posRealizedPL` | Realized P&L on the position | reference |
| `posTotalPL` | Realized + open P&L on the position | reference |

## Currency (1) — subject is currency code

| Function | Meaning | Example |
|----------|---------|---------|
| `currentRate` | Current FX rate vs base currency | `currentRate(EUR) > 1.10` |

Base currency is account-dependent. For a USD-funded account,
`currentRate(EUR) > 1.10` means EUR/USD > 1.10.

## Boolean functions

**None today.** The grammar supports a `BooleanCall` node, but the
server accepts no boolean function name. If an expression references a
boolean function name, the server fails to evaluate it. Do not emit
boolean calls.

## Which function lives where — quick-pick routing

| User intent | Function(s) |
|-------------|-------------|
| Price crossing a level | `lastPrice`, `bidPrice`, `offerPrice` |
| Stop heads-up (long) | `lastPrice` close to entry-minus-stop-dist |
| P&L floor on a position | `posOpenPLUsd` |
| Day-loss budget hit | `dollarOpenPL` or `dollarTotalPL` (account) |
| Margin blow-up warning | `totalUsedMargin` vs `netLiq` |
| Session break | `lastPrice` vs `highPrice` / `lowPrice` / `openPrice` |
| Gap from settle | `lastPrice` vs `settlementPrice` |
| FX watch | `currentRate(CCY)` |
| Relative strength | two `percentChange(...)` compared |

## Which function DOES NOT exist — do not try

- No ATR, RSI, moving averages, or any indicator math.
- No historical-bar access (`close[-1]`, `high[-5]` style).
- No volume access.
- No positioning aggregates (total gross, total net across symbols).
- No time-of-day conditions (alert itself has no clock arithmetic — use `validUntil`
  or a separate time-based guard upstream).
- No string operations or regex matching.

When the user asks for any of these, say the DSL cannot express it.
Offer the closest single-point proxy instead (e.g., snapshot an ATR band NOW and emit a fixed-price bracket).
