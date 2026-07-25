---
version: 1.1.0
last_updated: 2026-03-26
compatible_report_versions: [1, 2]
analysis_type: mistake_identification
---

# Prompt: Trade Mistake Identification

## System Instructions

You are analyzing a fact-only futures trade timeline report. Your task is to identify trading mistakes using only observable facts from the report.

### Contract Context

The report includes a `contracts` map keyed by contract_id with product details:
- `product_name` — full instrument name (e.g., "E-Mini S&P 500")
- `contract_name` — symbol (e.g., "ESH6")
- `dollar_per_tick` — dollar value of one tick (e.g., $12.50 for ES)
- `tick_size`, `value_per_point`, `is_micro`

Each trade includes dollar P&L fields alongside tick/R values:
- `realized_pnl_dollars`, `mfe_dollars`, `mae_dollars`

**Always reference the product by name** (not contract_id). Use dollar values to quantify the real cost of mistakes — "$125 left on the table" is more actionable than "10 ticks of giveback".

### Constraints

**STRICT RULES:**
1. **Only use facts present in the report** - No speculation or assumptions
2. **Cite exact YAML paths** - Every statement must reference a field (e.g., `trades[0].timeline[1].pnl_R`)
3. **No interpretation without evidence** - If a claim is not directly supported, do not state it
4. **Label hypotheses explicitly** - Mark anything requiring additional data as "hypothesis"
5. **Be concise** - Evidence-based statements only
6. **Use dollar amounts for impact** - Quantify mistakes in dollars when `realized_pnl_dollars` is available

### Output Format

Provide:
1. **Factual Observations** (3-7 items)
   - Fact with YAML path citation
   - No interpretation, just what the data shows

2. **Inconsistencies** (if any)
   - Compare intended outcome vs actual outcome
   - Use MFE/MAE and action flags
   - Cite specific fields

3. **Mechanical Improvement Hypotheses** (max 3)
   - Label as "hypothesis"
   - State what additional data would confirm it
   - Provide measurable rule change

---

## Task

Analyze the trade timeline below and identify mistakes following the constraints above.

### Example Output Format

**Factual Observations:**

1. Trade reached maximum favorable excursion of +0.7R at +2 minutes offset (`trades[0].timeline[1].pnl_R.mfe = +0.7`)
2. Final realized P&L was -0.4R (`trades[0].exit.realized_R = -0.4`)
3. No scaling action was taken during trade lifecycle (`trades[0].trade_state.scale_out = 0` for all timeline entries)
4. Volume participation rate was 1.60× session average at MFE peak (`trades[0].timeline[1].minute_volume_features.participation_rate_vs_session = 1.60`)
5. Full giveback from MFE occurred (`trades[0].derived.giveback_from_mfe_pct = 100`)

**Inconsistencies:**

Favorable excursion was achieved but not monetized:
- MFE reached planned scale level (+0.7R target)
- Trade had strong momentum confirmation (participation_rate_vs_session = 1.60, poc_shift = 'up')
- No partial profit taking occurred (scale_out = 0)
- Trade reversed to -0.4R loss (realized_vs_mfe_pct = 0)

**Mechanical Improvement Hypotheses:**

1. **Hypothesis:** Mandatory scaling at MFE >= 0.7R would improve expectancy
   - **Evidence needed:** Backtest across all trades with MFE >= 0.7R
   - **Proposed rule:** `IF mfe_R >= 0.7 AND participation_rate_vs_session >= 1.3 THEN scale_out 50%`
   - **Dollar impact:** MFE was $875 (`trades[0].mfe_dollars`), realized was -$500 — $1,375 swing from peak

2. **Hypothesis:** Volume decay signal was actionable
   - **Evidence:** participation_rate_vs_session dropped to 0.90 at +6m (`trades[0].timeline[2].minute_volume_features.participation_rate_vs_session = 0.90`)
   - **Proposed rule:** `IF participation_rate_vs_session < 1.0 AFTER mfe_R > 0.5 THEN tighten_stop OR reduce_size`

---

## Trade Timeline Report

(Report YAML/JSON will be appended here)
