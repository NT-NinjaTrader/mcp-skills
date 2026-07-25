# Hedge patterns — common cross-asset priors

Reference ranges for typical cross-underlying correlations in US futures.
Use these as priors when the user asks "is X correlated with Y?", before you pull live data.
Then confirm with `correlation.py`.

**All numbers are rough priors.** Correlations drift with regime.
Always validate with a recent-history run.

## Table of contents

1. Equity-index family (ES / NQ / YM / RTY)
2. Energy complex (CL / NG / HO / RB)
3. Metals (GC / SI / HG)
4. Bonds (ZB / ZN / ZF / ZT / UB)
5. Currencies (6E / 6B / 6J / 6A / DX)
6. Grains (ZC / ZS / ZW)
7. Cross-family (stocks vs bonds, stocks vs metals)

---

## 1. Equity-index family

All four US equity-index futures are tightly coupled in normal
regimes. Correlation is highest within size brackets (ES+NQ large-
cap, RTY+YM divergence).

| Pair | Typical r | β (B on A, log-rtn) | Notes |
|------|-----------|---------------------|-------|
| ES ↔ NQ | 0.85 – 0.95 | 1.2 – 1.5 | NQ has higher vol; β > 1 typical |
| ES ↔ YM | 0.90 – 0.97 | 0.9 – 1.1 | Closest to unit-β pair |
| ES ↔ RTY | 0.70 – 0.88 | 0.9 – 1.4 | Small-cap decoupling in risk-off |
| NQ ↔ RTY | 0.60 – 0.80 | 0.7 – 1.1 | Growth vs small-cap dispersion |

**When correlation tightens (>0.9 rolling)**: index-level macro move;
hedging one with another is effective.

**When correlation loosens (<0.6)**: sector rotation in progress;
single-index exposure does not equal broad-market exposure.

## 2. Energy complex

Looser than equity-index. Crude oil + refined products are tight,
but crude vs natural gas is structurally weak.

| Pair | Typical r | Notes |
|------|-----------|-------|
| CL ↔ RB | 0.70 – 0.88 | Gasoline tracks crude |
| CL ↔ HO | 0.65 – 0.85 | Heating oil tracks crude, seasonal |
| CL ↔ NG | -0.10 – 0.40 | Structurally decoupled — DO NOT hedge CL with NG |
| RB ↔ HO | 0.55 – 0.75 | Both refined; seasonal offset |

## 3. Metals

| Pair | Typical r | Notes |
|------|-----------|-------|
| GC ↔ SI | 0.65 – 0.85 | Silver has higher vol; β on gold often > 1.5 |
| GC ↔ HG | 0.30 – 0.60 | Copper diverges with industrial cycles |
| SI ↔ HG | 0.40 – 0.65 | Industrial-metals correlation |

## 4. Bonds

Tightly correlated across the curve. Differences are duration and
steepening trades.

| Pair | Typical r | Notes |
|------|-----------|-------|
| ZB ↔ ZN | 0.92 – 0.98 | ZB has longer duration (higher β on yield moves) |
| ZN ↔ ZF | 0.90 – 0.97 | Five-year vs ten-year curve trades |
| UB ↔ ZB | 0.85 – 0.95 | Ultra vs 30-year |

## 5. Currencies

| Pair | Typical r | Notes |
|------|-----------|-------|
| 6E ↔ 6B | 0.55 – 0.80 | Euro vs sterling; ECB/BOE path divergence |
| 6E ↔ DX | -0.90 – -0.98 | Euro is ~58% of DX basket — near-perfect inverse |
| 6J ↔ DX | -0.50 – -0.75 | Yen vs dollar (yen is 14% of DX) |
| 6A ↔ 6E | 0.30 – 0.60 | Risk-on currencies sometimes cluster |

## 6. Grains

| Pair | Typical r | Notes |
|------|-----------|-------|
| ZC ↔ ZS | 0.50 – 0.80 | Corn ↔ soybeans, substitutes in feed |
| ZS ↔ ZW | 0.40 – 0.70 | Soybeans ↔ wheat, both grains |
| ZC ↔ ZW | 0.45 – 0.65 | Less direct substitution |

## 7. Cross-family

| Pair | Typical r | Notes |
|------|-----------|-------|
| ES ↔ ZB | -0.30 – +0.20 | Classic stock/bond correlation — HIGHLY regime-dependent (goes positive in inflation scares, negative in flights-to-quality) |
| ES ↔ GC | -0.20 – +0.30 | Gold as hedge is unreliable; driven by real yields more than stocks |
| ES ↔ DX | -0.40 – +0.20 | Dollar vs stocks, regime-dependent |
| ES ↔ CL | -0.20 – +0.40 | Often positive in growth expansions |

## How to narrate a hedge proposal

1. **Report live correlation** from `correlation.py`. Compare it to the range in this file. Flag it if the current value is outside the typical range.
2. **Compute a β-based hedge** via `hedge_sizing.py`. Show raw qty, rounded qty, and residual_pct.
3. **Warn if the pair is low-r** (|r| < 0.5). Tell the user the hedge is mostly dollar-neutral in expectation, but variance will be high.
4. **Warn if you suspect a regime shift.** Check whether `correlation.py`'s rolling output says "tightening" or "loosening". If so, mention that the hedge math assumes a stable correlation.
5. **Suggest micros** when `rounded_qty = 0` or `residual_pct > 30`.

## Avoid

- Do not hedge across unrelated products based only on a "feel" correlation. Always pull recent data.
- Do not hedge with a negatively-correlated pair unless you understand the regime. Stock/bond hedges famously failed in 2022.
- Do not hedge a trade that the user already plans to close. The commissions and slippage outweigh the exposure reduction.
