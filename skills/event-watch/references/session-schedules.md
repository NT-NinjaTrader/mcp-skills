# Session schedules — US futures markets

All times are ET (America/New_York).
The clock itself handles daylight savings — the hours below are local clock time.

## CME equity indexes (ES, NQ, YM, RTY + micros)

| Phase            | Time (ET)          | Notes                                   |
|------------------|--------------------|-----------------------------------------|
| Globex open      | Sun 18:00          | Week opens                              |
| Overnight        | 18:00 – 09:30      | Thinner, wider spreads                  |
| NY cash open     | 09:30              | Volume + vol spike; spreads widen        |
| NY cash hours    | 09:30 – 16:00      | Highest liquidity                       |
| Settlement       | 16:00 (Mon–Fri)    | Daily settlement print                  |
| Post-settlement  | 16:00 – 17:00      | Trading continues; thin after the print |
| Daily halt       | 17:00 – 18:00      | Daily maintenance period; no trading    |
| Re-open          | 18:00              | Next Globex session                     |
| Weekly close     | Fri 17:00          | Shut until Sun 18:00 (about 49 hours)   |

## CME energy (CL, NG + micros)

| Phase             | Time (ET)          | Notes                                     |
|-------------------|--------------------|-------------------------------------------|
| Globex open       | Sun 18:00          |                                           |
| Pit equivalent    | 09:00 – 14:30      | Historical volume concentration           |
| EIA release (CL)  | Wed 10:30          | Weekly crude oil inventory                |
| EIA release (NG)  | Thu 10:30          | Weekly natural gas storage                |
| Settlement        | 14:30 (Mon–Fri)    | Pit-settled contracts                     |
| Daily halt        | 17:00 – 18:00      | Daily maintenance period; no trading      |
| Re-open           | 18:00              | Next Globex session                       |

## CME metals (GC, SI, HG + micros)

| Phase           | Time (ET)          | Notes                                     |
|-----------------|--------------------|-------------------------------------------|
| Globex open     | Sun 18:00          |                                           |
| London fix AM   | ~05:30             | Intra-day liquidity pick-up               |
| London fix PM   | ~10:00             |                                           |
| NY pit equiv    | 08:20 – 13:30 (GC) |                                           |
| Settlement      | 13:30 (GC, Mon–Fri)|                                           |
| Daily halt      | 17:00 – 18:00      | Daily maintenance period; no trading      |
| Re-open         | 18:00              | Next Globex session                       |

## CBOT grains (ZC, ZS, ZW)

| Phase           | Time (ET)          | Notes                                     |
|-----------------|--------------------|-------------------------------------------|
| Overnight open  | 20:00 – 08:45      | Thinner                                   |
| Pause           | 08:45 – 09:30      | No trading                                |
| Day session     | 09:30 – 14:20      | Main liquidity window                     |
| Settlement      | 14:20 (Mon–Fri)    |                                           |

## CBOT bonds (ZB, ZN, ZF, ZT, UB)

Follow equity-index hours for most purposes. Largest vol spike around
08:30 ET releases (CPI, NFP, Retail Sales, etc.).

## FX futures (6E, 6B, 6J, 6A + micros)

Near-continuous, but activity tracks underlying spot-market hours:

- **EUR (6E)**: most active 02:00 – 12:00 ET (London + early NY)
- **GBP (6B)**: 03:00 – 12:00 ET (London-heavy)
- **JPY (6J)**: 19:00 – 04:00 ET (Tokyo session)
- **AUD (6A)**: 17:00 – 02:00 ET (Sydney + Tokyo overlap)

## High-volatility boundaries to flag on ask

When the user asks a vol/exposure question, check if *now* is near any
of these — this skill doesn't proactively warn:

- **08:30 ET** — US economic releases (CPI, NFP, Retail Sales, PPI, GDP)
- **09:30 ET** — NY cash open (indexes)
- **10:00 ET** — Mid-morning releases (ISM, consumer confidence)
- **10:30 ET (Wed/Thu)** — EIA inventories
- **13:00 ET** — Treasury auctions
- **14:00 ET** — FOMC statement / FOMC projections
- **14:30 ET** — Fed Chair press conference
- **16:00 ET** — Index settlement

## What's **not** in this file

- Option expiration calendar — live in `contract-intel` references.
- Contract roll windows — live in `contract-intel` references.
- Kalshi event contracts — single-date, no recurring session; see
  `contract-intel` § event-contracts.
